"""AI Action Engine — canonical action catalog.

Single source of truth for every AI action exposed through the unified
``/projects/{id}/actions`` surface. Each entry declares its contract (category,
execution mode, mutation semantics, fallback support) and binds to a handler
in ``app.services.actions.executor``.

Actions never reimplement existing logic: transformations reuse the 21-node
pipeline's per-section generator (``agents.regenerate_section``), diagrams
reuse ``diagrams.registry`` and code artifacts reuse ``codegen.registry``
(whose safe ZIP path stays the single artifact channel).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

SectionKey = str


@dataclass(frozen=True)
class AIAction:
    id: str
    name: str
    category: str  # analysis | transformation | diagram | code | documentation
    description: str
    handler: Callable[..., Any]
    execution_mode: str = "short"  # short (synchronous) | long (durable job)
    mutates_project: bool = False
    supports_fallback: bool = True
    requires_blueprint: bool = True
    inputs: dict[str, Any] = field(default_factory=dict)
    apply_mode: str = "none"  # none | patch | replace | merge
    depends_on: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Blueprint sections that can be regenerated in isolation (21-node pipeline
# sections + the deterministic deployment section).
# ---------------------------------------------------------------------------

TRANSFORMABLE_SECTIONS = {
    "analysis": "Requirements Analysis",
    "domain_understanding": "Domain Understanding",
    "business_processes": "Business Process Modeling",
    "technology_selection": "Technology Selection",
    "technology_evaluation": "Technology Evaluation",
    "design_decisions": "Design Decisions",
    "tradeoffs": "Trade-off Analysis",
    "architecture": "Architecture",
    "database": "Database Design",
    "api": "API Specification",
    "ui_ux": "UI/UX Plan",
    "security": "Security Review",
    "performance": "Performance Review",
    "scalability": "Scalability Planning",
    "cost_estimation": "Cost Estimation",
    "business_risks": "Business Risk Analysis",
    "roadmap": "Development Roadmap",
    "product_evolution": "Product Evolution",
    "adr": "Architecture Decision Records",
    "testing": "Testing Strategy",
    "documentation": "Documentation",
    "deployment": "Deployment & DevOps",
}

#: Sections that carry user-facing "Explain" actions in the workspace UI.
EXPLAINABLE_SECTIONS = set(TRANSFORMABLE_SECTIONS) | {"validation"}


def _section_input() -> dict[str, Any]:
    return {"section": {"type": "string", "enum": sorted(TRANSFORMABLE_SECTIONS)}}


def _build_registry() -> dict[str, AIAction]:
    # Deferred import: the registry module is imported by the executor, which
    # in turn needs the registry constants — avoid the circular import.
    from app.services.actions import executor  # noqa: PLC0415

    actions: dict[str, AIAction] = {}

    # --- Analysis / read-only -------------------------------------------------
    actions["explain-project"] = AIAction(
        id="explain-project",
        name="Explain Project",
        category="analysis",
        description=(
            "Plain-language summary of the whole blueprint: scope, architecture, "
            "key decisions, risks and next steps."
        ),
        handler=executor.explain_project,
        mutates_project=False,
        inputs={"focus": {"type": "string", "optional": True}},
    )
    actions["explain-section"] = AIAction(
        id="explain-section",
        name="Explain Section",
        category="analysis",
        description="Plain-language summary of one blueprint section.",
        handler=executor.explain_section,
        mutates_project=False,
        inputs=_section_input(),
    )

    # --- Blueprint transformations (reuse the 21-node pipeline per section) ---
    # Each entry declares its target section, apply mode (how a stored result
    # may be applied to the blueprint) and declarative dependency metadata.
    # apply_mode is "none" unless the section content is safe to re-apply.
    named_transforms: dict[str, tuple[str, str, str, list[str]]] = {
        "improve-requirements": ("analysis", "Improve Requirements", "replace", []),
        "generate-architecture": ("architecture", "Generate Architecture", "replace", ["analysis"]),
        "generate-database-design": (
            "database",
            "Generate Database Design",
            "replace",
            ["analysis", "architecture"],
        ),
        "generate-api-specification": (
            "api",
            "Generate API Specification",
            "none",
            ["analysis", "database"],
        ),
        "generate-uiux-plan": ("ui_ux", "Generate UI/UX Plan", "none", ["analysis", "api"]),
        "generate-testing-strategy": (
            "testing",
            "Generate Testing Strategy",
            "none",
            ["analysis", "api"],
        ),
        "generate-deployment-plan": (
            "deployment",
            "Generate Deployment Plan",
            "none",
            ["architecture", "testing"],
        ),
        "generate-security-recommendations": (
            "security",
            "Generate Security Recommendations",
            "none",
            ["analysis", "architecture", "database", "api"],
        ),
        "generate-project-roadmap": (
            "roadmap",
            "Generate Project Roadmap",
            "replace",
            ["analysis", "architecture", "database"],
        ),
    }
    for action_id, (section, name, apply_mode, depends_on) in named_transforms.items():
        actions[action_id] = AIAction(
            id=action_id,
            name=name,
            category="transformation",
            description=(
                f"Regenerate the '{TRANSFORMABLE_SECTIONS[section]}' section with "
                "AI (or the deterministic engine), preserving every other section."
            ),
            handler=executor.transform_section,
            mutates_project=True,
            inputs=_section_input(),
            apply_mode=apply_mode,
            depends_on=depends_on,
        )
    actions["transform-section"] = AIAction(
        id="transform-section",
        name="Refine Section",
        category="transformation",
        description=(
            "Regenerate any blueprint section in isolation; unrelated sections "
            "are preserved and the blueprint is re-validated."
        ),
        handler=executor.transform_section,
        mutates_project=True,
        inputs=_section_input(),
    )

    # --- Diagram actions (existing hardened Mermaid generators) ---------------
    from app.services.diagrams.registry import DIAGRAMS

    for diagram_id in DIAGRAMS:
        actions[f"generate-diagram-{diagram_id}"] = AIAction(
            id=f"generate-diagram-{diagram_id}",
            name=f"Generate {DIAGRAMS[diagram_id]['label']}",
            category="diagram",
            description=f"Generate the {DIAGRAMS[diagram_id]['label']} Mermaid diagram for this blueprint.",
            handler=executor.generate_diagram,
            mutates_project=False,
            inputs={"diagram_id": {"type": "string", "enum": [diagram_id]}},
        )

    # --- Code generation actions (existing generators, safe ZIP stays unique) ---
    from app.services.codegen.registry import GENERATORS

    for generator_id in GENERATORS:
        actions[f"generate-{generator_id}"] = AIAction(
            id=f"generate-{generator_id}",
            name=GENERATORS[generator_id]["label"],
            category="code",
            description=GENERATORS[generator_id]["description"],
            handler=executor.generate_code_artifact,
            mutates_project=False,
            inputs={"generator_id": {"type": "string", "enum": [generator_id]}},
        )

    # --- Phase 10: Specialized AI Actions (read-only analysis) ---
    specialized_actions: list[tuple[str, str, str, Callable[..., Any], str, list[str]]] = [
        (
            "security-audit",
            "Security Audit",
            (
                "Analyze the blueprint for security risks: authentication, "
                "authorization, data protection, input validation, API security, "
                "secrets management, dependencies, infrastructure, deployment, "
                "logging, and common domain-specific threats."
            ),
            executor.security_audit,
            "none",
            [],
        ),
        (
            "generate-test-strategy",
            "Generate Test Strategy",
            (
                "Derive a practical testing strategy from requirements, "
                "architecture, database, API, and existing testing section. "
                "Covers unit, integration, API, database, frontend, E2E, security, "
                "performance, test data, and CI execution."
            ),
            executor.generate_test_strategy,
            "merge",
            ["analysis", "architecture", "database", "api"],
        ),
        (
            "generate-ci-cd",
            "Generate CI/CD Pipeline",
            (
                "Create a stack-aware CI/CD plan using technology, architecture, "
                "deployment, and testing sections. Covers install/build, lint, test, "
                "security checks, artifact generation, deployment, environments, "
                "secrets, and rollback."
            ),
            executor.generate_ci_cd,
            "merge",
            ["technology_selection", "deployment", "testing"],
        ),
        (
            "generate-sprint-plan",
            "Generate Sprint Plan",
            (
                "Derive an implementation plan from requirements, features, roadmap, "
                "architecture, database, and API. Outputs epics, sprints, goals, tasks, "
                "dependencies, priorities, effort estimates, and critical path."
            ),
            executor.generate_sprint_plan,
            "none",
            ["analysis", "roadmap", "architecture"],
        ),
        (
            "generate-risk-register",
            "Generate Risk Register",
            (
                "Analyze the blueprint for technical, security, operational, "
                "scalability, dependency, delivery, data, compliance, and vendor risks. "
                "Each risk includes category, likelihood, impact, severity, mitigation, "
                "owner role, and monitoring signal."
            ),
            executor.generate_risk_register,
            "merge",
            ["analysis", "architecture", "deployment", "security"],
        ),
        (
            "generate-compliance-map",
            "Generate Compliance Map",
            (
                "Map potentially relevant regulatory frameworks and controls based on "
                "domain and data. Outputs compliance considerations, relevant controls, "
                "missing controls, evidence required, and implementation recommendations "
                "— never claims legal compliance."
            ),
            executor.generate_compliance_map,
            "none",
            [],
        ),
    ]
    for action_id, name, description, handler, apply_mode, depends_on in specialized_actions:
        actions[action_id] = AIAction(
            id=action_id,
            name=name,
            category="analysis",
            description=description,
            handler=handler,
            mutates_project=False,
            supports_fallback=True,
            requires_blueprint=True,
            apply_mode=apply_mode,
            depends_on=depends_on,
        )

    return actions


class _LazyRegistry(dict):
    """dict-like registry that builds its contents on first access.

    Building the catalog requires the executor module, which imports this
    module — deferring construction breaks the cycle.
    """

    def _ensure(self) -> None:
        if not super().__len__():
            self.update(_build_registry())

    def values(self):
        self._ensure()
        return super().values()

    def items(self):
        self._ensure()
        return super().items()

    def get(self, key: str, default: Any = None):
        self._ensure()
        return super().get(key, default)

    def __contains__(self, key: object) -> bool:
        self._ensure()
        return super().__contains__(key)

    def __iter__(self):
        self._ensure()
        return super().__iter__()

    def __len__(self) -> int:
        self._ensure()
        return super().__len__()


ACTION_REGISTRY: _LazyRegistry = _LazyRegistry()


def get_action(action_id: str) -> AIAction | None:
    return ACTION_REGISTRY.get(action_id)
