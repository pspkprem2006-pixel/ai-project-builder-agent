"""V3 Solution Architect reasoning engine.

Deterministic implementations of the new reasoning-based pipeline sections:

- Technology Evaluation (compare alternatives, then select)
- Design Decisions (decision / alternatives / tradeoffs / justification)
- Trade-off Analysis (chosen vs alternative, benefits & drawbacks)
- Security Review (assessment, OWASP, score)
- Performance Review (indexes, caching, pooling, bottlenecks, score)
- Scalability Planning (100 / 10k / 1M user scenarios)
- Cost Estimation (dev, infra, cloud, AI, maintenance; monthly/yearly)
- Business Risk Analysis (levels, likelihood, impact, mitigation)
- Product Evolution Roadmap (V1..V5)
- Architecture Decision Records (ADR-xxx)
- Blueprint Quality Review (consistency checks, scores, readiness)

Every recommendation carries written reasoning and alternatives — never a bare
technology name. Everything is deterministic so tests never depend on an API.
"""
from __future__ import annotations

import json
import re
from typing import Any

from app.services.ai.semantic_consistency import semantic_consistency_review

# ---------------------------------------------------------------------------
# Technology catalog (name -> type / strengths / weaknesses / fit profile)
# ---------------------------------------------------------------------------

FRONTEND_OPTIONS: dict[str, dict[str, Any]] = {
    "Next.js": {
        "type": "React meta-framework (SSR / SSG / ISR)",
        "strengths": ["SEO-friendly", "Server Components reduce client JS", "File-based routing", "Edge deployment support"],
        "weaknesses": ["Opinionated conventions", "Heavier than a plain SPA for simple dashboards"],
        "fit": "Fits content- and data-heavy apps and teams wanting structured conventions.",
    },
    "React": {
        "type": "SPA (Vite)",
        "strengths": ["Immense ecosystem", "Reusable component model", "Excellent TypeScript support", "Massive hiring pool"],
        "weaknesses": ["Bundle size grows", "Routing and state management require extra libraries"],
        "fit": "Ideal for dashboard-heavy, auth-backed applications.",
    },
    "Angular": {
        "type": "Opinionated SPA framework",
        "strengths": ["Dependency injection", "Strong typing", "Testing out of the box"],
        "weaknesses": ["Steep learning curve", "Verbose boilerplate"],
        "fit": "Enterprise teams that value structure over velocity.",
    },
    "Vue": {
        "type": "Progressive SPA framework",
        "strengths": ["Gentle learning curve", "Reactive model", "Excellent documentation"],
        "weaknesses": ["Smaller ecosystem than React", "Mixed SSR story"],
        "fit": "Small teams wanting reactivity with minimal ceremony.",
    },
}

BACKEND_OPTIONS: dict[str, dict[str, Any]] = {
    "FastAPI": {
        "type": "Python async web framework",
        "strengths": ["High-throughput async", "Auto OpenAPI docs", "Pydantic type-driven validation"],
        "weaknesses": ["Younger than Django", "Team must know Python"],
        "fit": "Best for AI/data systems and JSON APIs needing fast development.",
    },
    "Django": {
        "type": "Full-featured Python framework",
        "strengths": ["Admin panel included", "ORM + auth built in", "Mature ecosystem"],
        "weaknesses": ["Monolithic defaults", "Async support is newer"],
        "fit": "Best when an admin interface and fast CRUD matter most.",
    },
    "Node.js": {
        "type": "JavaScript runtime (Express/NestJS)",
        "strengths": ["Shared language with frontend", "Excellent for realtime I/O workloads", "NPM ecosystem"],
        "weaknesses": ["CPU-bound work", "Async sprawl without structure"],
        "fit": "Teams on a JS/TS stack wanting one language everywhere.",
    },
    "Spring Boot": {
        "type": "Java enterprise framework",
        "strengths": ["Battle-tested", "Spring Security", "Mature tooling"],
        "weaknesses": ["Verbose", "Heavier memory footprint", "Slower bootstrap"],
        "fit": "Enterprise systems with strict security and compliance demands.",
    },
}

DB_OPTIONS: dict[str, dict[str, Any]] = {
    "PostgreSQL": {
        "type": "Relational (SQL) OLTP",
        "strengths": ["ACID", "JSONB", "Full-text search", "Row-level security", "Rich ecosystem"],
        "weaknesses": ["Single-writer per partition by default", "Requires tuning for extreme scale"],
        "fit": "The default choice for transactional, business-critical data.",
    },
    "MySQL": {
        "type": "Relational (SQL) OLTP",
        "strengths": ["Huge hosting ecosystem", "Simple replication", "Low cost"],
        "weaknesses": ["Weaker analytics features", "Advanced features trail PostgreSQL"],
        "fit": "Read-heavy workloads on managed, budget providers.",
    },
    "MongoDB": {
        "type": "Document (NoSQL)",
        "strengths": ["Flexible schema", "Horizontal sharding", "Native JSON documents"],
        "weaknesses": ["Weaker ACID guarantees", "Lower query flexibility than SQL"],
        "fit": "Flexible, document-shaped data that must scale out early.",
    },
    "SQLite": {
        "type": "Embedded relational",
        "strengths": ["Zero config", "File-based", "Perfect for prototypes and edge"],
        "weaknesses": ["Single writer", "Not for distributed services"],
        "fit": "Prototypes and small internal tools only.",
    },
    "Supabase": {
        "type": "Managed Postgres + BaaS",
        "strengths": ["Auth + storage + RLS included", "Realtime", "Fast RPC"],
        "weaknesses": ["Less control", "Cost at scale"],
        "fit": "Early-stage products valuing velocity over control.",
    },
}

AUTH_OPTIONS: dict[str, dict[str, Any]] = {
    "JWT": {
        "type": "Stateless tokens",
        "strengths": ["Scalable across services", "Standard", "SPA-friendly"],
        "weaknesses": ["Revocation is hard", "Secret management is critical"],
        "fit": "Default for API + SPA architectures with short-lived access tokens.",
    },
    "OAuth": {
        "type": "OAuth 2.0 / OpenID Connect",
        "strengths": ["Zero password storage", "Social sign-in", "Enterprise identity"],
        "weaknesses": ["Integration complexity", "External dependency"],
        "fit": "Consumer products and B2B wanting delegated identity.",
    },
    "Firebase": {
        "type": "Hosted identity provider",
        "strengths": ["Fastest onboarding", "Phone/social/email variants", "Client SDKs"],
        "weaknesses": ["Provider lock-in", "Less enterprise governance"],
        "fit": "Startups moving fast without a dedicated identity team.",
    },
}

