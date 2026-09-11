"""V2 deterministic reasoning engine.

Implements the same eleven-section pipeline as the LLM agents, but with
explicit domain knowledge instead of templates. Every decision carries a
written reason, the database comes from the domain entity model, workflows
drive the API and UI design, and a complexity scoring engine sizes the
roadmap. A deterministic cross-validation pass audits the assembled blueprint.

Used when no LLM key is configured, as a per-section fallback when the LLM
fails, and as the deterministic baseline for tests.
"""
from __future__ import annotations

from typing import Any

from app.services.ai import templates, v3_architect
from app.services.ai.domain_context import build_domain_context
from app.services.ai.domain_data import detect_domain

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

COMPLEXITY_WEIGHTS: dict[str, int] = {
    "hospital": 10,
    "finance": 12,
    "manufacturing": 12,
    "startup": 8,
    "agriculture": 8,
    "travel": 7,
    "retail": 7,
    "ecommerce": 8,
    "social": 8,
    "inventory": 7,
    "erp": 9,
    "chat": 7,
    "food": 7,
    "ai": 10,
    "saas": 6,
    "smart_city": 10,
    "custom": 8,
}


def _slug_path(name: str) -> str:
    return "/" + name.replace("_", "-")


def _workflow_diagram(steps: list[str]) -> str:
    """Render ordered workflow steps as a raw mermaid flowchart."""
    lines = ["flowchart LR"]
    prev: int | None = None
    for i, step in enumerate(steps):
        text = step.replace('"', "'")
        lines.append(f"    N{i}[\"{text}\"]")
        if prev is not None:
            lines.append(f"    N{prev} --> N{i}")
        prev = i
    return "\n".join(lines)


def _domain_key(input_data: dict[str, Any]) -> str:
    return detect_domain(
        input_data.get("category", ""),
        input_data.get("name", ""),
        input_data.get("description", ""),
        input_data.get("features", []),
    )


def _resolve_ctx(input_data: dict[str, Any], ctx: dict[str, Any] | None) -> dict[str, Any]:
    """Return the Domain Context, building it from the input when absent."""
    if ctx is None:
        ctx = build_domain_context(input_data)
    return ctx


def _normalize_project_input(input_data: dict[str, Any]) -> dict[str, Any]:
    """Accept both ``name`` and ``project_name`` aliases.

    The wizard sends ``project_name``; the deterministic engine and domain
    context use ``name`` internally.  This normaliser mutates a copy so the
    original caller is never affected.
    """
    if "name" not in input_data and "project_name" in input_data:
        data = dict(input_data)
        data["name"] = data.pop("project_name")
        return data
    return input_data


# ---------------------------------------------------------------------------
# Complexity scoring engine
# ---------------------------------------------------------------------------

def complexity_score(input_data: dict[str, Any]) -> dict[str, Any]:
    """Score build complexity 0-100 and derive time and team sizing."""
    features = input_data.get("features", []) or []
    domain = _domain_key(input_data)
    auth = input_data.get("auth_method", "JWT")
    backend = input_data.get("preferred_backend", "")
    database = input_data.get("database", "")
    deployment = input_data.get("deployment_platform", "")

    factors: list[str] = []
    score = 15
    score += min(len(features) * 4, 24)
    factors.append(f"{min(len(features), 6)} core feature areas add up to 24 points" if features else "No explicit feature list; baseline scope")

    weight = COMPLEXITY_WEIGHTS.get(domain, 6)
    score += weight
    factors.append(f"Domain '{domain}' carries a complexity weight of {weight}")

    if auth in ("OAuth", "Firebase"):
        score += 5
        factors.append(f"{auth} adds a third-party identity provider integration")
    if backend in ("Spring Boot", "Django"):
        score += 4
        factors.append(f"{backend} brings framework-level boilerplate and domain modeling overhead")
    if database == "MongoDB":
        score += 3
        factors.append("Document database adds schema-governance and data-integrity work")
    if deployment in ("Kubernetes", "AWS", "Azure", "GCP"):
        score += 5
        factors.append(f"{deployment} adds infrastructure-as-code and operations complexity")
    if domain in ("finance", "hospital"):
        score += 6
        factors.append(f"{domain} data is sensitive; compliance and audit requirements raise the bar")

    score = max(15, min(95, score))
    level = "Low" if score < 40 else "Medium" if score <= 70 else "High"
    if level == "Low":
        estimated_time = "4-6 weeks"
        team = {"roles": [{"role": "Full-stack developer", "count": 1}, {"role": "QA / Product", "count": 1}], "total": 2}
    elif level == "Medium":
        estimated_time = "6-10 weeks"
        team = {"roles": [{"role": "Full-stack developer", "count": 2}, {"role": "QA engineer", "count": 1}], "total": 3}
    else:
        estimated_time = "12-18 weeks"
        team = {
            "roles": [
                {"role": "Full-stack developer", "count": 2},
                {"role": "Frontend developer", "count": 1},
                {"role": "QA engineer", "count": 1},
                {"role": "DevOps engineer", "count": 1},
            ],
            "total": 5,
        }

    return {
        "score": score,
        "level": level,
        "reasoning": "Score drivers: " + "; ".join(factors),
        "estimated_time": estimated_time,
        "estimated_team": team,
    }


# ---------------------------------------------------------------------------
# 1. Requirements Analysis
# ---------------------------------------------------------------------------

