"""Domain Context object — the single source of truth for every generation agent.

Built once at the start of every blueprint generation from the user input. It
carries the detected (or synthesized) business domain, the allowed vocabulary
of the project and the forbidden vocabulary of every other known domain, so
downstream agents — LLM or deterministic — never leak entities or terminology
from unrelated industries into the blueprint.

For projects whose domain matches no known domain, a ``custom`` domain context
is synthesized deterministically from the user's own features, description and
category: business areas, core entities, modules, workflows and tables are all
derived from the input, never reused from another domain.
"""

from __future__ import annotations

import copy
import re
from typing import Any

from app.services.ai.domain_data import (
    DETECTION_KEYWORDS,
    DOMAIN_META,
    detect_domain,
    domain_tables,
    expand_entity_spec,
)

# High-signal terms per known domain. Only terms that are unambiguous markers
# of their domain are listed, so generic words (payment, product, order,
# notification, message, post, field, seed, sprint...) are never flagged.
CURATED_FORBIDDEN: dict[str, list[str]] = {
    "smart_city": [
        "municipal", "traffic signal", "traffic light", "public transport", "bus route",
        "waste collection", "citizen service", "emergency dispatch", "sensor telemetry",
        "parking zone", "street light", "city administration",
    ],
    "hospital": [
        "hospital", "clinic", "patient", "doctor", "physician", "nurse", "healthcare",
        "medical record", "prescription", "pharmacy", "medicine", "diagnosis", "surgery",
        "appointment", "ambulance", "symptom", "treatment", "vaccination", "laboratory",
        "radiology", "ward", "pharmacist", "cardiology", "pediatric",
    ],
    "food": [
        "restaurant", "cuisine", "courier", "dish", "chef", "kitchen", "takeaway",
        "meal", "ingredient", "recipe", "food delivery", "table reservation", "food truck",
    ],
    "ecommerce": [
        "cart", "wishlist", "ecommerce", "e-commerce", "marketplace", "sku",
        "coupon", "promotion code", "storefront", "merchant", "add to cart", "shopping",
    ],
    "startup": [
        "startup", "incubator", "founder", "investor", "pitch", "funding round",
        "venture capital", "angel investor", "pre-seed", "series a", "term sheet",
        "due diligence", "incubation program",
    ],
    "agriculture": [
        "farm", "farmer", "crop", "harvest", "agronomist", "irrigation", "soil",
        "livestock", "fertilizer", "pesticide", "greenhouse", "yield", "tractor",
        "plantation", "seedling",
    ],
    "finance": [
        "bank", "banking", "kyc", "loan", "overdraft", "fintech", "mortgage",
        "interest rate", "investment", "accountant", "bookkeeping", "portfolio", "crypto",
        "credit score", "wire transfer",
    ],
    "travel": [
        "travel", "tour", "hotel", "flight", "itinerary",
        "resort", "airline", "tourist", "vacation", "tourism", "boarding",
        "luggage",
    ],
    "retail": [
        "retail", "cashier", "point of sale", "pos terminal", "shelf", "barcode",
        "loyalty card", "loyalty program", "store manager",
    ],
    "manufacturing": [
        "manufacturing", "work order", "bill of materials",
        "raw material", "production line", "assembly", "quality inspector", "defect",
        "rework", "shop floor",
    ],
    "social": [
        "social media", "hashtag", "follower", "influencer", "reel", "meme",
    ],
    "inventory": [
        "inventory", "stock", "warehouse", "purchase order", "reorder level",
        "stock movement", "stockout", "pallet", "replenishment", "bin location",
    ],
    "erp": [
        "college", "university", "campus", "student", "faculty", "enrollment",
        "admissions", "tuition", "semester", "transcript", "attendance", "curriculum",
        "professor", "exam", "gradebook", "hostel",
    ],
    "chat": [
        "chat", "messaging", "chatbot", "direct message", "read receipt", "group chat",
        "instant messaging",
    ],
    "ai": [
        "resume", "nlp", "machine learning", "inference", "model training",
        "dataset", "embedding", "vector search", "job seeker", "recruiter",
    ],
    "saas": [
        "subscription", "tenant", "billing plan", "seat", "sso",
        "kanban", "timesheet",
    ],
}

# Domain labels too generic to act as cross-domain signals (they appear in
# normal software-engineering language and would flag healthy blueprints).
LOW_SIGNAL_LABELS = {"communication", "saas"}

DOMAIN_LABELS = {key: meta.get("label", key) for key, meta in DOMAIN_META.items()}


def _tokens(text: str) -> list[str]:
    """Normalized lowercase tokens (3+ chars) from a blob of text."""
    return [t for t in re.split(r"[^a-z0-9]+", str(text).lower()) if len(t) >= 3]


def _pluralize(name: str) -> str:
    if name.endswith(("s", "x", "z", "ch", "sh")):
        return f"{name}es"
    if name.endswith("y") and len(name) > 2 and name[-2] not in "aeiou":
        return f"{name[:-1]}ies"
    return f"{name}s"