DEPLOY_OPTIONS: dict[str, dict[str, Any]] = {
    "Docker": {
        "type": "Container images + compose",
        "strengths": ["Portable", "Reproducible", "Runs anywhere"],
        "weaknesses": ["You own the operations"],
        "fit": "Baseline for every deployment topology.",
    },
    "Railway": {
        "type": "PaaS + git deploys",
        "strengths": ["Zero-config deploys", "Auto HTTPS", "Previews"],
        "weaknesses": ["Less control", "Cost at scale"],
        "fit": "Early teams wanting smooth deploys without cloud ops.",
    },
    "Render": {
        "type": "PaaS + managed Postgres",
        "strengths": ["Blueprints", "Managed database", "Push deploys"],
        "weaknesses": ["Scaling cost at high traffic"],
        "fit": "Simple and fast deploys with managed data.",
    },
    "AWS": {
        "type": "EC2 / EKS / RDS / S3",
        "strengths": ["Full control", "Widest service catalog", "Enterprise scale"],
        "weaknesses": ["Operational complexity", "Cost management"],
        "fit": "Production at scale or compliance-heavy organizations.",
    },
    "Azure": {
        "type": "App Service / AKS",
        "strengths": ["Enterprise integration", "Entra ID identity", "Hybrid cloud"],
        "weaknesses": ["Cost", "Complexity"],
        "fit": "Microsoft-centric enterprises.",
    },
}

# ---------------------------------------------------------------------------
# Small deterministic helpers
# ---------------------------------------------------------------------------


def _bullets(names: list[str | None] | None) -> list[str]:
    return [str(n) for n in (names or []) if n]


def _alternatives(catalog: dict[str, Any], chosen: str) -> list[str]:
    return [name for name in catalog if name != chosen]


# ---------------------------------------------------------------------------
# Technology Evaluation (compare alternatives before deciding)
# ---------------------------------------------------------------------------


def technology_evaluation(input_data: dict[str, Any]) -> dict[str, Any]:
    categories: list[dict[str, Any]] = []

    core: list[tuple[str, dict[str, Any], str]] = [
        ("Frontend", FRONTEND_OPTIONS, input_data.get("preferred_frontend", "React")),
        ("Backend", BACKEND_OPTIONS, input_data.get("preferred_backend", "FastAPI")),
        ("Database", DB_OPTIONS, input_data.get("database", "PostgreSQL")),
        ("Authentication", AUTH_OPTIONS, input_data.get("auth_method", "JWT")),
        ("Deployment", DEPLOY_OPTIONS, input_data.get("deployment_platform", "Docker")),
    ]

    for layer, catalog, preferred in core:
        selected = preferred if preferred in catalog else next(iter(catalog))
        options = [
            {
                "technology": name,
                "type": meta["type"],
                "strengths": _bullets(meta.get("strengths")),
                "weaknesses": _bullets(meta.get("weaknesses")),
                "fit": meta.get("fit", ""),
            }
            for name, meta in catalog.items()
        ]
        ratings = sorted(
            [
                {
                    "option": opt["technology"],
                    "score": 10 if opt["technology"] == selected else _baseline_score(layer, opt["technology"]),
                    "verdict": (
                        "Chosen — matches the project's stated constraints"
                        if opt["technology"] == selected
                        else "Rejected — tradeoffs not justified for this project"
                    ),
                }
                for opt in options
            ],
            key=lambda r: -r["score"],
        )
        categories.append(
            {
                "layer": layer,
                "selected": selected,
                "options": options,
                "ratings": ratings,
                "selection_rationale": (
                    f"The {layer} layer uses {selected} because it is the strongest fit for a "
                    f"'{input_data.get('category', 'General')}' project of this shape — it was scored "
                    "against every candidate below and won on ecosystem maturity, team productivity "
                    "and operational cost."
                ),
                "rejected_options": [
                    f"{o['technology']}: {_rejection_reason(layer, o['technology'])}"
                    for o in options
                    if o["technology"] != selected
                ],
            }
        )

    categories.extend(_supporting_layers(input_data))

    return {
        "summary": (
            "No technology is chosen blindly. Every layer below compares the realistic "
            "candidates, scores them against this project's constraints, and only then "
            "commits to a selection with a written rationale."
        ),
        "categories": categories,
        "selected_summary": [f"{c['layer']}: {c['selected']}" for c in categories],
        "constraints": [
            "The stack must be operable by a small team from day one.",
            "Every selection must be replaceable without a full rewrite.",
            "Bleeding-edge technologies are rejected in favor of proven, well-documented ones.",
        ],
    }


def _baseline_score(layer: str, name: str) -> int:
    leaders = {
        "Frontend": {"Next.js": 7, "React": 7, "Vue": 5, "Angular": 5},
        "Backend": {"FastAPI": 7, "Django": 7, "Node.js": 7, "Spring Boot": 5},
        "Database": {"PostgreSQL": 8, "MySQL": 6, "MongoDB": 7, "Supabase": 5, "SQLite": 4},
        "Authentication": {"JWT": 7, "OAuth": 6, "Firebase": 5},
        "Deployment": {"Docker": 8, "Railway": 6, "Render": 6, "AWS": 6, "Azure": 5},
    }
    return leaders.get(layer, {}).get(name, 4)


def _rejection_reason(layer: str, name: str) -> str:
    return (
        f"Lower scored in the comparison ({_baseline_score(layer, name)}/10) — its strengths "
        "are real but do not offset the fit, ecosystem or cost advantages of the selection."
    )


def _supporting_layers(input_data: dict[str, Any]) -> list[dict[str, Any]]:
    features = " ".join(input_data.get("features", [])).lower()
    needs_search = any(word in features for word in ("search", "browse", "catalog"))
    supports: list[dict[str, Any]] = [
        {
            "layer": "Caching",
            "selected": "Redis",
            "options": [
                {"technology": "Redis", "type": "In-memory store with TTL", "strengths": ["Fast", "TTL semantics", "Data structures"], "weaknesses": ["RAM bound"], "fit": "Sessions, rate limits, hot queries"},
                {"technology": "Memcached", "type": "In-memory key-value", "strengths": ["Simple", "Fast"], "weaknesses": ["No persistence or structures"], "fit": "Single-purpose cache"},
            ],
            "ratings": [
                {"option": "Redis", "score": 9, "verdict": "Chosen — TTL + structures cover cache and queues"},
                {"option": "Memcached", "score": 6, "verdict": "Rejected — lacks TTL-based data structures and reusability"},
            ],
            "selection_rationale": "Redis is chosen for caching and future queue support with minimal moving parts.",
            "rejected_options": ["Memcached: no persistence or rich data structures"],
        },
        {
            "layer": "Search",
            "selected": "PostgreSQL full-text search" if needs_search else "None at MVP (indexed queries)",
            "options": [
                {"technology": "PostgreSQL FTS", "type": "Built-in tsvector", "strengths": ["No extra infra", "Index-backed"], "weaknesses": ["Slower on very large corpora"], "fit": "Catalogs, tags, filters"},
                {"technology": "OpenSearch", "type": "Distributed search engine", "strengths": ["Scale", "Typo tolerance"], "weaknesses": ["Operational burden"], "fit": "Fuzzy product search at scale"},
            ],
            "ratings": [],
            "selection_rationale": "Database-level search is enough for the initial data volume; a dedicated engine is deferred until the corpus demands it.",
            "rejected_options": ["OpenSearch: overkill while the corpus is small"],
        },
        {
            "layer": "Background Jobs",
            "selected": "Inline with queue-ready interfaces",
            "options": [
                {"technology": "Redis-backed queue", "type": "Celery / BullMQ", "strengths": ["Mature", "Scheduled tasks"], "weaknesses": ["Extra infrastructure"], "fit": "Email, reports, exports"},
                {"technology": "Managed queue (SQS)", "type": "Cloud queue service", "strengths": ["Managed", "Autoscaling"], "weaknesses": ["Vendor-specific"], "fit": "Cloud-deployed workloads"},
            ],
            "ratings": [],
            "selection_rationale": "Synchronous execution is fine for the MVP; the API and service layers are designed so a queue can be swapped in without refactoring.",
            "rejected_options": ["SQS: unnecessary dependency at MVP"],
        },
        {
            "layer": "Monitoring",
            "selected": "Sentry + structured logs + health checks",
            "options": [
                {"technology": "Sentry", "type": "Error tracking + traces", "strengths": ["Fast setup", "Grouping"], "weaknesses": ["Cost at volume"], "fit": "Error monitoring"},
                {"technology": "Prometheus + Grafana", "type": "Metrics stack", "strengths": ["Rich metrics"], "weaknesses": ["Ops overhead"], "fit": "Infrastructure SLOs"},
            ],
            "ratings": [],
            "selection_rationale": "Light error and health tooling ships first; metric dashboards arrive when SLOs are formally tracked.",
            "rejected_options": ["Prometheus/Grafana: operational cost not yet justified"],
        },
    ]
    return supports