def _analysis(input_data: dict[str, Any], ctx: dict[str, Any] | None = None) -> dict[str, Any]:
    ctx = _resolve_ctx(input_data, ctx)
    name = input_data["name"]
    desc = input_data["description"] or (
        f"A {input_data['category'].lower()} application designed to solve a focused business problem."
    )
    features = input_data["features"] or ["User management", "Core domain workflows", "Reporting"]
    meta = ctx["meta"]

    frs = [
        {
            "id": "FR-1",
            "title": "User authentication",
            "description": f"Register, login, logout and profile management using {input_data['auth_method']}.",
            "priority": "Must Have",
        },
        {
            "id": "FR-2",
            "title": "Role-based access control",
            "description": f"{', '.join(meta['roles'][:4])} roles with permission scoping for all resources.",
            "priority": "Must Have",
        },
    ]
    for i, feature in enumerate(features[:8]):
        frs.append(
            {
                "id": f"FR-{i + 3}",
                "title": feature,
                "description": f"Complete {feature.lower()} workflow: create, read, update, delete, search and audit.",
                "priority": "Must Have" if i < 3 else "Should Have",
            }
        )
    frs.append({"id": "FR-X", "title": "Audit logging", "description": "Immutable audit trail for sensitive operations.", "priority": "Should Have"})

    complexity = complexity_score(input_data)

    return {
        "problem_statement": (
            f"Organizations and users currently lack a unified, purpose-built solution for {name.lower()}. "
            f"Existing generic tools force manual workarounds, scattered data and inconsistent workflows. "
            f"{desc.strip('.')}. This project delivers a dedicated {meta['label'].lower()} platform that "
            f"automates the domain workflows, enforces data integrity, and provides actionable reporting."
        ),
        "objectives": [
            f"Deliver a production-ready {name} with the chosen {input_data['preferred_backend']} + {input_data['preferred_frontend']} stack",
            f"Automate the {meta['label']} core workflows end-to-end",
            "Enforce data integrity, security and auditability",
            "Provide role-aware dashboards and reporting",
            "Ship with CI/CD, tests and documentation from day one",
        ],
        "target_audience": (
            [u.strip() for u in input_data["target_users"].split(",") if u.strip()]
            or meta["primary_users"][:4]
        ),
        "functional_requirements": frs,
        "non_functional_requirements": [
            {"id": "NFR-1", "title": "Performance", "description": "API p95 latency under 500ms for read paths; pages interactive under 2s on broadband."},
            {"id": "NFR-2", "title": "Security", "description": f"OWASP Top 10 hardened; {input_data['auth_method']} with short-lived tokens; encrypted secrets."},
            {"id": "NFR-3", "title": "Reliability", "description": "99.9% availability target; graceful degradation; automated health checks."},
            {"id": "NFR-4", "title": "Scalability", "description": "Stateless API services to allow horizontal scaling; database read replicas at scale."},
            {"id": "NFR-5", "title": "Maintainability", "description": "Modular layered architecture, typed contracts, and CI-enforced code quality."},
            {"id": "NFR-6", "title": "Accessibility", "description": "WCAG 2.1 AA compliance for all public-facing flows."},
        ],
        "constraints": [
            f"The preferred stack ({input_data['preferred_frontend']} + {input_data['preferred_backend']} + {input_data['database']}) is fixed",
            f"Domain rules of {meta['label']} must be enforced in the data layer, not just the UI",
            "OWASP Top 10 security baseline",
        ],
        "assumptions": [
            "Users access the system over HTTPS from modern browsers",
            "Single-region deployment is sufficient for the first release",
            "Transactional email is delivered through a provider (SMTP or API)",
        ],
        "acceptance_criteria": [
            "All Must Have functional requirements are implemented and demoable",
            "Every documented endpoint is covered by an automated API test",
            "CI is green on every push to main",
            "All export formats (markdown, json, zip, pdf, docx) produce complete output",
        ],
        "complexity_score": complexity,
        "suggested_improvements": [
            "Start with a vertical-slice MVP to validate the core workflow early",
            "Add structured audit logging before the first release",
            "Instrument analytics from day one to drive product decisions",
            "Use feature flags to ship continuously without downtime",
        ],
        "risks": [
            {"risk": "Scope creep during feature definition", "likelihood": "High", "impact": "Medium", "mitigation": "Freeze scope at week 2; prioritize by impact."},
            {"risk": f"{input_data['database']} schema changes late in the cycle", "likelihood": "Medium", "impact": "High", "mitigation": "Mandatory migrations + integration tests."},
            {"risk": "Third-party API availability (auth/payments)", "likelihood": "Medium", "impact": "Medium", "mitigation": "Abstract integrations behind interfaces with mock fallbacks."},
            {"risk": "Security review gaps", "likelihood": "Medium", "impact": "High", "mitigation": "Automated SAST in CI + scheduled dependency updates."},
            {"risk": f"{meta['label']} domain rule violations", "likelihood": "Medium", "impact": "High", "mitigation": "Encode business rules as database constraints and service-layer validations."},
        ],
    }


# ---------------------------------------------------------------------------
# 2. Domain Understanding
# ---------------------------------------------------------------------------

def _domain_understanding(
    input_data: dict[str, Any], analysis: dict[str, Any], ctx: dict[str, Any] | None = None
) -> dict[str, Any]:
    ctx = _resolve_ctx(input_data, ctx)
    meta = ctx["meta"]
    blob = f"{input_data.get('category', '')} {input_data['name']} {input_data.get('description', '')} {' '.join(input_data.get('features', []))}".lower()
    matching = [kw for kw in meta.get("keywords", []) if kw in blob][:5] or ["core domain vocabulary"]
    return {
        "identified_domain": ctx["primary_domain"],
        "domain_label": ctx["domain_label"],
        "is_custom_domain": ctx["is_custom_domain"],
        "domain_reasoning": (
            f"The project description matches the {ctx['domain_label']} domain through signals like "
            f"{', '.join(matching)}. The analysis confirms processes such as "
            f"{', '.join(meta['processes'][:4])}, which are characteristic of this domain."
            if not ctx["is_custom_domain"]
            else (
                f"The project does not match any known domain; its business areas "
                f"({', '.join(meta['processes'][:4])}) were derived directly from the requested features, "
                f"so the blueprint stays domain-specific to '{input_data['name']}'."
            )
        ),
        "core_workflow": meta["core_workflow"],
        "primary_users": meta["primary_users"],
        "roles": meta["roles"],
        "processes": meta["processes"],
        "domain_knowledge_notes": (
            [
                f"Primary processes: {', '.join(meta['processes'])}",
                f"Core workflow: {meta['core_workflow']}",
                "Users expect role-scoped access to a shared record of truth",
                "Every mutation of business state must be auditable",
            ]
            + [f"Module '{m['name']}': {m['purpose']}" for m in meta["modules"][:4]]
        ),
        "future_expansion": meta["future_expansion"],
    }


# ---------------------------------------------------------------------------
# 3. Business Process Modeling
# ---------------------------------------------------------------------------

def _business_processes(
    input_data: dict[str, Any], domain: dict[str, Any], ctx: dict[str, Any] | None = None
) -> dict[str, Any]:
    ctx = _resolve_ctx(input_data, ctx)
    meta = ctx["meta"]
    workflows = []
    for wf in meta["workflows"]:
        workflows.append(
            {
                "name": wf["name"],
                "description": wf["description"],
                "actors": _actors_for(meta, wf["name"]),
                "steps": wf["steps"],
                "diagram": _workflow_diagram(wf["steps"]),
            }
        )

    business_rules = [
        {"rule": rule, "where_enforced": _enforcement_site(rule)} for rule in meta["business_rules"]
    ]
    role_permissions = _role_permissions(meta)
    return {
        "summary": (
            f"{meta['label']} runs on {len(workflows)} end-to-end workflows. Each workflow names its "
            f"actors and steps; the business rules below are enforced in the data layer so no client "
            f"can bypass them."
        ),
        "workflows": workflows,
        "business_rules": business_rules,
        "role_permissions": role_permissions,
        "critical_processes": [wf["name"] for wf in workflows[:3]],
    }


def _actors_for(meta: dict[str, Any], workflow_name: str) -> list[str]:
    keywords = {
        "incubation": ["Founder", "Program Manager", "Investor"],
        "investor": ["Investor", "Founder"],
        "crop": ["Farmer", "Agronomist"],
        "payment": ["Accountant", "Finance Manager", "Customer"],
        "booking": ["Traveler", "Agent", "Partner"],
        "sale": ["Customer", "Cashier", "Manager"],
        "production": ["Planner", "Operator", "Quality Inspector"],
        "post": ["User", "Moderator"],
        "patient": ["Patient", "Receptionist", "Doctor"],
        "order": ["Customer", "Restaurant Owner", "Courier"],
        "checkout": ["Customer", "Merchant"],
        "replenishment": ["Warehouse Operator", "Procurement Manager"],
        "academic": ["Student", "Faculty", "Admin"],
        "message": ["User", "Group Admin"],
    }
    for key, actors in keywords.items():
        if key in workflow_name.lower():
            return actors
    return meta["roles"][:3]


def _enforcement_site(rule: str) -> str:
    lowered = rule.lower()
    if any(k in lowered for k in ("cannot", "must not", "unique", "blocked", "forbidden", "only")):
        return "database CHECK/UNIQUE constraint plus API service-layer validation"
    if any(k in lowered for k in ("requires", "before", "gate", "after", "trigger")):
        return "API service-layer orchestration (transactional state machine)"
    if any(k in lowered for k in ("audit", "immutable", "append-only", "ledger")):
        return "append-only audit table written inside the same transaction"
    return "API service-layer validation with UI-side feedback"