def _snake(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def _custom_domain_meta(input_data: dict[str, Any]) -> dict[str, Any]:
    """Synthesize a domain meta for projects that match no known domain."""
    category = str(input_data.get("category") or "").strip()
    label = category or "Custom Domain"
    features = [str(f).strip() for f in input_data.get("features", []) if str(f).strip()]
    if not features:
        features = ["Core records", "Workflows", "Reporting"]
    target_users = [u.strip() for u in str(input_data.get("target_users") or "").split(",") if u.strip()]

    entities = []
    workflows = []
    modules = []
    for i, feature in enumerate(features[:8]):
        entity = _snake(feature) or f"entity_{i + 1}"
        singular = entity.rstrip("s") or entity
        table = _pluralize(singular)
        entities.append(
            expand_entity_spec(
                (
                    table,
                    f"Records managed by the '{feature}' business area.",
                    [
                        ("name", "VARCHAR(150) NOT NULL", f"{feature} record name"),
                        ("description", "TEXT", f"{feature} details"),
                        ("status", "VARCHAR(20) DEFAULT 'active'", "Record state"),
                        ("owner_id", "INTEGER REFERENCES users(id)", "Owning user"),
                        ("created_at", "TIMESTAMPTZ DEFAULT now()", "Creation time"),
                        ("updated_at", "TIMESTAMPTZ DEFAULT now()", "Last update"),
                    ],
                    [_idx_("idx", f"{table}_owner", ["owner_id"], False)],
                    [],
                    "3NF; records belong to exactly one owner and carry an audit-friendly state.",
                )
            )
        )
        workflows.append(
            {
                "name": f"{feature} workflow",
                "description": f"The end-to-end '{feature}' process for this project.",
                "steps": [f"Create {feature}", f"Track {feature}", f"Complete {feature}"],
            }
        )
        modules.append(
            {
                "name": feature,
                "purpose": f"'{feature}' records and workflows",
                "entities": [table],
            }
        )

    return {
        "label": label,
        "core_workflow": (
            f"Users register, operate the core records ({', '.join(features[:3])}) "
            f"and advance each workflow, with role-scoped access and audited state transitions."
        ),
        "primary_users": target_users or ["End users", "Managers", "Administrators"],
        "roles": [
            "Member",
            "Manager",
            "Administrator"
        ] + [r for r in target_users if r.lower() not in ("member", "manager", "administrator")][:2],
        "processes": features,
        "entities": entities,
        "modules": modules,
        "business_rules": [
            "Record status changes are written to the immutable audit log.",
            "Only users with an administrative role may approve state transitions.",
            "Every core record is validated before it becomes active.",
        ],
        "future_expansion": ["Real-time dashboards", "Advanced analytics", "Mobile application"],
        "workflows": workflows,
        "keywords": [],
    }


def _idx_(prefix: str, name: str, columns: list[str], unique: bool) -> tuple[str, list[str], bool]:
    return (name, columns, unique)


def _domain_meta_for(key: str, input_data: dict[str, Any]) -> dict[str, Any]:
    if key == "custom":
        meta = _custom_domain_meta(input_data)
        meta["key"] = key
        return meta
    meta = dict(DOMAIN_META.get(key, DOMAIN_META["saas"]))
    meta["key"] = key
    meta["keywords"] = [kw for dkey, kws in DETECTION_KEYWORDS if dkey == key for kw in kws]
    return meta


def _entity_names(entities: list[Any]) -> list[str]:
    names: list[str] = []
    for e in entities or []:
        if isinstance(e, dict):
            names.append(str(e.get("name", "")))
        elif isinstance(e, tuple) and e:
            names.append(str(e[0]))
    return names


def _allowed_vocabulary(input_data: dict[str, Any], meta: dict[str, Any]) -> list[str]:
    """Allowed terms: the user's own input plus the project domain's vocabulary."""
    allowed: set[str] = set()
    blob = " ".join(
        str(input_data.get(k, "")) for k in ("name", "category", "description", "target_users")
    ) + " " + " ".join(str(f) for f in input_data.get("features", []) or [])
    allowed.update(_tokens(blob))
    meta_blob = " ".join(
        [
            str(meta.get("label", "")),
            " ".join(str(p) for p in meta.get("processes", [])),
            " ".join(str(w.get("name", "")) for w in meta.get("workflows", [])),
            " ".join(str(r) for r in meta.get("roles", [])),
            " ".join(str(u) for u in meta.get("primary_users", [])),
            " ".join(_entity_names(meta.get("entities", []) or [])),
            " ".join(str(m.get("name", "")) for m in meta.get("modules", [])),
            " ".join(str(x) for x in meta.get("future_expansion", [])),
            " ".join(str(k) for k in meta.get("keywords", [])),
        ]
    ).lower()
    allowed.update(_tokens(meta_blob))
    allowed.update(str(meta.get("label", "")).lower().split())
    return sorted(allowed)


def _forbidden_vocabulary(key: str) -> list[str]:
    """Forbidden terms: high-signal vocabulary of every domain except the project's own."""
    forbidden: set[str] = set()
    for domain_key, terms in CURATED_FORBIDDEN.items():
        if domain_key == key:
            continue
        forbidden.update(terms)
        label = DOMAIN_LABELS.get(domain_key, domain_key)
        if label.lower() not in LOW_SIGNAL_LABELS:
            forbidden.add(label.lower())
    return sorted(forbidden)


def _normalize_entity(spec: Any) -> dict[str, Any]:
    """Normalize an entity definition (dict or compact tuple) into a table dict."""
    if isinstance(spec, dict):
        return dict(spec)
    if len(spec) >= 6:
        return expand_entity_spec(spec)
    name, purpose, columns = spec[:3]
    return {
        "name": name,
        "purpose": purpose,
        "columns": [
            {"name": col, "type": ctype, "constraints": [], "description": cdesc}
            for col, ctype, cdesc in columns
        ],
        "indexes": [],
        "relationships": [],
        "normalization_notes": "Designed in third normal form.",
    }


def build_domain_context(input_data: dict[str, Any]) -> dict[str, Any]:
    """Build the immutable Domain Context object for one blueprint generation.

    This is the single source of truth consumed by every generation agent and
    by the semantic consistency checker. It is derived deterministically from
    the user input, so it is fully isolated between projects.

    The returned object is a deep copy: no agent may mutate the domain, the
    allowed vocabulary or the forbidden vocabulary after the context has been
    created. Per-agent output is validated against it before admission to the
    pipeline (see ``agents._build_agent_node``).
    """
    name = str(input_data.get("name") or "Untitled Project")
    key = detect_domain(
        str(input_data.get("category") or ""),
        name,
        str(input_data.get("description") or ""),
        list(input_data.get("features", []) or []),
    )
    meta = _domain_meta_for(key, input_data)
    entities = meta.get("entities")
    if entities:
        tables = [_normalize_entity(t) for t in entities]
    else:
        # Recipe-sourced domains define ``entities: None`` and reuse the proven
        # v1 table designs from templates.TABLE_RECIPES.
        tables = [_normalize_entity(t) for t in domain_tables(key)]

    table_names = {t.get("name", "").rstrip("s") for t in tables if t.get("name")}
    module_names = {str(m.get("name", "")).rstrip("s") for m in meta.get("modules", [])}
    core_entities = sorted(table_names | module_names)

    forbidden = _forbidden_vocabulary(key)
    allowed = _allowed_vocabulary(input_data, meta)

    context = {
        "project_name": name,
        "primary_domain": key,
        "domain_label": meta["label"],
        "is_custom_domain": key == "custom",
        "business_areas": list(meta.get("processes", [])),
        "core_entities": [e for e in core_entities if e],
        "allowed_vocabulary": list(allowed),
        "forbidden_vocabulary": [f for f in forbidden if f not in allowed],
        "tables": tables,
        "meta": copy.deepcopy(meta),
        "module_names": [str(m.get("name", "")) for m in meta.get("modules", [])],
        "user_roles": list(meta.get("roles", [])),
        "business_processes": list(meta.get("processes", [])),
        "technology_constraints": _technology_constraints(input_data),
    }
    return copy.deepcopy(context)


def _technology_constraints(input_data: dict[str, Any]) -> list[str]:
    """Project-specific technology constraints derived from the user input."""
    stacks = [
        input_data.get("preferred_frontend"),
        input_data.get("preferred_backend"),
        input_data.get("database"),
        input_data.get("auth_method"),
        input_data.get("deployment_platform"),
        input_data.get("language"),
    ]
    return [str(s) for s in stacks if s]


def find_forbidden_terms(text: str, forbidden_terms: list[str]) -> list[str]:
    """Word-boundary scan of *text* for forbidden terms, most frequent first.

    Each term is also matched in its plural form, so 'traffic signal' flags
    'traffic signals' as well. JSON escape sequences are normalized first, so
    word boundaries are not corrupted by the trailing letters of escapes like
    '\\n'.
    """
    raw = str(text or "").lower()
    for escape in ("\\n", "\\t", "\\r", '\\"', "\\\\", "\\u"):
        raw = raw.replace(escape, " ")
    lowered = f" {raw} "
    variants: dict[str, list[str]] = {}
    for term in forbidden_terms:
        forms = {term, _pluralize(term)}
        forms.discard(term)
        variants[term] = sorted(forms)
    hits: list[tuple[int, str]] = []
    for term, plurals in variants.items():
        patterns = [rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])"]
        patterns += [rf"(?<![a-z0-9]){re.escape(p)}(?![a-z0-9])" for p in plurals]
        count = sum(len(re.findall(pattern, lowered)) for pattern in patterns)
        if count:
            hits.append((count, term))
    hits.sort(key=lambda item: (-item[0], item[1]))
    return [term for _, term in hits]