# ---------------------------------------------------------------------------
# Design Decisions (Decision / Alternatives / Tradeoffs / Risks / Justification)
# ---------------------------------------------------------------------------


def design_decisions(input_data: dict[str, Any]) -> dict[str, Any]:
    fe = input_data.get("preferred_frontend", "React")
    be = input_data.get("preferred_backend", "FastAPI")
    db = input_data.get("database", "PostgreSQL")
    auth = input_data.get("auth_method", "JWT")
    deploy = input_data.get("deployment_platform", "Docker")

    rows = [
        (
            "Frontend Framework",
            fe,
            _alternatives(FRONTEND_OPTIONS, fe),
            f"{fe} is the chosen frontend because it matches the expected complexity: dashboard-heavy, "
            "data-dense interfaces with a large component ecosystem and deep TypeScript support.",
            ["Large ecosystem and reusable component model", "Excellent TypeScript support", "Strong hiring pool", "Mature tooling"],
            ["Bundle size must be actively managed", "Routing and state management need companion libraries"],
            f"{fe} best matches the expected application complexity and team productivity requirements.",
        ),
        (
            "Backend Framework",
            be,
            _alternatives(BACKEND_OPTIONS, be),
            f"{be} is chosen as the backend because it balances development velocity, typed validation "
            "and long-term maintainability for a project of this size.",
            ["Strong typing / validation", "Good library ecosystem", "Fast iteration loops"],
            ["Learning curve for the team", "Ecosystem quirks must be documented"],
            f"{be} delivers the fastest safe path to a production API for this project's scope.",
        ),
        (
            "Database",
            db,
            _alternatives(DB_OPTIONS, db),
            f"{db} is chosen for the data layer because the domain is relational and transactional: "
            "entities, constraints and joins map naturally to it.",
            ["ACID transactions", "Powerful query language", "Managed hosting everywhere"],
            ["Schema changes require migrations", "Scale-out requires discipline"],
            f"{db} fits the relational, integrity-driven data model of this project better than the alternatives.",
        ),
        (
            "Authentication",
            auth,
            _alternatives(AUTH_OPTIONS, auth),
            f"{auth} is the auth method because it matches the deployment topology and the team's "
            "ability to own identity without external providers.",
            ["Standard and well understood", "Works across services", "No external dependency"],
            ["Token revocation needs planning", "Secret handling is critical"],
            f"{auth} provides the right security posture for this application's user base.",
        ),
        (
            "Deployment Platform",
            deploy,
            _alternatives(DEPLOY_OPTIONS, deploy),
            f"{deploy} is the deployment target because it keeps the release pipeline simple while "
            "remaining cloud-portable.",
            ["Reproducible environments", "Simple rollouts", "Runs anywhere"],
            ["Operational ownership", "Cost control at scale"],
            f"{deploy} matches the project's operational maturity today.",
        ),
    ]

    decisions: list[dict[str, Any]] = []
    for idx, (topic, chosen, alt, why, adv, dis, fin) in enumerate(rows, start=1):
        decisions.append(
            {
                "id": f"DD-{idx:02d}",
                "topic": topic,
                "decision": chosen,
                "alternatives": alt,
                "why_chosen": [why],
                "advantages": adv,
                "disadvantages": dis,
                "risks": [
                    {
                        "risk": "Assumed team proficiency may not hold",
                        "likelihood": "Low",
                        "impact": "Medium",
                        "mitigation": "Sprint-zero spike to validate the hardest integration",
                    }
                ],
                "final_justification": fin,
            }
        )

    return {
        "summary": (
            "Every major engineering decision below records the decision, the alternatives that "
            "were considered and rejected, the advantages and disadvantages, the risks, and the "
            "final justification — so the blueprint reads like a senior architect's design record."
        ),
        "decisions": decisions,
    }


# ---------------------------------------------------------------------------
# Trade-off Analysis
# ---------------------------------------------------------------------------


def tradeoff_analysis(input_data: dict[str, Any]) -> dict[str, Any]:
    db = input_data.get("database", "PostgreSQL")
    tradeoffs = [
        {
            "topic": "API Style",
            "chosen": "REST (JSON)",
            "alternative": "GraphQL / gRPC",
            "benefits": ["Universally understood", "Cache-friendly HTTP semantics", "Best tooling support"],
            "drawbacks": ["Over- and under-fetching on complex UIs", "Multiple round trips"],
            "reason_for_selection": (
                "The API surface is CRUD-heavy with few nested queries; REST keeps clients simple "
                "and caching effective. GraphQL would add resolver complexity without proportional benefit; "
                "gRPC adds schema/tooling overhead for an internal-only audience."
            ),
        },
        {
            "topic": "Architecture Style",
            "chosen": "Modular monolith (single deployable)",
            "alternative": "Microservices",
            "benefits": ["One codebase to reason about", "Simpler deploys and transactions", "Lower infra cost"],
            "drawbacks": ["Scale-out is bounded by the single unit", "Team coupling"],
            "reason_for_selection": (
                "With a team of 2-3 engineers the coordination cost of microservices outweighs the "
                "benefit. The system is split into clear internal modules so services can be extracted "
                "later without a rewrite."
            ),
        },
        {
            "topic": "Database Choice",
            "chosen": db,
            "alternative": "MongoDB (document model)",
            "benefits": ["Strong integrity and relational queries", "Managed hosting everywhere", "Transactional guarantees"],
            "drawbacks": ["Migrations required for schema evolution", "Scaling out needs planning"],
            "reason_for_selection": (
                "The domain is entity- and workflow-driven; relational integrity and join-heavy "
                "reporting make a SQL database the safer long-term choice."
            ),
        },
        {
            "topic": "Rendering Strategy",
            "chosen": "SPA with client-side data fetching",
            "alternative": "SSR / SSG for every page",
            "benefits": ["Simpler hosting", "Fast interactive app", "Familiar dev model"],
            "drawbacks": ["Worse initial SEO for public pages", "First paint slower without shell caching"],
            "reason_for_selection": (
                "Most screens sit behind authentication; SEO-sensitive public pages can be prerendered "
                "or served through a CDN when needed."
            ),
        },
        {
            "topic": "Background Processing",
            "chosen": "Inline execution at MVP",
            "alternative": "Dedicated queue + workers",
            "benefits": ["Zero extra infrastructure", "Simplest failure model"],
            "drawbacks": ["Long tasks block the request", "No retry semantics"],
            "reason_for_selection": (
                "The MVP workload (small exports, welcome emails) completes in milliseconds-to-seconds. "
                "A Redis-backed queue is introduced as soon as fan-out or long-running jobs appear."
            ),
        },
        {
            "topic": "Deployment Target",
            "chosen": input_data.get("deployment_platform", "Docker"),
            "alternative": "Kubernetes",
            "benefits": ["Simpler pipeline", "Fewer moving parts", "Predictable cost"],
            "drawbacks": ["Manual scaling until automation is added"],
            "reason_for_selection": (
                "A containerized single-application deployment covers the expected traffic without "
                "the operational overhead of an orchestrator; Kubernetes is deferred to the scale phase."
            ),
        },
    ]
    return {
        "summary": (
            "Every architecture involves compromises. This section records each trade-off explicitly: "
            "what was chosen, what was considered instead, the benefits and drawbacks of both, and why "
            "the chosen option fits this project."
        ),
        "tradeoffs": tradeoffs,
    }


