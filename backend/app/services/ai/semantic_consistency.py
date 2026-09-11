"""Semantic Consistency Checker.

Compares every blueprint section against the project's Domain Context and
produces a per-section PASS/FAIL report plus a semantic consistency score.
Any forbidden vocabulary — entities, terminology or workflows from another
domain — flags the section for regeneration.

The checker is deterministic and vocabulary-based: it runs after every
generation (LLM or template) and can also be invoked per section during the
regeneration workflow.
"""

from __future__ import annotations

import json
from typing import Any

from app.services.ai.domain_context import build_domain_context, find_forbidden_terms

# Section key -> human-readable label used in the report.
SEMANTIC_SECTIONS: dict[str, str] = {
    "analysis": "Requirements",
    "domain_understanding": "Domain Understanding",
    "business_processes": "Business Processes",
    "architecture": "Architecture",
    "database": "Database",
    "api": "API Design",
    "ui_ux": "UI",
    "roadmap": "Roadmap",
    "testing": "Testing",
    "deployment": "Deployment",
    "documentation": "Documentation",
}


def _section_blob(blueprint: dict[str, Any], section: str) -> str:
    return json.dumps(blueprint.get(section, {}), ensure_ascii=False, default=str)


def domain_context_for(blueprint: dict[str, Any]) -> dict[str, Any] | None:
    """Resolve the Domain Context stored on the blueprint.

    Falls back to rebuilding it from the stored project input so the checker
    also works on blueprints generated before the context object existed or on
    hand-assembled blueprints that carry a ``project`` block.
    """
    metadata = blueprint.get("metadata") or {}
    ctx = metadata.get("domain_context")
    if isinstance(ctx, dict) and ctx.get("forbidden_vocabulary"):
        return ctx
    project = blueprint.get("project")
    if isinstance(project, dict):
        input_data = {
            "name": project.get("name", ""),
            "description": project.get("description", ""),
            "category": project.get("category", ""),
            "target_users": "",
            "features": list(project.get("features", []) or []),
            "preferred_frontend": "",
            "preferred_backend": "",
            "database": "",
            "auth_method": "JWT",
            "deployment_platform": "",
        }
        return build_domain_context(input_data)
    return None


def scan_section(section: str, blueprint: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
    """Check one section against the Domain Context."""
    forbidden = ctx.get("forbidden_vocabulary", [])
    hits = find_forbidden_terms(_section_blob(blueprint, section), forbidden)
    status = "PASS" if not hits else "FAIL"
    reason = (
        "No cross-domain vocabulary detected."
        if not hits
        else f"Contains terminology from another domain: {', '.join(hits)}."
    )
    return {
        "section": section,
        "label": SEMANTIC_SECTIONS.get(section, section),
        "status": status,
        "forbidden_terms": hits,
        "reason": reason,
    }


def semantic_consistency_review(blueprint: dict[str, Any]) -> dict[str, Any]:
    """Compare every section against the Domain Context and score consistency."""
    ctx = domain_context_for(blueprint)
    if ctx is None:
        return {
            "semantic_score": None,
            "report": [],
            "warnings": [],
            "skipped": True,
        }

    report = [scan_section(section, blueprint, ctx) for section in SEMANTIC_SECTIONS]
    passed = [r for r in report if r["status"] == "PASS"]
    failed = [r for r in report if r["status"] == "FAIL"]
    total = len(report)
    score = int(round(100 * len(passed) / total)) if total else 100

    warnings = []
    for entry in failed:
        warnings.append(
            f"{entry['label']} references another domain: {', '.join(entry['forbidden_terms'])}."
        )

    return {
        "semantic_score": score,
        "report": report,
        "warnings": warnings,
        "skipped": False,
        "overall": "Consistent" if not failed else f"{len(failed)} section(s) contain cross-domain content",
    }


def failing_sections(blueprint: dict[str, Any]) -> list[str]:
    """Sections that currently reference vocabulary from another domain."""
    review = semantic_consistency_review(blueprint)
    return [entry["section"] for entry in review["report"] if entry["status"] == "FAIL"]