def _role_permissions(meta: dict[str, Any]) -> list[dict[str, Any]]:
    permissions = []
    admin_roles = {"admin", "administrator", "owner", "system admin"}
    for role in meta["roles"]:
        lowered = role.lower()
        if any(a in lowered for a in admin_roles):
            permissions.append(
                {
                    "role": role,
                    "can": ["Manage all domain records", "Manage users and roles", "View audit logs", "Configure system settings", "Run reports and exports"],
                }
            )
        else:
            permissions.append(
                {
                    "role": role,
                    "can": [
                        "Manage own profile and preferences",
                        "View dashboards and reports scoped to own data",
                        *[f"Execute {p}" for p in meta["processes"][:2]],
                    ],
                }
            )
    return permissions


# ---------------------------------------------------------------------------
# 4. Technology Selection
# ---------------------------------------------------------------------------

def _technology_selection(
    input_data: dict[str, Any],
    domain: dict[str, Any],
    analysis: dict[str, Any],
) -> dict[str, Any]:
    frontend = input_data["preferred_frontend"]
    backend = input_data["preferred_backend"]
    database = input_data["database"]
    auth = input_data["auth_method"]
    deployment = input_data["deployment_platform"]

    fe_info = templates._frontend(frontend)
    be_info = templates._backend(backend)
    db_info = templates._db(database)
    auth_info = templates._auth(auth)
    deploy_info = templates._deploy(deployment)

    fe_alternatives = [x for x in ["React", "Vue", "Angular"] if x != frontend]
    be_alternatives = [x for x in ["FastAPI", "Django", "Node.js", "Spring Boot"] if x != backend]
    db_alternatives = [x for x in ["PostgreSQL", "MySQL", "MongoDB"] if x != database]
    auth_alternatives = [x for x in ["JWT", "OAuth", "Firebase"] if x != auth]
    deploy_alternatives = [x for x in ["Docker", "Kubernetes", "Vercel", "Netlify"] if x != deployment]

    blob = (
        f"{input_data['name']} {input_data.get('description', '')} "
        f"{' '.join(input_data.get('features', []))}".lower()
    )
    needs_ai = any(k in blob for k in ("ai", "chat", "analy", "recommend", "nlp", "ml ", "insight"))

    stack = [
        {
            "layer": "Frontend",
            "technology": frontend,
            "version": "latest LTS",
            "reason": fe_info["why"] + f" Chosen by the user; pairs with {be_info['type']}.",
            "alternatives": fe_alternatives,
            "tradeoffs": fe_info.get("type", ""),
        },
        {
            "layer": "Backend",
            "technology": backend,
            "version": "latest stable",
            "reason": be_info["why"],
            "alternatives": be_alternatives,
            "tradeoffs": be_info.get("api_docs", ""),
        },
        {
            "layer": "Database",
            "technology": database,
            "version": "latest stable",
            "reason": db_info["why"],
            "alternatives": db_alternatives,
            "tradeoffs": db_info.get("features", ""),
        },
        {
            "layer": "Authentication",
            "technology": auth,
            "version": "latest",
            "reason": auth_info["why"],
            "alternatives": auth_alternatives,
            "tradeoffs": auth_info.get("type", ""),
        },
        {
            "layer": "Deployment",
            "technology": deployment,
            "version": "latest",
            "reason": deploy_info["why"],
            "alternatives": deploy_alternatives,
            "tradeoffs": "Managed vs self-hosted tradeoff reviewed during release planning.",
        },
    ]
    if needs_ai:
        stack.append(
            {
                "layer": "AI Services",
                "technology": "OpenAI-compatible API",
                "version": "gpt-4o class model",
                "reason": "The project includes AI-assisted features (analysis/recommendation); an OpenAI-compatible API keeps provider options open.",
                "alternatives": ["Local LLM (Ollama/vLLM)", "Anthropic API", "Hugging Face Inference"],
                "tradeoffs": "Latency and cost controlled by caching and prompt budgets.",
            }
        )

    frontend_libs = {
        "Next.js": {"name": "TanStack Query", "purpose": "Server-state caching", "why": "Reduces boilerplate for fetching and cache invalidation."},
        "React": {"name": "TanStack Query + Zustand", "purpose": "Server + UI state", "why": "Smallest reliable state solution for SPA dashboards."},
        "Vue": {"name": "Pinia + TanStack Query", "purpose": "State management", "why": "Official Vue store with typed modules."},
        "Angular": {"name": "NgRx", "purpose": "Predictable state", "why": "Enterprise-grade reactive state with devtools."},
    }
    backend_libs = {
        "FastAPI": [
            {"name": "SQLAlchemy 2.0 + Alembic", "purpose": "ORM + migrations", "why": "Type-safe models and versioned schema migrations."},
            {"name": "Pydantic v2", "purpose": "Validation", "why": "Contract-first request/response models at the API boundary."},
        ],
        "Django": [
            {"name": "Django REST Framework", "purpose": "API layer", "why": "Batteries-included serializers, viewsets and auth."},
            {"name": "drf-spectacular", "purpose": "OpenAPI docs", "why": "Auto-generated OpenAPI schema from DRF views."},
        ],
        "Node.js": [
            {"name": "Prisma", "purpose": "ORM + migrations", "why": "Type-safe queries with generated client."},
            {"name": "Zod", "purpose": "Validation", "why": "Shared schemas between API and frontend typing."},
        ],
        "Spring Boot": [
            {"name": "Spring Data JPA + Flyway", "purpose": "Persistence", "why": "Repository abstractions plus versioned SQL migrations."},
            {"name": "Spring Security", "purpose": "AuthN/AuthZ", "why": "First-class OAuth2/JWT support and method security."},
        ],
    }

    key_libraries = [
        {"name": frontend_libs[frontend]["name"], "purpose": frontend_libs[frontend]["purpose"], "why": frontend_libs[frontend]["why"]},
        *backend_libs.get(backend, backend_libs["FastAPI"]),
        {"name": "pytest / Playwright", "purpose": "Testing", "why": "Fast unit tests plus browser-level E2E for critical flows."},
    ]

    patterns = [
        {"name": "Layered architecture", "why": "Separates HTTP handling, business logic and data access for testability.", "applied_to": f"{backend} API service"},
        {"name": "Repository pattern", "why": "Abstracts the database so services stay testable with fakes.", "applied_to": "Persistence layer"},
        {"name": "DTO + validation boundary", "why": "Explicit request/response contracts validated at the edge.", "applied_to": "API endpoints"},
    ]
    if analysis["complexity_score"]["level"] == "High":
        patterns.append(
            {"name": "Modular monolith with service modules", "why": "Avoids premature microservices while keeping module boundaries for later extraction.", "applied_to": "Backend codebase"}
        )

    decision_matrix = [
        {"decision": "Frontend framework", "options_considered": fe_alternatives + [frontend], "chosen": frontend, "reason": fe_info["why"]},
        {"decision": "Backend framework", "options_considered": be_alternatives + [backend], "chosen": backend, "reason": be_info["why"]},
        {"decision": "Database engine", "options_considered": db_alternatives + [database], "chosen": database, "reason": db_info["why"]},
        {"decision": "Authentication", "options_considered": auth_alternatives + [auth], "chosen": auth, "reason": auth_info["why"]},
        {"decision": "Deployment target", "options_considered": deploy_alternatives + [deployment], "chosen": deployment, "reason": deploy_info["why"]},
    ]

    return {
        "summary": (
            f"The user's preferred stack ({frontend} + {backend} + {database}, {auth} auth, {deployment} "
            f"deployment) is respected and justified for a {domain['domain_label']} product. Supporting "
            f"libraries and patterns close the gaps without adding unneeded infrastructure."
        ),
        "selected_stack": stack,
        "key_libraries": key_libraries,
        "architecture_patterns": patterns,
        "decision_matrix": decision_matrix,
        "constraints": [
            f"Database is fixed to {database}",
            f"Auth is fixed to {auth}",
            "No microservices until traffic data justifies the split",
        ],
    }


# ---------------------------------------------------------------------------
# 5. Architecture
# ---------------------------------------------------------------------------