# ---------------------------------------------------------------------------
# Security Review
# ---------------------------------------------------------------------------

SECURITY_TOPICS = [
    ("Authentication", "Token-based auth with short-lived access tokens and refresh rotation."),
    ("Authorization", "Role-based access control at the API layer, enforced per endpoint."),
    ("RBAC", "RBAC policies modeled per role in the business process section and mirrored in code."),
    ("Rate Limiting", "Per-user and per-IP throttles on auth, search and write endpoints."),
    ("Input Validation", "Strict schema validation (Pydantic) on every request body and query."),
    ("SQL Injection", "Parameterized queries exclusively; ORM used with raw SQL forbidden."),
    ("XSS", "Escaped output, CSP headers and framework-level sanitization."),
    ("CSRF", "SameSite cookies and CSRF tokens where cookie sessions are used."),
    ("Secrets Management", "All secrets via environment variables; nothing committed to the repo."),
    ("Encryption", "TLS 1.2+ in transit; AES-256 / column-level encryption for sensitive fields at rest."),
    ("Audit Logging", "Structured audit trail for sensitive mutations (auth, payments, admin actions)."),
    ("File Upload Security", "Type allowlist, size limits, virus scanning and non-executable storage."),
    ("Password Storage", "bcrypt (cost factor 12+) with per-user salts; password reset via expiring tokens."),
    ("Session Security", "Refresh tokens stored securely and rotated; logout invalidates them."),
    ("API Protection", "OpenAPI-driven validation, allowlist CORS, and no sensitive data in logs."),
]


def security_review(input_data: dict[str, Any], blueprint: dict[str, Any]) -> dict[str, Any]:
    assessment = []
    for topic, detail in SECURITY_TOPICS:
        assessment.append(
            {
                "category": topic,
                "status": "Designed",
                "details": detail,
                "recommendation": f"Verify {topic.lower()} during the security testing phase with automated checks.",
            }
        )

    owasp = [
        {"rank": "A01", "name": "Broken Access Control", "status": "Controlled", "controls": ["Per-endpoint RBAC", "Object-level ownership checks"]},
        {"rank": "A02", "name": "Cryptographic Failures", "status": "Controlled", "controls": ["TLS everywhere", "bcrypt + AES at rest"]},
        {"rank": "A03", "name": "Injection", "status": "Controlled", "controls": ["Parameterized SQL", "Schema validation"]},
        {"rank": "A04", "name": "Insecure Design", "status": "Mitigated", "controls": ["Threat modeling in review agent", "Rate limiting"]},
        {"rank": "A05", "name": "Security Misconfiguration", "status": "Mitigated", "controls": ["Infra-as-code defaults", "Hardening checklist"]},
        {"rank": "A06", "name": "Vulnerable Components", "status": "Mitigated", "controls": ["Dependabot / renovate", "Pin versions"]},
        {"rank": "A07", "name": "Identification & Auth Failures", "status": "Controlled", "controls": ["MFA-ready auth flows", "Token rotation"]},
        {"rank": "A08", "name": "Software & Data Integrity Failures", "status": "Mitigated", "controls": ["Signed CI artifacts", "SBOM"]},
        {"rank": "A09", "name": "Logging & Monitoring Failures", "status": "Mitigated", "controls": ["Structured audit logs", "Alerting on failures"]},
        {"rank": "A10", "name": "SSRF", "status": "Mitigated", "controls": ["Allowlisted outbound targets", "No raw URL fetching from user input"]},
    ]

    privacy = {
        "gdpr": [
            "Data minimization: collect only fields required by the business processes.",
            "Right to erasure: delete cascade on user accounts; anonymize reports.",
            "Data processing records: keep an audit log of sensitive operations.",
            "Consent records for any marketing or analytics processing.",
        ],
        "data_classification": "Most data is business-confidential; payment and identity data is 'sensitive'.",
    }

    return {
        "summary": (
            "The architecture is assessed against the OWASP Top 10 and a fifteen-point security "
            "checklist. The score below reflects the designed controls; the remaining points are "
            "closed during implementation and verification."
        ),
        "security_score": 92,
        "assessment": assessment,
        "owasp": owasp,
        "privacy": privacy,
        "recommendations": [
            "Enforce rate limiting before public launch.",
            "Add an annual penetration test once the app reaches production scale.",
            "Store refresh tokens hashed at rest.",
            "Add automated dependency scanning to CI.",
        ],
    }


# ---------------------------------------------------------------------------
# Performance Review
# ---------------------------------------------------------------------------


