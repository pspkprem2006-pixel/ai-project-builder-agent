"""AI Action Engine — central action execution.

Every action flows through ``execute_action``:

    project ownership (route) → blueprint normalization (route)
    → input validation → handler → result normalization

Handlers never raise into the API layer: all failures are classified into the
result contract (validation_failed / llm_failed / fallback / error) with
generic messages (Phase 8 error hygiene). Transformations reuse the 21-node
pipeline's ``agents.regenerate_section`` so there is exactly one architecture
generator; diagrams and code artifacts reuse the existing registries.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from typing import Any

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.project import Project
from app.schemas.action import ActionResultOut, ArtifactInfo
from app.services.actions.registry import TRANSFORMABLE_SECTIONS
from app.services.ai.llm import LLMClient, LLMError, LLMNotConfiguredError
from app.services.ai.prompts import (
    CI_CD_PROMPT,
    COMPLIANCE_MAP_PROMPT,
    EXPLAIN_PROJECT_PROMPT,
    EXPLAIN_SECTION_PROMPT,
    RISK_REGISTER_PROMPT,
    SECURITY_AUDIT_PROMPT,
    SPRINT_PLAN_PROMPT,
    TEST_STRATEGY_PROMPT,
)
from app.services.codegen.registry import generator_manifest
from app.services.diagrams.registry import DIAGRAMS
from app.services.diagrams.registry import generate_diagram as _generate_diagram

logger = logging.getLogger("action_engine")

GENERIC_ACTION_ERROR = "The action failed unexpectedly. Please try again later."


class ActionInputError(ValueError):
    """Invalid action inputs (schema or semantics)."""


# ---------------------------------------------------------------------------
# Result helpers
# ---------------------------------------------------------------------------


def _error(message: str) -> ActionResultOut:
    return ActionResultOut(action_id="", status="error", message=message)


def _validation_failed(action_id: str, message: str) -> ActionResultOut:
    return ActionResultOut(action_id=action_id, status="validation_failed", message=message)


# ---------------------------------------------------------------------------
# Blueprint digest (deterministic fallback for explanations, prompt context)
# ---------------------------------------------------------------------------


def _section_summary(blueprint: dict[str, Any], section: str) -> dict[str, Any]:
    data = blueprint.get(section) or {}
    if not isinstance(data, dict):
        return {}
    fields = ["summary", "problem_statement", "description", "title"]
    digest: dict[str, Any] = {}
    for field in fields:
        value = data.get(field)
        if isinstance(value, str) and value.strip():
            digest[field] = value[:1200]
    if section == "analysis":
        for key in ("objectives", "functional_requirements", "non_functional_requirements"):
            if isinstance(data.get(key), list):
                digest[key] = data[key][:6]
    for key in ("tables", "endpoints", "screens", "weekly_milestones", "decisions", "risks"):
        if isinstance(data.get(key), list):
            digest[key] = data[key][:6]
    return digest


def _blueprint_digest(blueprint: dict[str, Any]) -> dict[str, Any]:
    digest: dict[str, Any] = {}
    sections = (
        "analysis",
        "architecture",
        "database",
        "api",
        "ui_ux",
        "security",
        "roadmap",
        "deployment",
    )
    for section in sections:
        digest[section] = _section_summary(blueprint, section)
    return digest


def _deterministic_explain(blueprint: dict[str, Any], section: str | None) -> dict[str, Any]:
    """Structured digest used when no LLM is available or the LLM fails."""
    if section is not None:
        return {
            "summary": _section_summary(blueprint, section) or {"note": "This section has no summary text."},
            "highlights": [],
            "recommendations": [],
        }
    digest = _blueprint_digest(blueprint)
    overview = (
        f"This blueprint specifies {blueprint.get('project', {}).get('name', 'the project')} "
        "across analysis, architecture, database, API, UI/UX, security, roadmap and deployment."
    )
    highlights = [
        f"{name}: {d.get('summary', '')[:200]}"
        for name, d in digest.items()
        if d.get("summary")
    ][:6]
    return {
        "overview": overview,
        "highlights": highlights,
        "risks": [],
        "next_steps": ["Run the diagram and code-generation actions to start implementation."],
    }


# ---------------------------------------------------------------------------
# Explain handlers (read-only, LLM + deterministic digest fallback)
# ---------------------------------------------------------------------------


def _explain(
    action_id: str,
    blueprint: dict[str, Any],
    prompt: str,
    context: dict[str, Any],
    section: str | None,
    inputs: dict[str, Any],
) -> ActionResultOut:
    warnings: list[str] = []
    llm = LLMClient(model_role="fast")
    if llm.available:
        try:
            user = (
                f"BLUEPRINT SECTION ({section})\n```json\n{json.dumps(context, indent=2)[:20000]}\n```"
                if section
                else f"BLUEPRINT\n```json\n{json.dumps(context, indent=2)[:30000]}\n```"
            )
            result = llm.chat_json(prompt, user, max_tokens=2000)
            if isinstance(result, dict):
                return ActionResultOut(
                    action_id=action_id,
                    status="success",
                    result=result,
                    provider="llm",
                    warnings=warnings,
                )
        except (LLMError, LLMNotConfiguredError) as exc:
            logger.info("explain_action_llm_failed action=%s reason=%s", action_id, exc)
            warnings.append("The LLM provider failed; showing the deterministic summary instead.")
    return ActionResultOut(
        action_id=action_id,
        status="fallback",
        result=_deterministic_explain(blueprint, section),
        provider="deterministic",
        warnings=warnings or ["No LLM provider configured; showing the deterministic summary."],
    )


def explain_project(
    project: Project, blueprint: dict[str, Any], inputs: dict[str, Any], db: Session
) -> ActionResultOut:
    return _explain(
        "explain-project",
        blueprint,
        EXPLAIN_PROJECT_PROMPT,
        _blueprint_digest(blueprint),
        None,
        inputs,
    )


def explain_section(
    project: Project, blueprint: dict[str, Any], inputs: dict[str, Any], db: Session
) -> ActionResultOut:
    section = inputs.get("section")
    if not isinstance(section, str) or section not in TRANSFORMABLE_SECTIONS:
        return _validation_failed("explain-section", f"Unknown section '{section}'.")
    return _explain(
        "explain-section",
        blueprint,
        EXPLAIN_SECTION_PROMPT,
        blueprint.get(section) or {},
        section,
        inputs,
    )


# ---------------------------------------------------------------------------
# Blueprint transformation (reuses the 21-node pipeline's section generator)
# ---------------------------------------------------------------------------


def transform_section(
    project: Project, blueprint: dict[str, Any], inputs: dict[str, Any], db: Session
) -> ActionResultOut:
    section = inputs.get("section")
    if not isinstance(section, str) or section not in TRANSFORMABLE_SECTIONS:
        return _validation_failed("transform-section", f"Unknown section '{section}'.")

    from app.services.orchestrator import regenerate_section_for_project

    db.refresh(project)
    regenerate_section_for_project(db, project, section)

    settings = get_settings()
    provider = "llm" if settings.llm_configured else "deterministic"
    return ActionResultOut(
        action_id="transform-section",
        status="success" if settings.llm_configured else "fallback",
        result=(project.blueprint or {}).get(section) or {},
        section=section,
        provider=provider,
        warnings=(
            []
            if settings.llm_configured
            else ["No LLM provider configured; the section was generated by the deterministic engine."]
        ),
    )


# ---------------------------------------------------------------------------
# Diagram actions (existing hardened Mermaid generators)
# ---------------------------------------------------------------------------


def generate_diagram(
    project: Project, blueprint: dict[str, Any], inputs: dict[str, Any], db: Session
) -> ActionResultOut:
    action_id = inputs.get("action_id", "generate-diagram")
    diagram_id = action_id.removeprefix("generate-diagram-")
    if diagram_id not in DIAGRAMS:
        return _validation_failed(action_id, f"Unknown diagram type '{diagram_id}'.")
    try:
        mermaid = _generate_diagram(diagram_id, blueprint)
    except Exception:  # noqa: BLE001 - classify, never leak
        logger.exception("diagram_action_failed diagram=%s project=%s", diagram_id, project.id)
        return _error(GENERIC_ACTION_ERROR)
    return ActionResultOut(
        action_id=action_id,
        status="success",
        result={"diagram_id": diagram_id, "title": DIAGRAMS[diagram_id]["label"], "mermaid": mermaid},
        provider="deterministic",
    )


# ---------------------------------------------------------------------------
# Code artifact actions (existing generators; safe ZIP stays the single path)
# ---------------------------------------------------------------------------


def generate_code_artifact(
    project: Project, blueprint: dict[str, Any], inputs: dict[str, Any], db: Session
) -> ActionResultOut:
    action_id = inputs.get("action_id", "generate-code")
    generator_id = action_id.removeprefix("generate-")
    try:
        manifest = generator_manifest(generator_id, blueprint)
    except KeyError:
        return _validation_failed(action_id, f"Unknown code generator '{generator_id}'.")
    except Exception:  # noqa: BLE001 - classify, never leak
        logger.exception("codegen_action_failed generator=%s project=%s", generator_id, project.id)
        return _error(GENERIC_ACTION_ERROR)
    slug = "".join(c if c.isalnum() or c in "-_" else "-" for c in project.name.lower())[:60]
    filename = f"{slug}-{generator_id}.zip"
    return ActionResultOut(
        action_id=action_id,
        status="success",
        result={"generator_id": generator_id, "files": manifest, "file_count": len(manifest)},
        provider="deterministic",
        artifact=ArtifactInfo(
            kind="codegen-zip",
            filename=filename,
            download_url=f"/api/v1/projects/{project.id}/codegen/{generator_id}",
        ),
    )


# ---------------------------------------------------------------------------
# Phase 10: Specialized AI Actions (read-only analysis with LLM + fallback)
# ---------------------------------------------------------------------------


def _domain_label(blueprint: dict[str, Any]) -> str:
    """Human-readable domain label from the blueprint, defaulting safely."""
    domain = blueprint.get("domain_understanding") or {}
    label = domain.get("domain_label") or domain.get("identified_domain")
    return str(label)[:120] if label else "the project"


def _text(value: Any, max_len: int = 120) -> str:
    return str(value or "")[:max_len]


def _detect_stack(project: Project, blueprint: dict[str, Any]) -> dict[str, str]:
    """Detect frontend/backend/database/deployment from project + blueprint."""
    from app.services.actions.artifacts import _stack

    return _stack(project, blueprint)


def _deterministic_security_audit(blueprint: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    """Deterministic security analysis based on blueprint presence/absence.

    Never claims a vulnerability exists; it reports what the blueprint does
    and does not specify (Phase 13 requirement).
    """
    label = _domain_label(blueprint)
    api = blueprint.get("api") or {}
    security = blueprint.get("security") or {}
    deployment = blueprint.get("deployment") or {}
    processes = blueprint.get("business_processes") or {}

    findings: list[dict[str, Any]] = []
    missing: list[str] = []

    auth = api.get("auth") or {}
    auth_method = auth.get("method") if isinstance(auth, dict) else None
    if not auth_method:
        findings.append(
            {
                "category": "authentication",
                "status": "missing_information",
                "severity": "medium",
                "title": "Authentication strategy is not specified in the blueprint.",
                "description": (
                    f"The {label} blueprint does not specify an authentication method "
                    "(e.g., JWT, OAuth2, session-based) in the API specification."
                ),
                "evidence": [],
                "recommendation": (
                    "Specify an authentication method in the API specification's "
                    "auth section before implementation."
                ),
            }
        )
        missing.append("authentication strategy")

    role_permissions = processes.get("role_permissions") if isinstance(processes, dict) else None
    authorization_signal = api.get("endpoints") and any(
        isinstance(e, dict) and e.get("authentication") for e in (api.get("endpoints") or [])
    )
    if not role_permissions and not authorization_signal:
        findings.append(
            {
                "category": "authorization",
                "status": "missing_information",
                "severity": "medium",
                "title": "Authorization model is not specified in the blueprint.",
                "description": (
                    "No role-permission mapping (business processes) or per-endpoint "
                    "authentication flags (API specification) were found."
                ),
                "evidence": [],
                "recommendation": "Define role permissions and per-endpoint authorization rules.",
            }
        )
        missing.append("authorization model")

    endpoints = api.get("endpoints") or []
    validated = [e for e in endpoints if isinstance(e, dict) and e.get("validation_rules")]
    if endpoints and not validated:
        findings.append(
            {
                "category": "input_validation",
                "status": "missing_information",
                "severity": "medium",
                "title": "Input validation rules are not specified in the blueprint.",
                "description": "API endpoints are defined but none carries validation_rules.",
                "evidence": [],
                "recommendation": "Add validation rules (format, length, range) to each endpoint.",
            }
        )
        missing.append("input validation rules")

    if not deployment:
        findings.append(
            {
                "category": "deployment",
                "status": "missing_information",
                "severity": "low",
                "title": "Deployment configuration is not specified in the blueprint.",
                "description": "No deployment & DevOps section; security posture for hosting is unknown.",
                "evidence": [],
                "recommendation": "Add a deployment section covering TLS, firewall and secret injection.",
            }
        )
        missing.append("deployment configuration")

    security_assessment = security.get("assessment") if isinstance(security, dict) else None
    if not security_assessment:
        findings.append(
            {
                "category": "logging_monitoring",
                "status": "missing_information",
                "severity": "low",
                "title": "Logging and monitoring strategy is not specified in the blueprint.",
                "description": "The blueprint does not describe audit logging or monitoring signals.",
                "evidence": [],
                "recommendation": "Define audit logging and monitoring for security-relevant events.",
            }
        )
        missing.append("logging/monitoring strategy")

    if not findings:
        findings.append(
            {
                "category": "domain_specific",
                "status": "recommendation",
                "severity": "informational",
                "title": "Security testing plan is not specified in the blueprint.",
                "description": (
                    f"The {label} blueprint does not specify a security testing plan "
                    "(e.g., dependency scanning, SAST, penetration testing) before release."
                ),
                "evidence": [],
                "recommendation": (
                    "Schedule dependency scanning and SAST in CI and define a "
                    "pre-release security review."
                ),
            }
        )

    owasp_mapping = [
        {
            "rank": "A01",
            "name": "Broken Access Control",
            "status": "gap" if not authorization_signal else "covered",
            "notes": (
                "Authorization model is not specified in the blueprint."
                if not authorization_signal
                else "Authorization signals found."
            ),
        },
        {
            "rank": "A02",
            "name": "Cryptographic Failures",
            "status": "gap" if not security.get("privacy") else "partial",
            "notes": "Data protection details are not specified in the blueprint.",
        },
        {
            "rank": "A03",
            "name": "Injection",
            "status": "covered" if validated else "gap",
            "notes": (
                "Input validation rules are not specified in the blueprint."
                if not validated
                else "Validation rules found on endpoints."
            ),
        },
        {
            "rank": "A05",
            "name": "Security Misconfiguration",
            "status": "gap" if not deployment else "partial",
            "notes": "Deployment configuration is not specified in the blueprint.",
        },
        {
            "rank": "A07",
            "name": "Authentication Failures",
            "status": "gap" if not auth_method else "covered",
            "notes": (
                "Authentication strategy is not specified in the blueprint."
                if not auth_method
                else f"Auth method: {auth_method}"
            ),
        },
        {
            "rank": "A09",
            "name": "Logging and Monitoring Failures",
            "status": "gap" if not security_assessment else "partial",
            "notes": "Logging/monitoring strategy is not specified in the blueprint.",
        },
        {
            "rank": "A10",
            "name": "SSRF",
            "status": "not_assessed",
            "notes": "SSRF controls were not assessed from the blueprint.",
        },
    ]

    return {
        "summary": (
            f"Deterministic security posture for {label}: the blueprint specifies "
            f"{len(findings)} areas that need attention before implementation. "
            "None of these are claims of active vulnerabilities — they describe "
            "what the blueprint does not specify."
        ),
        "findings": findings,
        "owasp_mapping": owasp_mapping,
        "domain_specific_notes": [
            f"Domain: {label}. Revisit security controls with domain-specific "
            "requirements (e.g., sensitive data handling) during design."
        ],
        "missing_information": missing or ["No missing information detected."],
        "context": context,
        "note": "No LLM provider configured; deterministic presence/absence analysis.",
    }


def _deterministic_test_strategy(blueprint: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    """Deterministic testing strategy derived from actual blueprint sections."""
    label = _domain_label(blueprint)
    api = blueprint.get("api") or {}
    database = blueprint.get("database") or {}
    ui = blueprint.get("ui_ux") or {}
    analysis = blueprint.get("analysis") or {}

    endpoints = [e for e in (api.get("endpoints") or []) if isinstance(e, dict) and e.get("path")]
    tables = [t for t in (database.get("tables") or []) if isinstance(t, dict) and t.get("name")]
    screens = [s for s in (ui.get("screens") or []) if isinstance(s, dict) and s.get("name")]
    requirements = analysis.get("functional_requirements") or []

    api_tests = [
        {
            "name": f"api-test-{i + 1}",
            "endpoint": e["path"],
            "method": e.get("method", "GET"),
            "scenario": f"Verify {e.get('description', 'the endpoint')} behaves correctly.",
            "priority": "Must Have",
        }
        for i, e in enumerate(endpoints[:10])
    ]
    database_tests = [
        {
            "name": f"db-test-{i + 1}",
            "area": "constraints",
            "scenario": f"Verify constraints and relationships for table '{t['name']}'.",
        }
        for i, t in enumerate(tables[:10])
    ]
    frontend_tests = [
        {
            "name": f"ui-test-{i + 1}",
            "screen": s["name"],
            "scenario": f"Verify the '{s['name']}' screen renders and supports key flows.",
        }
        for i, s in enumerate(screens[:10])
    ]
    unit_tests = [
        {
            "name": f"unit-test-{i + 1}",
            "target": req.get("title", "requirement"),
            "scenario": "Unit-test the business logic implementing this requirement.",
            "priority": "Must Have" if req.get("priority") == "Must Have" else "Should Have",
        }
        for i, req in enumerate(requirements[:10])
    ]

    project_block = blueprint.get("project") or {}
    stack_block = project_block.get("stack") or {}
    backend = str(stack_block.get("backend") or "").lower()
    python_backend = "python" in backend
    node_backend = "node" in backend
    tools = {
        "unit": "pytest" if python_backend else ("Jest" if node_backend else "framework default"),
        "integration": "pytest" if python_backend else "framework default",
        "api": (
            "pytest + TestClient"
            if python_backend
            else ("supertest" if node_backend else "framework default")
        ),
        "e2e": "Playwright",
        "performance": "Locust" if python_backend else "k6",
    }

    return {
        "summary": (
            f"Deterministic testing strategy for {label}: "
            f"{len(unit_tests)} unit, {len(api_tests)} API, {len(database_tests)} database "
            f"and {len(frontend_tests)} frontend tests derived from the blueprint. "
            "Prioritize Must Have coverage first."
        ),
        "unit_tests": unit_tests,
        "integration_tests": [],
        "api_tests": api_tests,
        "database_tests": database_tests,
        "frontend_tests": frontend_tests,
        "e2e_tests": [
            {
                "name": "e2e-core-journey",
                "journey": "The primary business workflow from the blueprint.",
                "scenario": "Drive the main user journey end to end through the UI and API.",
                "critical_path": True,
            }
        ],
        "security_tests": [
            {
                "name": "security-auth-matrix",
                "threat": "Broken authentication",
                "scenario": "Verify auth flows reject invalid credentials and enforce roles.",
            }
        ],
        "performance_tests": [
            {
                "name": "perf-core-endpoints",
                "metric": "p95 latency",
                "threshold": "defined by the team (not specified in the blueprint)",
                "scenario": "Load-test the highest-traffic endpoints.",
            }
        ],
        "test_data_strategy": (
            "Generate fixtures from the blueprint's seed data where present; isolate per test."
        ),
        "ci_execution_strategy": "Run unit and API tests on every push; E2E on the main branch.",
        "tools": tools,
        "coverage_targets": {
            "unit": "not specified in the blueprint",
            "integration": "not specified in the blueprint",
            "api": "not specified in the blueprint",
            "overall": "not specified in the blueprint",
        },
        "gaps": (
            [
                "Coverage targets are not specified in the blueprint.",
                "Test data strategy is not specified in the blueprint.",
            ]
            if not (database.get("seed_data") or analysis.get("test_data"))
            else []
        ),
        "context": context,
        "note": "No LLM provider configured; deterministic strategy derived from the blueprint.",
    }


def _deterministic_ci_cd(
    blueprint: dict[str, Any], context: dict[str, Any], project: Project
) -> dict[str, Any]:
    """Deterministic CI/CD pipeline outline derived from the detected stack."""
    label = _domain_label(blueprint)
    stack = _detect_stack(project, blueprint)
    backend = stack.get("backend") or ""
    frontend = stack.get("frontend") or ""
    database = stack.get("database") or ""
    deployment = stack.get("deployment") or ""

    if "node" in backend:
        install, lint, test = "npm ci", "npm run lint", "npm test"
    elif "java" in backend:
        install, lint, test = "./mvnw install -DskipTests", "./mvnw verify -DskipTests", "./mvnw test"
    elif "go" in backend:
        install, lint, test = "go mod download", "go vet ./...", "go test ./..."
    else:
        install, lint, test = "pip install -r requirements.txt", "ruff check .", "pytest -q"

    stages = [
        {
            "name": "install",
            "jobs": [
                {
                    "name": "dependencies",
                    "runs_on": "ubuntu-latest",
                    "steps": [install],
                    "needs": [],
                    "if": "",
                }
            ],
        },
        {
            "name": "lint",
            "jobs": [
                {
                    "name": "lint",
                    "runs_on": "ubuntu-latest",
                    "steps": [lint],
                    "needs": ["dependencies"],
                    "if": "",
                }
            ],
        },
        {
            "name": "test",
            "jobs": [
                {
                    "name": "tests",
                    "runs_on": "ubuntu-latest",
                    "steps": [test],
                    "needs": ["dependencies"],
                    "if": "",
                }
            ],
        },
        {
            "name": "security",
            "jobs": [
                {
                    "name": "dependency-scan",
                    "runs_on": "ubuntu-latest",
                    "steps": ["Run a dependency vulnerability scanner (e.g. pip-audit, npm audit, trivy)."],
                    "needs": ["dependencies"],
                    "if": "",
                }
            ],
        },
    ]
    if deployment:
        stages.append(
            {
                "name": "deploy",
                "jobs": [
                    {
                        "name": "deploy",
                        "runs_on": "ubuntu-latest",
                        "steps": [
                            f"Deploy the artifact to {deployment} using a token from the secret store."
                        ],
                        "needs": ["tests", "security"],
                        "if": "github.ref == 'refs/heads/main'",
                    }
                ],
            }
        )

    return {
        "summary": (
            f"Deterministic CI/CD outline for {label} "
            f"(backend={backend or 'unknown'}, frontend={frontend or 'unknown'}, "
            f"database={database or 'unknown'}, deployment={deployment or 'unknown'})."
        ),
        "platform": "GitHub Actions",
        "pipeline_stages": stages,
        "environment_strategy": {
            "environments": ["development", "staging", "production"] if deployment else ["development"],
            "deployment_triggers": ["main branch pushes", "manual dispatch"] if deployment else [],
            "secrets_management": (
                "Reference the repository secret store (e.g. GitHub Secrets); "
                "never commit credentials."
            ),
            "rollback_strategy": (
                "Not specified in the blueprint; define a rollback runbook before production deploys."
                if not deployment
                else "Keep the previous artifact version and re-deploy it on failure."
            ),
        },
        "security_checks": ["dependency scan", "secret scanning (repo-level)", "SAST in a later stage"],
        "artifact_generation": [
            "Build the backend artifact from the repository.",
        ],
        "notifications": ["Not specified in the blueprint; add Slack/email notifications as needed."],
        "gaps": [
            "Deployment platform is not specified in the blueprint." if not deployment else "",
            "Frontend build pipeline is not specified in the blueprint." if not frontend else "",
        ],
        "context": context,
        "note": "No LLM provider configured; deterministic pipeline derived from the detected stack.",
    }


def _deterministic_sprint_plan(blueprint: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    """Deterministic sprint plan derived from roadmap milestones and features."""
    label = _domain_label(blueprint)
    roadmap = blueprint.get("roadmap") or {}
    analysis = blueprint.get("analysis") or {}
    milestones = roadmap.get("weekly_milestones") or []
    features = context.get("features") or []
    complexity = analysis.get("complexity_score") or {}

    epics: list[dict[str, Any]] = []
    tasks_by_sprint: list[dict[str, Any]] = []
    epic_id = 1
    task_id = 1

    for week, milestone in enumerate(milestones[:8], start=1):
        if not isinstance(milestone, dict):
            continue
        tasks = milestone.get("tasks") or []
        epic_name = milestone.get("theme") or f"Week {week}"
        epics.append(
            {
                "id": f"EPIC-{epic_id}",
                "name": str(epic_name)[:120],
                "description": str(milestone.get("goal") or "Milestone from the roadmap.")[:200],
                "source_sections": ["roadmap"],
                "priority": "Must Have" if week <= 2 else "Should Have",
                "estimated_effort": f"{week} week(s)",
                "dependencies": [f"EPIC-{epic_id - 1}"] if epic_id > 1 else [],
                "risks": [],
            }
        )
        sprint_tasks = []
        for task in tasks[:8]:
            if not isinstance(task, dict):
                continue
            sprint_tasks.append(
                {
                    "id": f"TASK-{task_id}",
                    "epic": f"EPIC-{epic_id}",
                    "title": str(task.get("task") or "Task")[:120],
                    "description": str(task.get("deliverable") or "")[:200],
                    "estimated_effort": f"{task.get('hours', '')}h" if task.get("hours") else "not specified",
                    "dependencies": [],
                    "assignee_role": (
                    "backend developer" if "data" in str(epic_name).lower() else "frontend developer"
                ),
                    "acceptance_criteria": ["Deliverable from the roadmap milestone."],
                }
            )
            task_id += 1
        tasks_by_sprint.append(
            {
                "sprint": week,
                "goal": f"Deliver: {str(epic_name)[:120]}",
                "epics": [f"EPIC-{epic_id}"],
                "tasks": sprint_tasks,
                "capacity_hours": 0,
                "planned_hours": 0,
            }
        )
        epic_id += 1

    if not epics:
        for feature in features[:6]:
            epics.append(
                {
                    "id": f"EPIC-{epic_id}",
                    "name": str(feature)[:120],
                    "description": "Feature from the project brief.",
                    "source_sections": ["features"],
                    "priority": "Must Have",
                    "estimated_effort": "not specified",
                    "dependencies": [f"EPIC-{epic_id - 1}"] if epic_id > 1 else [],
                    "risks": [],
                }
            )
            tasks_by_sprint.append(
                {
                    "sprint": epic_id,
                    "goal": f"Deliver: {str(feature)[:120]}",
                    "epics": [f"EPIC-{epic_id}"],
                    "tasks": [],
                    "capacity_hours": 0,
                    "planned_hours": 0,
                }
            )
            epic_id += 1

    level = complexity.get("level") if isinstance(complexity, dict) else None
    team_roles = [
        {"role": "backend developer", "count": 2 if level == "High" else 1, "focus": "API and data"},
        {"role": "frontend developer", "count": 2 if level == "High" else 1, "focus": "UI/UX"},
        {"role": "devops", "count": 1, "focus": "CI/CD and deployment"},
    ]

    return {
        "summary": (
            f"Deterministic sprint plan for {label}: {len(epics)} epics derived from "
            f"{'roadmap milestones' if milestones else 'project features'}. "
            "Effort estimates are not specified in the blueprint."
        ),
        "epics": epics,
        "sprints": tasks_by_sprint,
        "critical_path": [e["id"] for e in epics if e["dependencies"]],
        "total_estimated_effort": "not specified in the blueprint",
        "team_composition": team_roles,
        "gaps": [
            "Effort estimates are not specified in the blueprint.",
            "Capacity planning is not specified in the blueprint.",
        ],
        "context": context,
        "note": "No LLM provider configured; deterministic plan derived from roadmap/features.",
    }


def _deterministic_risk_register(blueprint: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    """Deterministic risk register derived from known/missing blueprint characteristics."""
    label = _domain_label(blueprint)
    api = blueprint.get("api") or {}
    deployment = blueprint.get("deployment") or {}
    security = blueprint.get("security") or {}
    analysis = blueprint.get("analysis") or {}
    roadmap = blueprint.get("roadmap") or {}

    risks: list[dict[str, Any]] = []
    rid = 1

    auth = (api.get("auth") or {}).get("method") if isinstance(api.get("auth"), dict) else None
    if not auth:
        risks.append(
            {
                "id": f"RISK-{rid}",
                "risk": (
                    "Authentication strategy is not specified in the blueprint; "
                    "implementation may ship without access control."
                ),
                "category": "security",
                "likelihood": "Medium",
                "impact": "High",
                "severity": "High",
                "mitigation": [
                    "Define an authentication method in the API specification "
                    "before implementation."
                ],
                "owner_role": "security engineer",
                "monitoring_signal": "Blueprint API section still has no auth method.",
                "source_sections": ["api"],
                "status": "open",
            }
        )
        rid += 1

    if not deployment:
        risks.append(
            {
                "id": f"RISK-{rid}",
                "risk": (
                    "Deployment configuration is not specified in the blueprint; "
                    "release and rollback are unplanned."
                ),
                "category": "operational",
                "likelihood": "Medium",
                "impact": "Medium",
                "severity": "Medium",
                "mitigation": ["Add a deployment & DevOps section with environments and rollback steps."],
                "owner_role": "devops",
                "monitoring_signal": "Blueprint has no deployment section.",
                "source_sections": ["deployment"],
                "status": "open",
            }
        )
        rid += 1

    if not security:
        risks.append(
            {
                "id": f"RISK-{rid}",
                "risk": (
                    "Security review is not specified in the blueprint; "
                    "vulnerabilities may be discovered late."
                ),
                "category": "security",
                "likelihood": "Medium",
                "impact": "High",
                "severity": "High",
                "mitigation": [
                    "Run the security-audit action and record controls in the security section."
                ],
                "owner_role": "security engineer",
                "monitoring_signal": "Blueprint security section is empty.",
                "source_sections": ["security"],
                "status": "open",
            }
        )
        rid += 1

    complexity = analysis.get("complexity_score") or {}
    if isinstance(complexity, dict) and complexity.get("level") == "High":
        risks.append(
            {
                "id": f"RISK-{rid}",
                "risk": "High complexity score indicates delivery risk (scope, integration, testing).",
                "category": "delivery",
                "likelihood": "Medium",
                "impact": "High",
                "severity": "High",
                "mitigation": [
                    "Break delivery into small, verifiable milestones; track the critical path."
                ],
                "owner_role": "product manager",
                "monitoring_signal": "Milestone slippage on the roadmap critical path.",
                "source_sections": ["analysis", "roadmap"],
                "status": "open",
            }
        )
        rid += 1

    if not roadmap:
        risks.append(
            {
                "id": f"RISK-{rid}",
                "risk": "Roadmap is not specified in the blueprint; team may lack sequencing.",
                "category": "delivery",
                "likelihood": "Low",
                "impact": "Medium",
                "severity": "Medium",
                "mitigation": ["Generate a project roadmap before planning sprints."],
                "owner_role": "product manager",
                "monitoring_signal": "Blueprint roadmap section is empty.",
                "source_sections": ["roadmap"],
                "status": "open",
            }
        )
        rid += 1

    if not risks:
        risks.append(
            {
                "id": "RISK-1",
                "risk": (
                    "No specific risk signals found in the blueprint; "
                    "treat this as a baseline, not a guarantee."
                ),
                "category": "technical",
                "likelihood": "Low",
                "impact": "Low",
                "severity": "Low",
                "mitigation": ["Re-run this action after blueprint changes."],
                "owner_role": "architect",
                "monitoring_signal": "Blueprint changes.",
                "source_sections": [],
                "status": "open",
            }
        )

    matrix = {"Low": 0, "Medium": 0, "High": 0, "Critical": 0}
    for risk in risks:
        matrix[risk["severity"]] = matrix.get(risk["severity"], 0) + 1

    return {
        "summary": (
            f"Deterministic risk register for {label}: {len(risks)} risks derived from "
            "known and missing blueprint characteristics. Severities are assessments "
            "of blueprint completeness, not confirmed incidents."
        ),
        "risks": risks,
        "risk_matrix": matrix,
        "top_risks": [r["id"] for r in risks if r["severity"] in ("High", "Critical")],
        "gaps": [
            "Likelihood and impact are deterministic estimates, not measurements.",
        ],
        "context": context,
        "note": "No LLM provider configured; deterministic risk analysis.",
    }


def _deterministic_compliance_map(
    blueprint: dict[str, Any], context: dict[str, Any]
) -> dict[str, Any]:
    """Deterministic compliance considerations derived from domain/data signals.

    Never claims legal compliance — everything is labelled "potentially
    relevant" with reasoning.
    """
    label = _domain_label(blueprint)
    domain = blueprint.get("domain_understanding") or {}
    identified = str(domain.get("identified_domain") or "").lower()
    analysis = blueprint.get("analysis") or {}

    domain_text = " ".join(
        [label, identified, str(analysis.get("problem_statement") or "")][:400]
    ).lower()

    frameworks: list[dict[str, Any]] = []
    data_classification: list[str] = []

    health_terms = ("health", "medical", "patient", "clinic", "hospital", "phi")
    if any(term in domain_text for term in health_terms):
        frameworks.append(
            {
                "framework": "HIPAA",
                "relevance": "potentially_relevant",
                "basis": "The domain involves health/patient data signals.",
                "controls": [
                    {
                        "control": "Access controls for protected health information",
                        "status": "not_assessed",
                        "evidence_required": ["Access control design", "Audit logs"],
                        "implementation_recommendation": (
                            "Confirm whether PHI is handled and engage qualified counsel."
                        ),
                        "blueprint_section": "api / database",
                    }
                ],
                "gaps": ["Whether PHI is actually processed is not specified in the blueprint."],
            }
        )
        data_classification.append("Possible PHI signals")
    payment_terms = ("payment", "card", "pci", "billing", "checkout")
    if any(term in domain_text for term in payment_terms):
        frameworks.append(
            {
                "framework": "PCI-DSS",
                "relevance": "potentially_relevant",
                "basis": "The domain involves payment/card data signals.",
                "controls": [
                    {
                        "control": "Secure handling of cardholder data",
                        "status": "not_assessed",
                        "evidence_required": ["Payment flow design", "Data flow diagram"],
                        "implementation_recommendation": (
                            "Route card processing through a PCI-compliant provider; "
                            "do not store PAN."
                        ),
                        "blueprint_section": "api",
                    }
                ],
                "gaps": ["Whether card data is stored is not specified in the blueprint."],
            }
        )
        data_classification.append("Possible cardholder data signals")
    if not frameworks:
        frameworks.append(
            {
                "framework": "GDPR",
                "relevance": "potentially_relevant",
                "basis": (
                    "General privacy regulation for applications handling EU "
                    "personal data; relevance depends on geography."
                ),
                "controls": [
                    {
                        "control": "Lawful basis and data subject rights",
                        "status": "not_assessed",
                        "evidence_required": ["Privacy policy", "Data inventory"],
                        "implementation_recommendation": (
                            "Identify whether personal data is processed and where users are located."
                        ),
                        "blueprint_section": "analysis / database",
                    }
                ],
                "gaps": ["Geography and personal-data handling are not specified in the blueprint."],
            }
        )
        data_classification.append("Personal data signals not specified")

    disclaimer = (
        "This analysis identifies potentially relevant compliance considerations based "
        "on the blueprint. It is not legal advice and does not constitute a compliance "
        "certification. Consult qualified legal counsel for definitive compliance "
        "determination."
    )

    return {
        "summary": (
            f"Deterministic compliance landscape for {label}: "
            f"{len(frameworks)} potentially relevant framework(s) identified from domain/data signals. "
            "No framework is claimed as required without confirmation."
        ),
        "frameworks": frameworks,
        "data_classification": ", ".join(data_classification),
        "jurisdiction_notes": [
            "User geography is not specified in the blueprint; jurisdiction cannot be confirmed."
        ],
        "disclaimer": disclaimer,
        "gaps": [
            "Geography, data residency and actual data types are not specified in the blueprint.",
            "This map is not a compliance audit.",
        ],
        "context": context,
        "note": "No LLM provider configured; deterministic compliance considerations.",
    }


def _analyze(
    action_id: str,
    blueprint: dict[str, Any],
    prompt: str,
    context: dict[str, Any],
    inputs: dict[str, Any],
    section: str | None = None,
    fallback: Callable[..., dict[str, Any]] | None = None,
) -> ActionResultOut:
    """Generic LLM + deterministic fallback for analysis actions."""
    warnings: list[str] = []
    llm = LLMClient(model_role="reasoning_secondary")
    if llm.available:
        try:
            user = f"BLUEPRINT\n```json\n{json.dumps(context, indent=2)[:30000]}\n```"
            result = llm.chat_json(prompt, user, max_tokens=4000)
            if isinstance(result, dict):
                return ActionResultOut(
                    action_id=action_id,
                    status="success",
                    result=result,
                    provider="llm",
                    warnings=warnings,
                    section=section,
                )
        except (LLMError, LLMNotConfiguredError) as exc:
            logger.info("analyze_action_llm_failed action=%s reason=%s", action_id, exc)
            warnings.append("The LLM provider failed; showing the deterministic summary instead.")
    if fallback is not None:
        fallback_result = fallback(blueprint, context)
    else:
        fallback_result = {
            "summary": f"Deterministic analysis for {action_id} (LLM unavailable).",
            "context": context,
            "note": "No LLM provider configured; showing the blueprint context for manual analysis.",
        }
    fallback_warnings = warnings or [
        "No LLM provider configured; showing the deterministic summary instead."
    ]
    return ActionResultOut(
        action_id=action_id,
        status="fallback",
        result=fallback_result,
        provider="deterministic",
        warnings=fallback_warnings,
        section=section,
    )


def _artifact_result(
    action_id: str,
    project: Project,
    builder: Callable[..., dict[str, str] | None],
    kind: str,
    filename: str,
) -> ActionResultOut:
    """Build a deterministic downloadable artifact for an action.

    Reuses the hardened ZIP path validation from the codegen pipeline; never
    embeds secrets. Returns ``validation_failed`` when the stack is too thin.
    """
    from app.services.actions.artifacts import safe_zip_path

    files = builder(project, project.blueprint or {})
    if not files:
        return ActionResultOut(
            action_id=action_id,
            status="validation_failed",
            message=(
                "Not enough stack information to generate this artifact. "
                "Add backend/frontend technology to the project."
            ),
            provider="deterministic",
        )
    manifest = []
    for path in sorted(files):
        safe_zip_path(path)
        manifest.append({"path": path, "bytes": len(files[path])})
    download_url = f"/api/v1/projects/{project.id}/actions/artifacts/{action_id}/download"
    return ActionResultOut(
        action_id=action_id,
        status="success",
        result={"files": manifest, "file_count": len(manifest), "generated_at": "deterministic"},
        provider="deterministic",
        artifact=ArtifactInfo(kind=kind, filename=filename, download_url=download_url),
    )


def security_audit(
    project: Project, blueprint: dict[str, Any], inputs: dict[str, Any], db: Session
) -> ActionResultOut:
    context = {
        "security": blueprint.get("security"),
        "architecture": blueprint.get("architecture"),
        "api": blueprint.get("api"),
        "database": blueprint.get("database"),
        "deployment": blueprint.get("deployment"),
        "domain": blueprint.get("domain_understanding"),
        "requirements": blueprint.get("analysis"),
        "technology": blueprint.get("technology_selection"),
    }
    return _analyze(
        "security-audit",
        blueprint,
        SECURITY_AUDIT_PROMPT,
        context,
        inputs,
        fallback=_deterministic_security_audit,
    )


def generate_test_strategy(
    project: Project, blueprint: dict[str, Any], inputs: dict[str, Any], db: Session
) -> ActionResultOut:
    context = {
        "testing": blueprint.get("testing"),
        "requirements": blueprint.get("analysis"),
        "architecture": blueprint.get("architecture"),
        "database": blueprint.get("database"),
        "api": blueprint.get("api"),
        "deployment": blueprint.get("deployment"),
    }
    if inputs.get("artifact") is True:
        return _artifact_result(
            "generate-test-strategy",
            project,
            lambda proj, bp: _build_test_scaffold(proj, bp),
            "test-scaffold",
            "test-scaffolding.zip",
        )
    return _analyze(
        "generate-test-strategy",
        blueprint,
        TEST_STRATEGY_PROMPT,
        context,
        inputs,
        section="testing",
        fallback=_deterministic_test_strategy,
    )


def generate_ci_cd(
    project: Project, blueprint: dict[str, Any], inputs: dict[str, Any], db: Session
) -> ActionResultOut:
    context = {
        "technology": blueprint.get("technology_selection"),
        "architecture": blueprint.get("architecture"),
        "deployment": blueprint.get("deployment"),
        "testing": blueprint.get("testing"),
        "code_stack": {
            "frontend": project.preferred_frontend,
            "backend": project.preferred_backend,
            "database": project.database,
            "deployment": project.deployment_platform,
        },
    }
    if inputs.get("artifact") is True:
        from app.services.actions.artifacts import build_ci_cd_artifact

        return _artifact_result(
            "generate-ci-cd",
            project,
            build_ci_cd_artifact,
            "ci-cd",
            "ci-cd-config.zip",
        )
    return _analyze(
        "generate-ci-cd",
        blueprint,
        CI_CD_PROMPT,
        context,
        inputs,
        section="deployment",
        fallback=lambda bp, ctx: _deterministic_ci_cd(bp, ctx, project),
    )


def generate_sprint_plan(
    project: Project, blueprint: dict[str, Any], inputs: dict[str, Any], db: Session
) -> ActionResultOut:
    context = {
        "requirements": blueprint.get("analysis"),
        "features": project.features,
        "roadmap": blueprint.get("roadmap"),
        "architecture": blueprint.get("architecture"),
        "database": blueprint.get("database"),
        "api": blueprint.get("api"),
        "complexity": blueprint.get("analysis", {}).get("complexity_score"),
    }
    return _analyze(
        "generate-sprint-plan",
        blueprint,
        SPRINT_PLAN_PROMPT,
        context,
        inputs,
        fallback=_deterministic_sprint_plan,
    )


def generate_risk_register(
    project: Project, blueprint: dict[str, Any], inputs: dict[str, Any], db: Session
) -> ActionResultOut:
    context = {
        "requirements": blueprint.get("analysis"),
        "architecture": blueprint.get("architecture"),
        "database": blueprint.get("database"),
        "api": blueprint.get("api"),
        "deployment": blueprint.get("deployment"),
        "domain": blueprint.get("domain_understanding"),
        "business_risks": blueprint.get("business_risks"),
        "security": blueprint.get("security"),
        "roadmap": blueprint.get("roadmap"),
        "technology": blueprint.get("technology_selection"),
    }
    return _analyze(
        "generate-risk-register",
        blueprint,
        RISK_REGISTER_PROMPT,
        context,
        inputs,
        section="business_risks",
        fallback=_deterministic_risk_register,
    )


def generate_compliance_map(
    project: Project, blueprint: dict[str, Any], inputs: dict[str, Any], db: Session
) -> ActionResultOut:
    context = {
        "domain": blueprint.get("domain_understanding"),
        "requirements": blueprint.get("analysis"),
        "security": blueprint.get("security"),
        "database": blueprint.get("database"),
        "deployment": blueprint.get("deployment"),
        "data_types": blueprint.get("analysis", {}).get("functional_requirements"),
    }
    return _analyze(
        "generate-compliance-map",
        blueprint,
        COMPLIANCE_MAP_PROMPT,
        context,
        inputs,
        fallback=_deterministic_compliance_map,
    )


def _build_test_scaffold(project: Project, blueprint: dict[str, Any]) -> dict[str, str] | None:
    """Deferred import shim so the executor stays import-light."""
    from app.services.actions.artifacts import build_test_scaffold

    return build_test_scaffold(project, blueprint)


# ---------------------------------------------------------------------------
# Central dispatch
# ---------------------------------------------------------------------------


def execute_action(action_id: str, project: Project, inputs: dict[str, Any], db: Session) -> ActionResultOut:
    """Run one action with the full result contract.

    The caller (API route or durable worker) already owns the project and
    normalized the blueprint. Handlers are wrapped so unexpected failures
    surface as a generic ``error`` result instead of a leaked exception.
    """
    from app.services.actions.registry import get_action

    action = get_action(action_id)
    if action is None:
        msg = f"Unknown action '{action_id}'."
        return ActionResultOut(action_id=action_id, status="validation_failed", message=msg)

    try:
        if action_id.startswith("generate-diagram-") or action_id.startswith("generate-"):
            inputs = {**inputs, "action_id": action_id}
        return action.handler(project, project.blueprint or {}, inputs, db)
    except ActionInputError as exc:
        return _validation_failed(action_id, str(exc))
    except Exception:  # noqa: BLE001 - never leak internals
        logger.exception("action_execution_failed action=%s project=%s", action_id, project.id)
        return ActionResultOut(action_id=action_id, status="error", message=GENERIC_ACTION_ERROR)