def _architecture(
    input_data: dict[str, Any],
    domain: dict[str, Any],
    tech: dict[str, Any],
    analysis: dict[str, Any],
) -> dict[str, Any]:
    frontend, backend, database, deployment = (
        input_data["preferred_frontend"],
        input_data["preferred_backend"],
        input_data["database"],
        input_data["deployment_platform"],
    )
    complexity = analysis["complexity_score"]["level"]
    patterns = [
        {"pattern": "Layered (Controller-Service-Repository)", "explanation": "Separates HTTP handling, business logic and data access for testability.", "why_here": f"Keeps the {domain['domain_label']} business rules testable without HTTP."},
        {"pattern": "Repository pattern", "explanation": "Abstracts the database so the domain layer never depends on SQL specifics.", "why_here": f"Makes the {database} schema swappable and services unit-testable."},
        {"pattern": "DTO + validation boundary", "explanation": "Explicit request/response contracts validated at the edge.", "why_here": "Protects the domain model from malformed client input."},
    ]
    if complexity == "High":
        patterns.append(
            {"pattern": "Service layer with dependency injection", "explanation": "Enables unit testing with mocks and clean interchangeability.", "why_here": "The size of this build requires testable seams across services."}
        )

    components = [
        {"name": "Web client", "responsibility": "Rendering, state management, user interaction", "technology": frontend},
        {"name": "API service", "responsibility": "REST endpoints, validation, orchestration of workflows", "technology": backend},
        {"name": "Data store", "responsibility": "Persistent storage and queries", "technology": database},
        {"name": "Worker (optional)", "responsibility": "Email, exports, background jobs", "technology": "Celery / BullMQ / Quartz"},
        {"name": "Observability", "responsibility": "Logs, metrics, tracing, uptime", "technology": "Prometheus + Grafana / Sentry"},
    ]

    return {
        "summary": (
            f"A clean, layered web architecture for the {domain['domain_label']} domain: a {frontend} client "
            f"talks to a stateless {backend} REST API backed by {database}, deployed via {deployment}. "
            f"Workflows from the process model map onto service methods; heavy or slow work moves to background jobs."
        ),
        "patterns": patterns,
        "high_level_architecture": templates._build_high_level(frontend, backend, database, deployment),
        "component_diagram": templates._build_component_diagram(backend),
        "data_flow": templates._build_sequence(input_data, input_data["auth_method"]),
        "service_communication": (
            "graph TB\n"
            '    subgraph Services["Backend Services"]\n'
            '      AUTH["Auth Service"]\n'
            '      CORE["Core Domain Service"]\n'
            '      NOTIF["Notification Service"]\n'
            '      REPORT["Reporting Service"]\n'
            '    end\n'
            '    subgraph Infra["Shared Infrastructure"]\n'
            f'      DB["{database}"]\n'
            '      CACHE["Redis"]\n'
            '      BUS["Message Bus (Redis Streams / RabbitMQ)"]\n'
            '    end\n'
            '    CORE --> DB\n'
            '    AUTH --> DB\n'
            '    REPORT --> DB\n'
            '    CORE --> BUS\n'
            '    NOTIF --> BUS\n'
            '    REPORT --> CACHE\n'
            '    CORE --> CACHE'
        ),
        "deployment_architecture": templates._build_deployment_diagram(deployment, backend),
        "components": components,
        "design_decisions": [
            {"decision": "Stateless API", "rationale": "Enables horizontal scaling and simple deployments; session state lives in short-lived tokens."},
            {"decision": "Modular monolith over microservices", "rationale": f"{complexity} complexity does not justify distributed-system overhead at launch."},
            {"decision": "Synchronous REST + async workers", "rationale": "CRUD stays simple; emails, exports and AI calls run off the request path."},
            {"decision": "Domain-driven table ownership", "rationale": f"Every table belongs to a {domain['domain_label']} module, keeping the schema explainable."},
        ],
    }


# ---------------------------------------------------------------------------
# 6. Database
# ---------------------------------------------------------------------------

def _database(
    input_data: dict[str, Any], domain: dict[str, Any], ctx: dict[str, Any] | None = None
) -> dict[str, Any]:
    ctx = _resolve_ctx(input_data, ctx)
    database = input_data["database"]
    db_info = templates._db(database)
    tables = [dict(t) for t in templates.BASE_TABLES] + [dict(t) for t in ctx["tables"]]

    erd = templates._build_erd(tables)

    create_lines = ["-- PostgreSQL-compatible DDL generated by AI Project Builder Agent", ""]
    for table in tables:
        create_lines.append(f"CREATE TABLE IF NOT EXISTS {table['name']} (")
        for col in table["columns"]:
            create_lines.append(f"    {col['name']} {col['type']},")
        create_lines.append(");")
        create_lines.append("")
    for table in tables:
        for index in table["indexes"]:
            suffix = " UNIQUE" if index["unique"] else ""
            create_lines.append(
                f"CREATE{suffix} INDEX IF NOT EXISTS {index['name']} "
                f"ON {table['name']} ({', '.join(index['columns'])});"
            )

    fk_lines = []
    for table in tables:
        for rel in table.get("relationships", []):
            target = rel["to_table"]
            fk_lines.append(
                f"ALTER TABLE {table['name']} ADD CONSTRAINT fk_{table['name']}_{target} "
                f"FOREIGN KEY ({target.rstrip('s')}_id) REFERENCES {target}(id) ON DELETE CASCADE;"
            )
    sql_scripts = {
        "create_tables": "\n".join(create_lines),
        "indexes": "".join(
            f"CREATE{' UNIQUE' if i['unique'] else ''} INDEX IF NOT EXISTS {i['name']} "
            f"ON {t['name']} ({', '.join(i['columns'])});\n"
            for t in tables
            for i in t["indexes"]
        ).strip(),
        "constraints": "\n".join(fk_lines),
    }

    meta = ctx["meta"]
    integrity_rules = list(meta["business_rules"])
    integrity_rules += [
        "All money columns use NUMERIC, never float",
        "All timestamps use TIMESTAMPTZ",
        "Foreign keys are enforced and cascade where the domain allows",
    ]

    return {
        "erd_diagram": erd,
        "summary": (
            f"A normalized {domain['domain_label']} schema on {database} ({db_info['type']}) derived from the "
            f"domain entity model. Every table carries a normalization note; business rules from the process "
            f"model are encoded as constraints, unique indexes and append-only ledgers."
        ),
        "tables": tables,
        "sql_scripts": sql_scripts,
        "migration_scripts": [
            {"file": "0001_initial.py", "description": "Creates all base and domain tables with indexes.", "sql": sql_scripts["create_tables"]},
            {"file": "0002_constraints.py", "description": "Adds FK constraints not expressed inline.", "sql": sql_scripts["constraints"]},
        ],
        "seed_data": {
            "file": "seed/dev_seed.py",
            "description": "Deterministic development seed: admin user, roles, and sample domain records.",
            "sql": (
                "-- Seed: 1 admin user + 2 roles + sample records\n"
                "INSERT INTO roles (name, description) VALUES ('admin', 'Full access'), ('member', 'Standard access');\n"
                "INSERT INTO users (email, full_name, password_hash, is_active)\n"
                "VALUES ('admin@example.com', 'Admin', '$2b$12$placeholder_hash', true);"
            ),
        },
        "data_integrity_rules": integrity_rules,
    }


# ---------------------------------------------------------------------------
# 7. API Design
# ---------------------------------------------------------------------------