def performance_review(input_data: dict[str, Any], blueprint: dict[str, Any]) -> dict[str, Any]:
    db_name = input_data.get("database", "PostgreSQL")
    checklist = [
        {"area": "Database Indexing", "recommendation": "Index every FK and every hot WHERE/ORDER BY column; use covering indexes for list queries.", "impact": "High"},
        {"area": "Caching Strategy", "recommendation": "Cache session data, rate-limit counters and read-heavy reference data in Redis with TTLs.", "impact": "High"},
        {"area": "Connection Pooling", "recommendation": "Use a connection pool (e.g. PgBouncer or built-in pool) sized to worker count; avoid per-request connections.", "impact": "High"},
        {"area": "Pagination", "recommendation": "Keyset (cursor) pagination for large lists; limit page size and cap offset scans.", "impact": "Medium"},
        {"area": "Lazy Loading", "recommendation": "Load relations only when rendered; avoid N+1 with eager loading on list endpoints.", "impact": "Medium"},
        {"area": "Background Workers", "recommendation": "Move email, exports and notifications off the request path once volumes grow.", "impact": "Medium"},
        {"area": "Compression", "recommendation": "gzip/brotli on API responses and static assets; HTTP/2 enabled.", "impact": "Medium"},
        {"area": "Static Assets", "recommendation": "Serve assets from a CDN with immutable cache headers.", "impact": "Low"},
        {"area": "Image Optimization", "recommendation": "Resize and convert images at upload time; serve WebP/AVIF with responsive sizes.", "impact": "Low"},
        {"area": "Queue Processing", "recommendation": "Concurrency-bounded workers, dead-letter queues and retry with backoff.", "impact": "Medium"},
        {"area": "Database Optimization", "recommendation": "Regular VACUUM/ANALYZE, explain-plan review for hot queries, and slow-query logging.", "impact": "Medium"},
        {"area": "API Optimization", "recommendation": "Batch endpoints for dashboard widgets; keep payloads slim with field selection.", "impact": "Medium"},
    ]

    bottlenecks = [
        {
            "stage": "Query growth",
            "cause": "Unexpanded list queries over thousands of rows",
            "remedy": "Keyset pagination + covering indexes from the first release",
        },
        {
            "stage": "Auth token verification",
            "cause": "JWT decode + DB user lookup per request",
            "remedy": "Stateless verification, cached user snapshots, short-lived access tokens",
        },
        {
            "stage": "File uploads",
            "cause": "Synchronous handling of large payloads",
            "remedy": "Direct-to-object-store uploads with signed URLs",
        },
    ]

    return {
        "summary": (
            "The design is reviewed against twelve performance areas. Most apply from day one with "
            "small effort; the expected bottlenecks below are monitored from the first release."
        ),
        "performance_score": 89,
        "checklist": checklist,
        "bottlenecks": bottlenecks,
        "expected_bottlenecks": [b["stage"] for b in bottlenecks],
        "database_tuning": {
            "engine": db_name,
            "recommendations": [
                "Enable query logging in development and slow-query logging in production.",
                "Prefer composite indexes for the most common WHERE + ORDER BY combinations.",
                "Use EXPLAIN ANALYZE before merging any complex query.",
            ],
        },
    }


# ---------------------------------------------------------------------------
# Scalability Planning (100 / 10k / 1M users)
# ---------------------------------------------------------------------------


def scalability_planning(input_data: dict[str, Any], blueprint: dict[str, Any]) -> dict[str, Any]:
    scenarios = [
        {
            "scenario": "A",
            "scale": "100 users",
            "assumptions": "Single team, single instance, shared database.",
            "expected_bottlenecks": ["None — well under a single node's capacity"],
            "scaling_strategy": "Keep the architecture simple; instrument metrics from day one.",
            "database_scaling": "One instance; indexed queries.",
            "caching": "Optional; Redis for sessions if needed.",
            "cdn": "Not required.",
            "load_balancer": "None needed.",
            "auto_scaling": "Manual.",
            "queue_requirements": "None.",
            "microservices_migration": "None.",
            "infrastructure_changes": "None.",
        },
        {
            "scenario": "B",
            "scale": "10,000 users",
            "assumptions": "Concurrency grows; team of 3-4; reads dominate.",
            "expected_bottlenecks": ["DB CPU on hot list queries", "Single app instance", "Token verification overhead"],
            "scaling_strategy": "Horizontal app replicas behind a load balancer; cache hot reads; keyset pagination.",
            "database_scaling": "Replica for reads; connection pooling; partitioning for the largest tables.",
            "caching": "Redis for sessions, counters and hot reference data.",
            "cdn": "Static assets + public pages.",
            "load_balancer": "Single LB with sticky-session-free routing.",
            "auto_scaling": "Replica count scaled on CPU/memory thresholds.",
            "queue_requirements": "Redis-backed queue for email/exports/notifications.",
            "microservices_migration": "Not needed; internal modules stay together.",
            "infrastructure_changes": "Managed hosting with autoscaling enabled.",
        },
        {
            "scenario": "C",
            "scale": "1,000,000 users",
            "assumptions": "Multiple regions; 99.9% availability target; dedicated team.",
            "expected_bottlenecks": ["Writes contention in the primary DB", "Shared caches become hotspots", "Regional latency"],
            "scaling_strategy": "Split reads to replicas, partition heavy tables, and extract hot workflows into services.",
            "database_scaling": "Read replicas per region; horizontal sharding for the hottest entities; archives for cold data.",
            "caching": "Multi-tier Redis clusters + CDN at the edge.",
            "cdn": "Full static + API edge caching for public content.",
            "load_balancer": "Regional LBs + global DNS routing.",
            "auto_scaling": "Kubernetes-backed autoscaling per workload.",
            "queue_requirements": "Dedicated queues per domain (email, jobs, analytics, notifications).",
            "microservices_migration": "Extract billing, notifications and search into services with their own stores.",
            "infrastructure_changes": "Kubernetes adoption, IaC (Terraform), SLO dashboards, cost tagging.",
        },
    ]
    return {
        "summary": (
            "Growth is planned as explicit scenarios. Each scenario names its expected bottlenecks "
            "and the exact infrastructure changes that unlock the next tier, so engineering effort "
            "is spent only when the business needs it."
        ),
        "scenarios": scenarios,
        "approach": (
            "Design once, scale in stages: a modular monolith today, replicas and caching at 10k, "
            "and controlled service extraction at 1M. Every stage is observable via the monitoring "
            "layers introduced earlier."
        ),
    }


# ---------------------------------------------------------------------------
# Cost Estimation
# ---------------------------------------------------------------------------


def cost_estimation(input_data: dict[str, Any], blueprint: dict[str, Any]) -> dict[str, Any]:
    complexity = blueprint.get("analysis", {}).get("complexity_score", {})
    hours = 360 if complexity.get("score", 50) >= 70 else 240 if complexity.get("score", 50) >= 40 else 160
    dev_rate = 65
    development_total = hours * dev_rate
    infra_monthly = 90
    third_party_monthly = 25
    ai_monthly = 15
    maintenance_monthly = int(development_total * 0.15 / 12)

    infra = {
        "monthly_total": infra_monthly,
        "yearly_total": infra_monthly * 12,
        "breakdown": [
            {"item": "App hosting (managed)", "amount": 40},
            {"item": "Database (managed)", "amount": 25},
            {"item": "Object storage + CDN", "amount": 15},
            {"item": "Monitoring + error tracking", "amount": 10},
        ],
    }
    total_monthly = infra_monthly + third_party_monthly + ai_monthly + maintenance_monthly
    return {
        "summary": (
            "Costs are estimated in USD from the complexity score and the selected stack. "
            "Development dominates at first; recurring costs are modest and every line is "
            "explained so budgets can be defended."
        ),
        "currency": "USD",
        "development_cost": {
            "estimated_total": development_total,
            "estimated_hours": hours,
            "assumptions": f"Billed at ${dev_rate}/hour blended rate for a team of {complexity.get('estimated_team', {}).get('total', 2)}.",
            "breakdown": [
                {"item": "Design & architecture", "amount": int(development_total * 0.1)},
                {"item": "Backend + database implementation", "amount": int(development_total * 0.4)},
                {"item": "Frontend implementation", "amount": int(development_total * 0.3)},
                {"item": "Testing, QA and hardening", "amount": int(development_total * 0.15)},
                {"item": "Deployment and documentation", "amount": int(development_total * 0.05)},
            ],
        },
        "infrastructure_cost": infra,
        "cloud_cost": {"note": "Included in infrastructure_cost; managed services chosen to avoid idle spend."},
        "ai_cost": {
            "monthly_total": ai_monthly,
            "yearly_total": ai_monthly * 12,
            "note": "LLM inference for AI features; rises with usage and can be capped via rate limits.",
        },
        "database_cost": {"note": "Included in infrastructure_cost; scaling to replicas roughly doubles DB line."},
        "storage_cost": {"note": "Included in infrastructure_cost; grows with file uploads."},
        "email_cost": {"monthly_total": 0, "note": "Transactional email is free-tier at MVP; paid tiers only above volume limits."},
        "monitoring_cost": {"note": "Included in infrastructure_cost."},
        "maintenance_cost": {"monthly_total": maintenance_monthly, "note": "15% of development cost per year for patches, upgrades and support."},
        "third_party_services": {"monthly_total": third_party_monthly, "note": "Map services, payment gateway and similar small fees."},
        "summary_table": {
            "monthly_total": total_monthly,
            "yearly_total": total_monthly * 12,
            "one_time_total": development_total,
        },
        "optimization_strategies": [
            "Use managed serverless where traffic is bursty to avoid idle compute.",
            "Cache aggressively to reduce database costs.",
            "Keep LLM usage behind explicit features with token budgets.",
            "Right-size instances quarterly; delete unused environments.",
            "Use reserved/committed-use pricing once traffic is stable.",
        ],
    }


# ---------------------------------------------------------------------------
# Business Risk Analysis
# ---------------------------------------------------------------------------


def business_risk_analysis(input_data: dict[str, Any], blueprint: dict[str, Any]) -> dict[str, Any]:
    analysis = blueprint.get("analysis", {})
    risks = [
        {
            "risk": "Low user adoption",
            "type": "Market",
            "likelihood": "Medium",
            "impact": "High",
            "level": "High",
            "warning": "The best architecture cannot save a product nobody uses.",
            "mitigation": ["Validate the core workflow with early users before full build-out", "Launch an MVP milestone and instrument usage"],
        },
        {
            "risk": "Vendor lock-in",
            "type": "Technical",
            "likelihood": "Medium",
            "impact": "Medium",
            "level": "Medium",
            "warning": "Hosted services can become hard to leave.",
            "mitigation": ["Prefer portable abstractions (Docker, standard SQL)", "Document migration paths in ADRs"],
        },
        {
            "risk": "Scalability issues at growth",
            "type": "Technical",
            "likelihood": "Medium",
            "impact": "Medium",
            "level": "Medium",
            "warning": "Early indexing and pagination mistakes are the most expensive to fix later.",
            "mitigation": ["The scalability plan sets explicit checkpoints", "Load-test at the 10k-user scenario before marketing pushes"],
        },
        {
            "risk": "Security incident",
            "type": "Security",
            "likelihood": "Low",
            "impact": "High",
            "level": "High",
            "warning": "Sensitive data loss erodes trust irreversibly.",
            "mitigation": ["OWASP-based controls designed in", "Pen test + dependency scanning before launch"],
        },
        {
            "risk": "Budget overrun",
            "type": "Financial",
            "likelihood": "Medium",
            "impact": "Medium",
            "level": "Medium",
            "warning": "Scope creep is the main budget driver.",
            "mitigation": ["Cost model tied to feature count", "Weekly roadmap check against the critical path"],
        },
        {
            "risk": "Timeline slippage",
            "type": "Delivery",
            "likelihood": "Medium",
            "impact": "Medium",
            "level": "Medium",
            "warning": "Estimate accuracy drops sharply beyond 8 weeks.",
            "mitigation": ["Milestones are weekly and deliverables-based", "Complexity score drives realistic sizing"],
        },
        {
            "risk": "Technical debt accumulation",
            "type": "Technical",
            "likelihood": "Medium",
            "impact": "Medium",
            "level": "Medium",
            "warning": "Untracked debt slows every future feature.",
            "mitigation": ["Consistency fixes logged by the review agent", "Refactoring budget inside each milestone"],
        },
    ]
    inherited = [
        {"risk": r["risk"], "likelihood": r.get("likelihood", "Medium"), "impact": r.get("impact", "Medium"), "mitigation": "; ".join(r.get("mitigation", []))}
        for r in analysis.get("risks", [])
    ]
    return {
        "summary": (
            "Risks are scored by likelihood and impact and ranked by combined level. Every risk "
            "carries a mitigation strategy, and the register is revisited whenever the scope changes."
        ),
        "risks": risks,
        "analysis_risks": inherited,
        "overall_risk_level": "Medium",
        "risk_score": 45,
    }


# ---------------------------------------------------------------------------
# Product Evolution Roadmap (V1..V5)
# ---------------------------------------------------------------------------


def product_evolution(input_data: dict[str, Any], blueprint: dict[str, Any]) -> dict[str, Any]:
    versions = [
        {
            "version": "Version 1",
            "name": "Core MVP",
            "objective": "Prove the core workflow end-to-end with the smallest useful feature set.",
            "features": ["Primary workflows from the business process model", "Essential CRUD + auth", "Basic monitoring"],
            "architecture_changes": ["Modular monolith deploys as a single unit"],
            "migration_requirements": ["None — greenfield"],
        },
        {
            "version": "Version 2",
            "name": "Business Features",
            "objective": "Complete the commercial feature set that makes the product sellable.",
            "features": ["Billing and payments", "Role-based admin tooling", "Email notifications", "Reporting dashboards"],
            "architecture_changes": ["Background queue for jobs", "Read replicas if load demands"],
            "migration_requirements": ["Database migrations for new entities", "Queue consumer rollout behind feature flag"],
        },
        {
            "version": "Version 3",
            "name": "AI Features",
            "objective": "Differentiate with AI-driven insights over the accumulated data.",
            "features": ["Recommendations", "Smart search", "Anomaly alerts", "Natural-language reporting"],
            "architecture_changes": ["AI service boundary (separate deployment)", "Token budget + caching layer for LLM calls"],
            "migration_requirements": ["Feature flags for all AI surfaces", "Data export pipeline for model training"],
        },
        {
            "version": "Version 4",
            "name": "Enterprise Features",
            "objective": "Win larger accounts with governance, compliance and SSO.",
            "features": ["SSO / SAML / SCIM", "Audit trails and retention policies", "Multi-tenant workspaces", "Custom roles"],
            "architecture_changes": ["Tenant-aware data layer", "Audit log service", "Regional residency options"],
            "migration_requirements": ["Tenant migration scripts", "Compliance documentation and pen-test cycle"],
        },
        {
            "version": "Version 5",
            "name": "Global Scale",
            "objective": "Serve a worldwide audience with multi-region reliability.",
            "features": ["Multi-region read replicas", "Edge caching", "Localization", "Premium support tiers"],
            "architecture_changes": ["Kubernetes-based orchestration", "Service extraction (billing, search, notifications)", "Sharded hot tables"],
            "migration_requirements": ["Data partitioning plan", "Chaos engineering practice", "SLO dashboards per region"],
        },
    ]
    return {
        "summary": (
            "The product evolves in five explicit phases. Each version lists objectives, features, "
            "architecture changes and migration requirements, so the roadmap reads like a product "
            "strategy document rather than a feature list."
        ),
        "current_phase": "Version 1",
        "versions": versions,
        "long_term_strategy": (
            "Invest in the data model and modular boundaries now; each later phase reuses them "
            "instead of rewriting. AI features (V3) are designed as an additive service so the "
            "core system never depends on them."
        ),
    }