def _api(
    input_data: dict[str, Any],
    db_section: dict[str, Any],
    domain: dict[str, Any],
    processes: dict[str, Any],
) -> dict[str, Any]:
    backend_info = templates._backend(input_data["preferred_backend"])
    auth_info = templates._auth(input_data["auth_method"])
    tables = [t["name"] for t in db_section["tables"]]
    endpoints = [
        {
            "path": "/auth/register",
            "method": "POST",
            "description": "Create a new user account.",
            "authentication": "None",
            "request": {"headers": {"Content-Type": "application/json"}, "body": {"email": "string", "password": "string (min 8)", "full_name": "string"}},
            "response": {"success": {"id": 1, "email": "string"}, "errors": {"409": "Email already registered"}},
            "validation_rules": ["email format", "password min 8 chars", "unique email"],
            "status_codes": [{"code": 201, "meaning": "Created"}, {"code": 409, "meaning": "Email exists"}, {"code": 422, "meaning": "Validation failed"}],
        },
        {
            "path": "/auth/login",
            "method": "POST",
            "description": f"Authenticate and receive an access token ({input_data['auth_method']}).",
            "authentication": "None",
            "request": {"headers": {"Content-Type": "application/json"}, "body": {"email": "string", "password": "string"}},
            "response": {"success": {"access_token": "string", "token_type": "bearer"}, "errors": {"401": "Invalid credentials"}},
            "validation_rules": ["credentials must match"],
            "status_codes": [{"code": 200, "meaning": "Token issued"}, {"code": 401, "meaning": "Bad credentials"}],
        },
        {
            "path": "/auth/me",
            "method": "GET",
            "description": "Return the authenticated user profile.",
            "authentication": f"Bearer token ({input_data['auth_method']})",
            "request": {"headers": {"Authorization": "Bearer <token>"}, "body": {}},
            "response": {"success": {"id": 1, "email": "string", "full_name": "string"}, "errors": {"401": "Missing/invalid token"}},
            "validation_rules": ["valid access token required"],
            "status_codes": [{"code": 200, "meaning": "Profile"}, {"code": 401, "meaning": "Unauthorized"}],
        },
    ]
    for table in tables:
        if table in ("user_roles", "audit_logs"):
            continue
        path = _slug_path(table)
        endpoints.append(
            {
                "path": path,
                "method": "GET",
                "description": f"List {table.replace('_', ' ')} with pagination, filtering and search.",
                "authentication": f"Bearer token ({input_data['auth_method']})",
                "request": {"headers": {"Authorization": "Bearer <token>"}, "body": {}, "query": {"page": 1, "page_size": 50, "q": "optional search"}},
                "response": {"success": {"items": [], "total": 0, "page": 1}, "errors": {"401": "Unauthorized", "403": "Forbidden"}},
                "validation_rules": ["page >= 1", "page_size <= 100"],
                "status_codes": [{"code": 200, "meaning": "List"}, {"code": 401, "meaning": "Unauthorized"}],
            }
        )
        endpoints.append(
            {
                "path": path,
                "method": "POST",
                "description": f"Create a new {table.replace('_', ' ').rstrip('s')} record.",
                "authentication": f"Bearer token ({input_data['auth_method']})",
                "request": {"headers": {"Authorization": "Bearer <token>"}, "body": {"...": "resource fields"}},
                "response": {"success": {"id": 1}, "errors": {"400": "Business rule violation", "422": "Validation failed"}},
                "validation_rules": ["required fields", "foreign keys must exist", "domain business rules enforced in the service layer"],
                "status_codes": [{"code": 201, "meaning": "Created"}, {"code": 422, "meaning": "Validation failed"}],
            }
        )

    workflow_endpoints: dict[str, list[str]] = {}
    for wf in processes["workflows"]:
        action_endpoints = [
            {
                "path": f"/workflows/{_slug_path(wf['name'].lower().replace(' ', '-'))[1:]}/execute",
                "method": "POST",
                "description": f"Execute the '{wf['name']}' workflow against the current state.",
                "authentication": f"Bearer token ({input_data['auth_method']})",
                "request": {"headers": {"Authorization": "Bearer <token>"}, "body": {"...": "workflow-specific parameters"}},
                "response": {"success": {"accepted": True}, "errors": {"400": "Business rule violation", "401": "Unauthorized"}},
                "validation_rules": ["role permission required", "business rules of the workflow checked in order"],
                "status_codes": [{"code": 200, "meaning": "Workflow advanced"}, {"code": 400, "meaning": "Rule violation"}],
            }
        ]
        endpoints.extend(action_endpoints)
        workflow_endpoints[wf["name"]] = [a["path"] for a in action_endpoints]

    business_workflow_mapping = [
        {"workflow": wf_name, "endpoints": paths} for wf_name, paths in workflow_endpoints.items()
    ]

    return {
        "summary": (
            f"A REST API built with {input_data['preferred_backend']} ({backend_info['type']}). Resources "
            f"mirror the domain tables; workflow endpoints advance the modeled business processes and are "
            f"the only places business rules may fire. Authentication uses {auth_info['type']}."
        ),
        "base_url": "/api/v1",
        "auth": {"method": input_data["auth_method"], "description": auth_info["type"], "flow": auth_info["flow"]},
        "endpoints": endpoints,
        "pagination": "Offset pagination: ?page=N&page_size=N (max 100). Responses include items, total, page.",
        "error_format": '{"detail": "human readable message", "code": "MACHINE_CODE", "field": "optional"}',
        "business_workflow_mapping": business_workflow_mapping,
    }


# ---------------------------------------------------------------------------
# 8. UI/UX Planning
# ---------------------------------------------------------------------------