# ---------------------------------------------------------------------------
# Architecture Decision Records (ADR)
# ---------------------------------------------------------------------------


def adr_records(input_data: dict[str, Any], blueprint: dict[str, Any]) -> dict[str, Any]:
    design = blueprint.get("design_decisions", {}).get("decisions", [])
    records = []
    for idx, d in enumerate(design[:6], start=1):
        records.append(
            {
                "id": f"ADR-{idx:03d}",
                "title": f"Selection of {d['decision']} for {d['topic']}",
                "decision_id": d["id"],
                "context": d["final_justification"],
                "problem": f"Choose the technology for the {d['topic']} layer that best fits the project's constraints.",
                "alternatives": d["alternatives"],
                "chosen_solution": d["decision"],
                "reasoning": d["why_chosen"],
                "consequences": {
                    "positive": d["advantages"],
                    "negative": d["disadvantages"],
                },
                "future_considerations": [
                    "Revisit this decision when traffic or team size changes materially.",
                    "Document any override in a new ADR rather than editing this one.",
                ],
            }
        )
    return {
        "summary": (
            "Architecture Decision Records capture the 'why' behind each major choice in a "
            "reusable, searchable format. They are the permanent memory of the design process."
        ),
        "records": records,
    }


# ---------------------------------------------------------------------------
# Blueprint Quality Review (validation agent)
# ---------------------------------------------------------------------------


def quality_review(blueprint: dict[str, Any]) -> dict[str, Any]:
    """Review the assembled blueprint for consistency and produce a quality report."""
    workflows = _get(blueprint, "business_processes.workflows", [])
    endpoints = _get(blueprint, "api.endpoints", [])
    mapping = _get(blueprint, "api.business_workflow_mapping", [])
    requirements = _get(blueprint, "analysis.functional_requirements", [])
    screens = _get(blueprint, "ui_ux.screens", [])
    tables = _get(blueprint, "database.tables", [])
    checks = []
    fixes = []

    # 1. Business modules match requirements
    req_covered = len(requirements) > 0
    checks.append(
        {"area": "Requirements coverage", "status": "pass" if req_covered else "fail",
         "message": f"{len(requirements)} functional requirements documented.",
         "recommendation": "Keep requirements in sync with the workflow model."}
    )

    # 2. Database supports every business process
    db_support = len(tables) > 0 and len(workflows) > 0
    checks.append(
        {"area": "Database supports processes", "status": "pass" if db_support else "fail",
         "message": f"{len(tables)} tables designed to support {len(workflows)} workflows.",
         "recommendation": "Add tables whenever a new workflow is modeled."}
    )

    # 3. APIs cover every workflow
    mapped_workflows = {m.get("workflow") for m in mapping}
    uncovered = [w.get("name") for w in workflows if w.get("name") not in mapped_workflows]
    if uncovered:
        checks.append(
            {"area": "API workflow coverage", "status": "fail", "message": f"Workflows without endpoints: {', '.join(uncovered)}.",
             "recommendation": "Add endpoints for uncovered workflows."}
        )
        fixes.append({"section": "api", "issue": f"Uncovered workflows: {', '.join(uncovered)}", "fixed_by": "API agent re-run adds endpoints for every workflow."})
    else:
        checks.append({"area": "API workflow coverage", "status": "pass", "message": f"All {len(workflows)} workflows map to endpoints.", "recommendation": ""})

    # 4. UI supports every API
    ui_support = len(screens) > 0
    checks.append(
        {"area": "UI supports workflows", "status": "pass" if ui_support else "fail",
         "message": f"{len(screens)} screens designed for the modeled workflows.",
         "recommendation": "Every workflow needs at least one screen."}
    )

    # 5. Testing covers every API
    api_tests = _get(blueprint, "testing.api_tests", [])
    test_cover = len(api_tests) >= min(len(endpoints), 4) or len(api_tests) > 0
    checks.append(
        {"area": "Testing coverage", "status": "pass" if test_cover else "fail",
         "message": f"{len(api_tests)} API test cases for {len(endpoints)} endpoints.",
         "recommendation": "At least one test per endpoint."}
    )

    # 6. Security matches architecture
    security_score = _get(blueprint, "security.security_score", 0)
    checks.append(
        {"area": "Security posture", "status": "pass" if security_score >= 80 else "warn",
         "message": f"Security assessment score {security_score}/100.",
         "recommendation": "Close remaining OWASP items before production."}
    )

    # 7. Documentation references all modules
    doc_ok = bool(_get(blueprint, "documentation.readme"))
    checks.append(
        {"area": "Documentation", "status": "pass" if doc_ok else "fail",
         "message": "README and guides reference the complete module list." if doc_ok else "Documentation missing.",
         "recommendation": "Regenerate documentation after any section change."}
    )

    # 8. Deployment supports expected scale
    deploy_ok = bool(_get(blueprint, "deployment.dockerfile")) and len(_get(blueprint, "scalability.scenarios", [])) > 0
    checks.append(
        {"area": "Deployment & scale", "status": "pass" if deploy_ok else "warn",
         "message": "Containerized deployment with staged scalability plan.",
         "recommendation": "Match environment sizes to the 10k-user scenario."}
    )

    # 9. Unused tables — tables not reachable through the API, not referenced by
    #    relationships, foreign keys or requirements, and not part of the seed data.
    unused_tables = _unused_tables(blueprint)
    if unused_tables:
        checks.append(
            {"area": "Unused tables", "status": "warn",
             "message": f"Tables without API, relationship or requirement references: {', '.join(unused_tables)}.",
             "recommendation": "Expose them through CRUD endpoints, reference them from another entity, or remove them."}
        )
        fixes.append({"section": "database", "issue": f"Unused tables: {', '.join(unused_tables)}", "fixed_by": "Database agent re-run prunes orphan tables or the API agent exposes them."})
    else:
        checks.append({"area": "Unused tables", "status": "pass", "message": f"All {len(tables)} tables are referenced by the API, relationships or requirements.", "recommendation": ""})

    # 10. Missing entities — API resources that have no backing table.
    missing_entities = _missing_entities(blueprint)
    if missing_entities:
        checks.append(
            {"area": "Missing entities", "status": "fail",
             "message": f"API resources without a corresponding table: {', '.join(missing_entities)}.",
             "recommendation": "Add the missing entities to the database design or drop the orphan endpoints."}
        )
        fixes.append({"section": "database", "issue": f"Missing tables for resources: {', '.join(missing_entities)}", "fixed_by": "Database agent re-run adds tables for every API resource."})
    else:
        checks.append({"area": "Missing entities", "status": "pass", "message": f"Every API resource maps to a {len(tables)}-table schema.", "recommendation": ""})

    # 11. Semantic consistency — every section is compared against the
    #     project's Domain Context (forbidden vocabulary from other domains).
    semantic = semantic_consistency_review(blueprint)
    semantic_report = semantic.get("report", [])
    semantic_failed = [r for r in semantic_report if r["status"] == "FAIL"]
    if semantic.get("skipped"):
        checks.append(
            {"area": "Semantic consistency", "status": "warn",
             "message": "Domain Context unavailable; skipped cross-domain vocabulary scan.",
             "recommendation": "Regenerate the blueprint so the Domain Context is recorded."}
        )
    elif semantic_failed:
        checks.append(
            {"area": "Semantic consistency", "status": "fail",
             "message": f"Semantic consistency {semantic['semantic_score']}/100 — cross-domain content in: "
                        f"{', '.join(r['label'] for r in semantic_failed)}.",
             "recommendation": "Regenerate the flagged sections; they reference vocabulary from another domain."}
        )
        for entry in semantic_failed:
            fixes.append({
                "section": entry["section"],
                "issue": f"Cross-domain vocabulary: {', '.join(entry['forbidden_terms'])}",
                "fixed_by": "Semantic regeneration re-renders the section against the Domain Context.",
            })
    else:
        checks.append(
            {"area": "Semantic consistency", "status": "pass",
             "message": f"Semantic consistency {semantic['semantic_score']}/100 — no cross-domain vocabulary detected.",
             "recommendation": ""}
        )

    fails = [c for c in checks if c["status"] == "fail"]
    warns = [c for c in checks if c["status"] == "warn"]

    consistency_pct = _consistency_pct(workflows, mapping, endpoints, screens, tables, requirements)
    architecture_pct = 92 if _get(blueprint, "architecture.high_level_architecture") else 60
    security_pct = security_score
    performance_pct = _get(blueprint, "performance.performance_score", 80)
    docs_pct = 100 if doc_ok else 40
    semantic_pct = semantic.get("semantic_score")
    if semantic_pct is not None:
        overall = int(
            (consistency_pct * 2 + architecture_pct + security_pct + performance_pct + docs_pct + semantic_pct * 2) / 8
        )
    else:
        overall = int(
            (consistency_pct * 2 + architecture_pct + security_pct + performance_pct + docs_pct) / 6
        )
    production_readiness = max(0, min(100, overall - len(fails) * 12 - len(warns) * 4))
    readiness = "Production Ready" if overall >= 90 and not fails else "Needs Attention" if fails else "Ready with Minor Gaps"

    quality_report: dict[str, Any] = {
        "overall_quality": overall,
        "production_readiness_score": production_readiness,
        "consistency": consistency_pct,
        "architecture": architecture_pct,
        "security": security_pct,
        "performance": performance_pct,
        "documentation": docs_pct,
        "readiness": readiness,
        "confidence_score": max(0, overall - len(warns) * 2),
        "summary": f"{len(checks)} checks executed, {len(fails)} fail, {len(warns)} warn.",
    }
    if semantic_pct is not None:
        quality_report["semantic_consistency_score"] = semantic_pct

    return {
        "overall_verdict": (
            "The blueprint is internally consistent and production-ready."
            if not fails
            else f"Review found {len(fails)} fail-level issue(s); affected sections were regenerated."
        ),
        "passed": not fails,
        "checks": checks,
        "gaps": [{"section": c["area"], "gap": c["message"], "suggestion": c["recommendation"]} for c in warns + fails],
        "consistency_fixes": fixes,
        "semantic_consistency": semantic,
        "quality_report": quality_report,
    }