def _ui_ux(input_data: dict[str, Any], domain: dict[str, Any], processes: dict[str, Any]) -> dict[str, Any]:
    entity_screens = []
    for wf in processes["workflows"]:
        entity_screens.append(
            {
                "name": wf["name"],
                "route": f"/workflows/{wf['name'].lower().replace(' ', '-')}",
                "purpose": f"Run and monitor the '{wf['name']}' process with its role-specific actions.",
                "key_components": ["DataTable", "WorkflowStepper", "ActionMenu", "StatusBadge"],
            }
        )

    screens = [
        {"name": "Login", "route": "/login", "purpose": "Authenticate users", "key_components": ["AuthForm", "BrandMark", "PasswordField"]},
        {"name": "Dashboard", "route": "/", "purpose": f"{domain['domain_label']} overview with KPIs and quick actions", "key_components": ["StatCard", "RecentList", "QuickActions"]},
        *entity_screens,
        {"name": "Detail view", "route": "/{resource}/:id", "purpose": "Full record with edit/delete", "key_components": ["DetailPanel", "ActionMenu"]},
        {"name": "Create/Edit form", "route": "/{resource}/new", "purpose": "Capture validated input", "key_components": ["FormShell", "Field", "SubmitButton"]},
        {"name": "Reports", "route": "/reports", "purpose": "Charts and exports for managers", "key_components": ["ChartCard", "ExportMenu", "DateRangePicker"]},
        {"name": "Settings", "route": "/settings", "purpose": "Profile and preferences", "key_components": ["Tabs", "ProfileForm", "DangerZone"]},
    ]

    nav_lines = ["flowchart TD"]
    nav_lines.append('    L["Login"] --> D["Dashboard"]')
    for i, screen in enumerate(entity_screens):
        nav_lines.append(f'    D --> W{i}["{screen["name"]}"]')
        nav_lines.append(f'    W{i} --> DET["Detail / Edit"]')
    nav_lines.append('    D --> R["Reports"]')
    nav_lines.append('    D --> S["Settings"]')

    user_journeys = [
        {
            "journey": wf["name"],
            "screens": ["Login", "Dashboard", wf["name"], "Detail view", "Create/Edit form"],
        }
        for wf in processes["workflows"]
    ]

    colors = {
        "primary": "#4F46E5 (Indigo 600)",
        "secondary": "#0F172A (Slate 900)",
        "accent": "#10B981 (Emerald 500)",
        "background": "#F8FAFC (Slate 50)",
        "text": "#1E293B (Slate 800)",
    }

    return {
        "design_principles": [
            "Progressive disclosure: show essentials first, detail on demand",
            "Consistent spacing scale and one accent color",
            "Optimistic UI with clear loading and empty states",
            f"Role-aware surfaces: each {domain['domain_label']} role sees only its workflows",
            "Accessible by default: keyboard navigation and ARIA labels",
        ],
        "screens": screens,
        "navigation_flow": "\n".join(nav_lines),
        "components": [
            {"name": "AppShell", "purpose": "Sidebar + topbar + content frame", "props": ["navItems", "user"]},
            {"name": "StatCard", "purpose": "KPI metric display", "props": ["label", "value", "trend", "icon"]},
            {"name": "DataTable", "purpose": "Sortable/filterable table", "props": ["columns", "rows", "loading"]},
            {"name": "WorkflowStepper", "purpose": "Visual progress through process steps", "props": ["steps", "current"]},
            {"name": "StatusBadge", "purpose": "Domain status colors", "props": ["status"]},
            {"name": "Modal", "purpose": "Focused dialogs", "props": ["open", "title", "children"]},
            {"name": "Toast", "purpose": "Transient feedback", "props": ["variant", "message"]},
            {"name": "FormField", "purpose": "Labeled input with validation", "props": ["label", "error", "hint"]},
            {"name": "EmptyState", "purpose": "Empty list guidance", "props": ["title", "action"]},
            {"name": "ConfirmDialog", "purpose": "Destructive action confirmation", "props": ["title", "onConfirm"]},
        ],
        "forms": [
            {
                "name": "Auth forms",
                "fields": [
                    {"name": "email", "type": "email", "validation": "required, valid email"},
                    {"name": "password", "type": "password", "validation": "required, min 8 chars"},
                ],
            },
            {
                "name": "Entity form",
                "fields": [
                    {"name": "name", "type": "text", "validation": "required, max 200"},
                    {"name": "description", "type": "textarea", "validation": "optional, max 2000"},
                    {"name": "status", "type": "select", "validation": "one of allowed enum"},
                ],
            },
            {
                "name": "Workflow form",
                "fields": [
                    {"name": "workflow", "type": "select", "validation": "one of the modeled workflows"},
                    {"name": "parameters", "type": "json", "validation": "valid JSON per workflow schema"},
                ],
            },
        ],
        "tables": [
            {
                "name": "Resource table",
                "columns": ["Name", "Status", "Owner", "Updated at", "Actions"],
                "features": ["Server-side pagination", "Search + column filters", "Row selection for bulk actions"],
            }
        ],
        "dashboard_layout": (
            "Top KPI row (4 stat cards) -> primary content grid (main workflow table 2/3, activity feed 1/3) -> "
            "secondary row (chart + quick actions). Stacks vertically below 1024px."
        ),
        "responsive_strategy": "Mobile-first; sidebar collapses to a drawer, tables scroll horizontally, forms go single-column.",
        "colors": colors,
        "typography": {"font_family": "Inter", "headings": "600/700 weight, tight tracking", "body": "400 weight, 1.5 line height"},
        "reusable_components": ["Button", "Input", "Select", "Badge", "Table", "Card", "Tabs", "Avatar", "Spinner", "EmptyState", "ConfirmDialog", "WorkflowStepper"],
        "user_journeys": user_journeys,
    }


# ---------------------------------------------------------------------------
# 9. Roadmap
# ---------------------------------------------------------------------------

def _roadmap(input_data: dict[str, Any], analysis: dict[str, Any]) -> dict[str, Any]:
    complexity = analysis["complexity_score"]["level"]
    weeks = 4 if complexity == "Low" else 6 if complexity == "Medium" else 8
    base_hours = 90 if complexity == "Low" else 150 if complexity == "Medium" else 230

    themes = [
        ("Planning, domain model & architecture", [
            "Write PRD and acceptance criteria",
            "Freeze the domain model and business rules",
            "Define architecture and data model",
            "Set up repo, CI and environments",
            "Create database schema + migrations",
            "Bootstrap backend and frontend projects",
        ]),
        ("Authentication & core backend", [
            f"Implement {input_data['auth_method']} auth flow",
            "Role-based access control",
            "Core domain CRUD APIs",
            "Workflow endpoints and business rules",
            "Validation, error handling and audit logs",
            "Unit tests for services",
        ]),
        ("Frontend & integration", [
            "App shell, navigation and routing",
            "Auth screens and guards",
            "Workflow screens (list/detail/form)",
            "Dashboard and reports",
            "Connect API client layer",
            "End-to-end integration tests",
        ]),
        ("Testing, hardening & deployment", [
            "API and security tests",
            "Performance pass and edge cases",
            "Seed data and documentation",
            "Docker + CI/CD pipeline",
            f"Deploy to {input_data['deployment_platform']}",
            "Stakeholder demo and release notes",
        ]),
    ]
    if weeks > 4:
        themes = themes[:2] + [
            ("Advanced features & reporting", [
                "Reporting and analytics endpoints",
                "Search, filters and export",
                "Notification flows",
                "Admin screens",
                "QA regression pass",
            ]),
        ] + themes[2:]
    if weeks > 6:
        themes = themes[:2] + [
            ("Advanced features & reporting", [
                "Reporting and analytics endpoints",
                "Search, filters and export",
                "Notification flows",
                "Admin screens",
                "QA regression pass",
            ]),
        ] + themes[2:4] + [
            ("Hardening & performance", [
                "Load testing and tuning",
                "Caching and query optimization",
                "Security review and fixes",
                "Disaster recovery drills",
            ]),
        ] + themes[4:]

    hours_per_week = int(base_hours / len(themes)) + 5
    milestones = []
    for idx, (theme, tasks) in enumerate(themes, start=1):
        tasks_payload = [{"task": t, "hours": max(3, hours_per_week // len(tasks) - idx), "deliverable": t} for t in tasks]
        week_hours = sum(t["hours"] for t in tasks_payload)
        milestones.append(
            {
                "week": idx,
                "theme": theme,
                "tasks": tasks_payload,
                "week_hours": week_hours,
                "goal": f"Complete: {theme.lower()}",
            }
        )

    return {
        "summary": (
            f"A {len(themes)}-week roadmap (~{sum(m['week_hours'] for m in milestones)} hours) sized from the "
            f"complexity score ({complexity}). Vertical slices with continuous testing; the domain model is "
            f"frozen before feature work starts."
        ),
        "total_estimated_hours": sum(m["week_hours"] for m in milestones),
        "weekly_milestones": milestones,
        "critical_path": ["Requirements freeze", "Domain model & business rules", "Database schema", "Authentication", "Core CRUD + workflow APIs", "Frontend integration", "Release hardening"],
        "team_plan": [
            {"role": "Full-stack engineer", "focus": "Vertical slices end-to-end"},
            {"role": "QA engineer", "focus": "Test strategy, automation, release sign-off"},
            {"role": "Product owner", "focus": "Requirements, acceptance criteria, stakeholder demos"},
        ],
    }


# ---------------------------------------------------------------------------
# 10. Testing
# ---------------------------------------------------------------------------

def _testing(
    input_data: dict[str, Any],
    db_section: dict[str, Any],
    api_section: dict[str, Any],
) -> dict[str, Any]:
    endpoints = [e for e in api_section["endpoints"] if not e["path"].startswith("/auth")]
    sample_paths = [e["path"] for e in endpoints[:3]]
    rule_count = len(db_section.get("data_integrity_rules", []))
    return {
        "summary": (
            "A pragmatic pyramid: many fast unit tests, fewer integration tests, and a thin set of "
            "end-to-end tests. API tests cover the documented endpoints; integrity tests verify the "
            "business rules encoded in the schema."
        ),
        "unit_tests": [
            {"name": "test_auth_register", "target": "AuthService.register", "scenario": "Valid input creates user; duplicate email raises conflict."},
            {"name": "test_auth_login", "target": "AuthService.login", "scenario": "Correct password returns token; wrong password rejected."},
            {"name": "test_service_validation", "target": "DomainService.create", "scenario": "Invalid payload rejected with field-level errors."},
            {"name": "test_money_math", "target": "Pricing module", "scenario": "Totals computed without floating point drift."},
            {"name": "test_business_rules", "target": "WorkflowService", "scenario": f"Every one of the {rule_count} modeled business rules is enforced."},
            {"name": "test_repository_filters", "target": "Repository.list", "scenario": "Pagination + filters return expected slices."},
        ],
        "integration_tests": [
            {"name": "test_registration_flow", "flow": "register -> login -> me", "scenario": "Full auth journey against the real database."},
            {"name": "test_crud_lifecycle", "flow": "create -> read -> update -> delete", "scenario": "Resource lifecycle persists correctly."},
            {"name": "test_workflow_execution", "flow": "workflow start -> step -> completion", "scenario": "Workflow endpoints advance state and enforce rules in order."},
            {"name": "test_migration_smoke", "flow": "migrate -> seed -> query", "scenario": "Migrations and seed data apply cleanly on a fresh database."},
        ],
        "api_tests": [
            {"name": "api_auth_flow", "endpoint": "/auth/*", "method": "POST", "scenario": "Register/login/me return documented status codes."},
            *[
                {"name": "api_resource", "endpoint": path, "method": "GET/POST/PUT/DELETE", "scenario": "Happy path + 401 without token + 422 on bad payload."}
                for path in sample_paths
            ],
            {"name": "api_pagination", "endpoint": "/{resource}", "method": "GET", "scenario": "Page bounds respected; page_size capped."},
        ],
        "security_tests": [
            {"name": "jwt_expiry", "threat": "Replay of expired tokens", "scenario": "Expired token returns 401; refresh rotates tokens."},
            {"name": "injection_probe", "threat": "SQL / NoSQL injection", "scenario": "Malicious strings in filters are neutralized by parameterization."},
            {"name": "privacy_leak", "threat": "Horizontal privilege escalation", "scenario": "User A cannot read/update User B resources."},
            {"name": "rate_limit", "threat": "Credential stuffing", "scenario": "Login endpoint throttled after N failures."},
        ],
        "performance_tests": [
            {"name": "api_p95", "metric": "p95 latency", "threshold": "< 500ms on 50 RPS", "scenario": "k6 load test on read endpoints."},
            {"name": "list_scalability", "metric": "query time", "threshold": "< 300ms with 1M rows", "scenario": "Index verification on the largest tables."},
            {"name": "frontend_lcp", "metric": "Largest Contentful Paint", "threshold": "< 2.5s", "scenario": "Lighthouse budget on dashboard route."},
        ],
        "edge_cases": [
            {"name": "empty_collections", "scenario": "Every list view renders a helpful empty state."},
            {"name": "duplicate_submit", "scenario": "Double-click submit creates exactly one record."},
            {"name": "unicode_names", "scenario": "Non-ASCII names and text survive round-trips."},
            {"name": "concurrent_edits", "scenario": "Last-write-wins with optimistic locking warning."},
            {"name": "rule_violations", "scenario": "Every business rule returns a 400 with a machine-readable code."},
        ],
        "test_data": (
            "Deterministic seed: 1 admin + 3 members, sample domain records, unique emails. "
            "Faker-based factories for load and scale tests."
        ),
        "qa_checklist": [
            "All listed screens render with empty, loading, error and populated states",
            "No unhandled 5xx on any documented endpoint",
            "RBAC matrix verified for every role",
            "All workflow steps reachable from the UI for each role",
            "Accessibility: keyboard navigation on all primary flows",
            "Responsive: 375px, 768px, 1440px breakpoints pass",
            "Documentation matches shipped behavior",
        ],
    }


# ---------------------------------------------------------------------------
# 11. Documentation
# ---------------------------------------------------------------------------

def _documentation(input_data: dict[str, Any], blueprint: dict[str, Any]) -> dict[str, Any]:
    """Documentation generator — the README is assembled entirely from the
    Domain Context and the blueprint sections, never from static templates."""
    name = input_data["name"]
    fe, be, db = input_data["preferred_frontend"], input_data["preferred_backend"], input_data["database"]
    ctx = _resolve_ctx(input_data, blueprint.get("domain_context"))
    domain = blueprint["domain_understanding"]
    analysis = blueprint.get("analysis", {})
    architecture = blueprint.get("architecture", {})
    business_processes = blueprint.get("business_processes", {})
    modules = ctx["module_names"] or [wf.get("name") for wf in business_processes.get("workflows", [])]

    objectives = [str(o) for o in analysis.get("objectives", [])][:4]
    problem = analysis.get("problem_statement") or (
        f"{name} is built to solve a focused business problem in the {domain.get('domain_label', '')} domain."
    )

    stack_rows = "\n".join(
        f"| {fe} | {templates._frontend(fe)['why']} |\n"
        f"| {be} | {templates._backend(be)['why']} |\n"
        f"| {db} | {templates._db(db)['why']} |\n"
        f"| {input_data['auth_method']} | {templates._auth(input_data['auth_method'])['why']} |\n"
        f"| {input_data['deployment_platform']} | {templates._deploy(input_data['deployment_platform'])['why']} |"
    )

    architecture_summary = architecture.get("summary") or (
        f"A layered web architecture: a {fe} client backed by a stateless {be} REST API on {db}."
    )
    future_scope = domain.get("future_expansion", []) or blueprint.get("documentation", {}).get("future_improvements", [])

    readme = f"""# {name}

> {domain.get('domain_label', '')} · {input_data['category']}

## Business Overview

**Business problem**

{problem}

**Objectives**

""" + "".join(f"- {o}\n" for o in objectives) + f"""
**Primary users**

{", ".join(domain.get('primary_users', []))}

## Technology Stack

| Layer | Choice | Why |
|-------|--------|-----|
{stack_rows}

## Architecture Summary

{architecture_summary}

## Key Modules

""" + "".join(f"- {m}\n" for m in modules) + f"""
## Deployment

Containerized via Docker and deployed to {input_data['deployment_platform']}, with
monitoring via Sentry + Prometheus/Grafana and structured JSON logging.

## Future Scope

""" + "".join(f"- {item}\n" for item in future_scope) + """
## Quick start

```bash
cp .env.example .env
docker compose up -d
# backend: http://localhost:8010/docs   frontend: http://localhost:3010
```

## Repository layout

```
backend/    API service (controllers -> services -> repositories)
frontend/   Web client
database/   Migrations and seed data
docs/       Architecture, API, database and deployment docs
```

## Documentation

- [Architecture](docs/architecture.md)
- [API reference](docs/api.md)
- [Database design](docs/database.md)
- [Deployment guide](docs/deployment.md)
"""
    installation = (
        "## Installation\n\n### Prerequisites\n- Python 3.13+, Node 22+, Docker (optional)\n\n"
        "### 1. Backend\n```bash\ncd backend\npython -m venv .venv\nsource .venv/bin/activate  # Windows: .venv\\Scripts\\activate\npip install -r requirements.txt\nuvicorn app.main:app --reload\n```\n"
        "### 2. Frontend\n```bash\ncd frontend\nnpm install\ncp .env.local.example .env.local\nnpm run dev\n```\n"
        "### 3. Verify\nOpen http://localhost:8010/docs (Swagger) and http://localhost:3010."
    )
    return {
        "readme": readme,
        "installation_guide": installation,
        "api_documentation": f"See the API section of the blueprint: {len(blueprint['api']['endpoints'])} endpoints documented with request/response examples, validation rules, status codes and a business-workflow mapping. Interactive docs available via the framework's OpenAPI UI.",
        "architecture_documentation": "Layered architecture (controller -> service -> repository) with a stateless API, documented component/data-flow diagrams, deployment topology and the design decisions that led to the shape.",
        "database_documentation": f"Normalized {db} schema derived from the {domain['domain_label']} entity model, with ERD, FK/CHECK constraints, indexes, normalization notes per table and a migration strategy (Alembic/Flyway/Knex).",
        "deployment_guide": f"Containerized via Docker, deployed to {input_data['deployment_platform']}, monitored with Sentry + Prometheus/Grafana, logging via structured JSON.",
        "contribution_guide": "1) Fork and branch from main. 2) Run lint + tests locally. 3) Open a PR with a clear description. 4) CI must pass; changes to API schemas require updated docs.",
        "future_improvements": domain["future_expansion"]
        + [
            "Real-time features via WebSockets (notifications, presence)",
            "Multi-tenancy and workspace isolation",
            "Mobile app (React Native / PWA)",
        ],
    }


# ---------------------------------------------------------------------------
# Cross-validation (delegates to V3 quality review)
# ---------------------------------------------------------------------------

def validate_blueprint(blueprint: dict[str, Any]) -> dict[str, Any]:
    """Backward-compatible wrapper around the V3 quality review."""
    return v3_architect.quality_review(blueprint)


# ---------------------------------------------------------------------------
# Assembly
# ---------------------------------------------------------------------------

SECTIONS = [
    "analysis",
    "domain_understanding",
    "business_processes",
    "technology_selection",
    "architecture",
    "database",
    "api",
    "ui_ux",
    "roadmap",
    "testing",
    "documentation",
]


def fallback_section(section: str, input_data: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    """Deterministic per-section fallback for the agent pipeline.

    ``state`` holds the sections produced by prior agents (pipeline order).
    """
    input_data = _normalize_project_input(input_data)
    ctx = _resolve_ctx(input_data, state.get("domain_context"))
    if section == "analysis":
        return _analysis(input_data, ctx)
    if section == "domain_understanding":
        return _domain_understanding(input_data, state.get("analysis", {}), ctx)
    if section == "business_processes":
        return _business_processes(input_data, state.get("domain_understanding", {}), ctx)
    if section == "technology_selection":
        return _technology_selection(
            input_data, state.get("domain_understanding", {}), state.get("analysis", {})
        )
    if section == "technology_evaluation":
        return v3_architect.technology_evaluation(input_data)
    if section == "design_decisions":
        return v3_architect.design_decisions(input_data)
    if section == "tradeoffs":
        return v3_architect.tradeoff_analysis(input_data)
    if section == "architecture":
        return _architecture(
            input_data,
            state.get("domain_understanding", {}),
            state.get("technology_selection", {}),
            state.get("analysis", {}),
        )
    if section == "database":
        return _database(input_data, state.get("domain_understanding", {}), ctx)
    if section == "api":
        return _api(
            input_data,
            state.get("database", {}),
            state.get("domain_understanding", {}),
            state.get("business_processes", {}),
        )
    if section == "ui_ux":
        return _ui_ux(input_data, state.get("domain_understanding", {}), state.get("business_processes", {}))
    if section == "security":
        return v3_architect.security_review(input_data, state)
    if section == "performance":
        return v3_architect.performance_review(input_data, state)
    if section == "scalability":
        return v3_architect.scalability_planning(input_data, state)
    if section == "cost_estimation":
        return v3_architect.cost_estimation(input_data, state)
    if section == "business_risks":
        return v3_architect.business_risk_analysis(input_data, state)
    if section == "roadmap":
        return _roadmap(input_data, state.get("analysis", {}))
    if section == "product_evolution":
        return v3_architect.product_evolution(input_data, state)
    if section == "adr":
        return v3_architect.adr_records(input_data, state)
    if section == "testing":
        return _testing(input_data, state.get("database", {}), state.get("api", {}))
    if section == "documentation":
        return _documentation(
            input_data,
            blueprint={
                "api": state.get("api", {}),
                "database": state.get("database", {}),
                "domain_understanding": state.get("domain_understanding", {}),
                "analysis": state.get("analysis", {}),
                "architecture": state.get("architecture", {}),
                "business_processes": state.get("business_processes", {}),
                "domain_context": ctx,
            },
        )
    if section == "validation":
        # The validation is computed at the end; use the quality_review on the assembled blueprint
        blueprint = {k: state.get(k) for k in state if k != "validation"}
        return v3_architect.quality_review(blueprint)
    raise KeyError(f"Unknown blueprint section: {section}")


def generate_blueprint(input_data: dict[str, Any]) -> dict[str, Any]:
    """Deterministically generate the full V3 blueprint from wizard input.

    A Domain Context object is built once from the input and consumed by every
    section builder, so the whole blueprint stays domain-consistent and fully
    isolated from previous generations.
    """
    input_data = _normalize_project_input(input_data)
    ctx = build_domain_context(input_data)
    analysis = _analysis(input_data, ctx)
    domain = _domain_understanding(input_data, analysis, ctx)
    processes = _business_processes(input_data, domain, ctx)
    tech = _technology_selection(input_data, domain, analysis)
    architecture = _architecture(input_data, domain, tech, analysis)
    database = _database(input_data, domain, ctx)
    api = _api(input_data, database, domain, processes)
    ui_ux = _ui_ux(input_data, domain, processes)
    roadmap = _roadmap(input_data, analysis)
    testing = _testing(input_data, database, api)
    documentation = _documentation(
        input_data,
        blueprint={
            "api": api,
            "database": database,
            "domain_understanding": domain,
            "analysis": analysis,
            "architecture": architecture,
            "business_processes": processes,
            "domain_context": ctx,
        },
    )

    # V3 additional sections
    tech_eval = v3_architect.technology_evaluation(input_data)
    design = v3_architect.design_decisions(input_data)
    tradeoffs = v3_architect.tradeoff_analysis(input_data)
    security = v3_architect.security_review(input_data, {})
    performance = v3_architect.performance_review(input_data, {})
    scalability = v3_architect.scalability_planning(input_data, {})
    cost = v3_architect.cost_estimation(input_data, {})
    risks = v3_architect.business_risk_analysis(input_data, {})
    evolution = v3_architect.product_evolution(input_data, {})

    partial = {
        "analysis": analysis,
        "domain_understanding": domain,
        "business_processes": processes,
        "technology_selection": tech,
        "technology_evaluation": tech_eval,
        "design_decisions": design,
        "tradeoffs": tradeoffs,
        "architecture": architecture,
        "database": database,
        "api": api,
        "ui_ux": ui_ux,
        "roadmap": roadmap,
        "product_evolution": evolution,
        "testing": testing,
        "documentation": documentation,
        "deployment": templates._deployment(input_data),
        "security": security,
        "performance": performance,
        "scalability": scalability,
        "cost_estimation": cost,
        "business_risks": risks,
    }

    # ADR needs design_decisions from the partial blueprint
    adr = v3_architect.adr_records(input_data, partial)
    partial["adr"] = adr

    # The Domain Context travels with the blueprint so the Blueprint Review
    # agent and the semantic consistency checker can audit every section.
    partial["metadata"] = {"domain_context": ctx}

    # Compute validation/quality review on the assembled blueprint
    validation = v3_architect.quality_review(partial)
    partial["validation"] = validation

    return partial