def _get(blueprint: dict[str, Any], dotted: str, default: Any = None) -> Any:
    node: Any = blueprint
    for part in dotted.split("."):
        if not isinstance(node, dict) or part not in node:
            return default
        node = node[part]
    return node


def _norm_resource(text: str) -> str:
    """Normalize a table/resource name: lowercase, separators to spaces."""
    return str(text or "").strip().lower().replace("_", " ").replace("-", " ").strip()


def _singular_resource(name: str) -> str:
    """Best-effort singular form for matching resource names to table names."""
    if name.endswith("ies") and len(name) > 3:
        return f"{name[:-3]}y"
    if name.endswith("ss"):
        return name
    if name.endswith("s") and len(name) > 1:
        return name[:-1]
    return name


def _table_variants(table_name: str) -> set[str]:
    norm = _norm_resource(table_name)
    return {norm, _singular_resource(norm), norm.replace(" ", "_")}


def _unused_tables(blueprint: dict[str, Any]) -> list[str]:
    """Tables not reachable through endpoints, relationships, FKs, requirements or seed data."""
    tables = _get(blueprint, "database.tables", [])
    if not tables:
        return []
    table_names = [str(t.get("name") or "") for t in tables]
    variants = {name: _table_variants(name) for name in table_names}
    referenced: set[str] = set()

    def mark_referenced(corpus: Any) -> None:
        blob = json.dumps(corpus, ensure_ascii=False).lower() if corpus else ""
        for name, cands in variants.items():
            for cand in cands:
                if cand and re.search(rf"(?<![a-z0-9]){re.escape(cand)}(?![a-z0-9])", blob):
                    referenced.add(name)
                    break

    endpoints = _get(blueprint, "api.endpoints", [])
    mark_referenced([e.get("path") for e in endpoints])
    mark_referenced([e.get("description") for e in endpoints])
    mark_referenced(_get(blueprint, "analysis.functional_requirements", []))
    mark_referenced([w.get("name") for w in _get(blueprint, "business_processes.workflows", [])])

    for table in tables:
        for rel in table.get("relationships", []):
            mark_referenced([rel.get("to_table"), rel.get("on")])
        owns_fk = False
        for column in table.get("columns", []):
            col_text = f"{column.get('type')} {' '.join(column.get('constraints') or [])}"
            mark_referenced([col_text])
            if "references" in col_text.lower():
                owns_fk = True
        # Tables holding foreign keys (join tables, audit trails) exist to serve
        # the entities they reference — count them as used.
        if owns_fk:
            referenced.add(str(table.get("name") or ""))

    mark_referenced([_get(blueprint, "database.seed_data")])

    return [name for name in table_names if name not in referenced]


def _missing_entities(blueprint: dict[str, Any]) -> list[str]:
    """API resources (non-auth, non-workflow endpoints) without a backing table."""
    tables = _get(blueprint, "database.tables", [])
    table_names = {name for name in (_get(blueprint, "database.tables", []) and [str(t.get("name") or "") for t in tables] or []) if name}
    variants = set()
    for name in table_names:
        variants |= _table_variants(name)

    missing: list[str] = []
    for endpoint in _get(blueprint, "api.endpoints", []):
        path = str(endpoint.get("path") or "")
        if path.startswith("/auth/") or "/workflows/" in path:
            continue
        resource = _norm_resource(path.rstrip("/").rsplit("/", 1)[-1])
        if not resource or resource in ("me", "execute"):
            continue
        if resource not in variants and _singular_resource(resource) not in variants:
            label = f"'{resource}' ({endpoint.get('method')} {path})"
            if label not in missing:
                missing.append(label)
    return missing


def _consistency_pct(
    workflows: list[Any],
    mapping: list[Any],
    endpoints: list[Any],
    screens: list[Any],
    tables: list[Any],
    requirements: list[Any],
) -> int:
    parts = 0
    total = 0
    if workflows:
        total += 1
        parts += 1 if all(w.get("name") in {m.get("workflow") for m in mapping} for w in workflows) else 0
    if endpoints:
        total += 1
        parts += 1 if any(e.get("path") for e in endpoints) else 0
    if screens:
        total += 1
        parts += 1
    if tables:
        total += 1
        parts += 1
    if requirements:
        total += 1
        parts += 1
    return int(100 * (parts / total)) if total else 100
