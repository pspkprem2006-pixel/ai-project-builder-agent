"""Action Result persistence service.

Provides CRUD operations for action results with project ownership enforcement.
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any

from sqlalchemy import desc, func
from sqlalchemy.orm import Session

from app.models.action_result import ActionResult
from app.models.blueprint_revision import BlueprintRevision
from app.models.project import Project


def _serialize(data: Any) -> str | None:
    if data is None:
        return None
    return json.dumps(data)


def _deserialize(text: str | None) -> Any:
    if text is None:
        return None
    try:
        return json.loads(text)
    except (TypeError, ValueError):
        return None


def _classify_quality(
    result_data: dict[str, Any] | None,
    status: str,
    warnings: list[str] | None,
) -> tuple[str, int | None, str | None]:
    """Classify action result quality based on deterministic signals.

    Returns (quality, completeness, consistency_status).
    """
    if status in ("error", "validation_failed"):
        return "invalid", None, "failed"

    if result_data is None:
        return "invalid", 0, "no_data"

    if status == "fallback":
        # Fallback results have context but no LLM analysis
        if "context" in result_data and "note" in result_data:
            return "partial", 50, "fallback_only"
        return "partial", 40, "fallback_only"

    # Success status - evaluate result structure
    completeness = 0

    # Check for expected keys based on action type (would need action_id)
    # For now, do generic structural checks
    if isinstance(result_data, dict):
        has_summary = (
            isinstance(result_data.get("summary"), str) and result_data["summary"].strip()
        )
        if has_summary:
            completeness += 20
        if "warnings" in result_data and isinstance(result_data["warnings"], list):
            completeness += 10
        if len(result_data) >= 3:
            completeness += 20
        if len(result_data) >= 5:
            completeness += 20
        if len(result_data) >= 8:
            completeness += 20
        completeness = min(completeness, 100)

    if warnings:
        completeness = max(0, completeness - len(warnings) * 5)

    if completeness >= 80:
        quality = "valid"
        consistency_status = "consistent"
    elif completeness >= 50:
        quality = "partial"
        consistency_status = "partial"
    else:
        quality = "invalid"
        consistency_status = "incomplete"

    return quality, completeness, consistency_status


_SECRET_VALUE_PATTERNS = (
    # Assignment/JSON-style values for secret-like keys (quoted, 8+ chars).
    # The optional quote before the separator covers JSON keys ("password": "…")
    # as well as plain-text assignments (password: "…").
    r"(?i)(api[_-]?key|secret[_-]?key|password|private[_-]?key|token|credential|bearer)"
    r"['\"]?\s*[=:]\s*['\"][A-Za-z0-9+/_\-\.]{8,}['\"]",
    # Well-known secret prefixes / long tokens (sk-…, ghp_…, AKIA…, Bearer …).
    r"(?i)sk-[A-Za-z0-9]{16,}",
    r"(?i)ghp_[A-Za-z0-9]{20,}",
    r"(?i)AKIA[0-9A-Z]{16}",
    r"(?i)Bearer\s+[A-Za-z0-9._\-]{20,}",
)


def _contains_secrets(data: Any) -> bool:
    """Detect actual secret VALUES embedded in result data.

    Merely discussing "tokens", "passwords" or "secrets" as topics is NOT a
    leak; only literal secret-like values (``password="abc123…"``, ``sk-…``,
    ``Bearer …``) are rejected. ``${{ secrets.X }}`` references are fine.
    """
    if data is None:
        return False
    text = str(data)
    return any(re.search(pattern, text) for pattern in _SECRET_VALUE_PATTERNS)


def _has_unsafe_path(data: Any) -> bool:
    """True if any string VALUE looks like a traversal or absolute path.

    Only values that themselves are paths are flagged (e.g. ``"../etc/passwd"``,
    ``"..\\secrets"``, ``"C:\\Users\\..."``). Incidental mid-text occurrences
    (Docker ``build: ../frontend``, ``postgres:\\n`` JSON escapes, command
    strings) must never block a legitimate apply.
    """
    if isinstance(data, dict):
        return any(_has_unsafe_path(value) for value in data.values())
    if isinstance(data, list):
        return any(_has_unsafe_path(value) for value in data)
    if isinstance(data, str):
        stripped = data.strip()
        if stripped.startswith("../") or stripped.startswith("..\\"):
            return True
        if re.match(r"^[A-Za-z]:[\\/]", stripped):
            return True
    return False


def _validate_action_result(
    action_id: str,
    result_data: dict[str, Any] | None,
    section: str | None,
    blueprint: dict[str, Any] | None,
) -> tuple[bool, list[str]]:
    """Validate action result before applying to blueprint.

    Returns (is_valid, error_messages).
    """
    errors = []

    if result_data is None:
        errors.append("Result data is empty")
        return False, errors

    if not isinstance(result_data, dict):
        errors.append("Result must be a JSON object")
        return False, errors

    # Validate section exists in blueprint if specified
    if section and blueprint and section not in blueprint:
        errors.append(f"Section '{section}' does not exist in blueprint")
        return False, errors

    # Check for secrets
    if _contains_secrets(result_data):
        errors.append("Result contains potential secrets or credentials")
        return False, errors

    # Check for unsafe paths (traversal-style values only)
    if _has_unsafe_path(result_data):
        errors.append("Result contains potentially unsafe paths")
        return False, errors

    # Validate expected structure for applicable actions
    applicable_actions = {
        "improve-requirements": ["analysis"],
        "generate-architecture": ["architecture"],
        "generate-database-design": ["database"],
        "generate-project-roadmap": ["roadmap"],
        "generate-test-strategy": ["testing"],
        "generate-risk-register": ["business_risks"],
        "generate-ci-cd": ["deployment"],
    }

    if action_id in applicable_actions and section:
        expected_sections = applicable_actions[action_id]
        if section not in expected_sections:
            errors.append(f"Action '{action_id}' cannot apply to section '{section}'")
            return False, errors

    return len(errors) == 0, errors


def create_action_result(
    db: Session,
    project: Project,
    action_id: str,
    status: str,
    input_data: dict[str, Any] | None,
    result_data: dict[str, Any] | None,
    section: str | None,
    warnings: list[str] | None,
    provider: str | None,
    blueprint_revision: int,
    artifact_available: bool = False,
) -> ActionResult:
    """Persist an action execution result."""
    quality, completeness, consistency_status = _classify_quality(result_data, status, warnings)

    action_result = ActionResult(
        project_id=project.id,
        action_id=action_id,
        status=status,
        input=_serialize(input_data),
        result=_serialize(result_data),
        section=section,
        warnings=_serialize(warnings),
        provider=provider,
        blueprint_revision=blueprint_revision,
        completed_at=(
            datetime.utcnow() if status in ("success", "fallback", "error", "validation_failed") else None
        ),
        quality=quality,
        completeness=completeness,
        consistency_status=consistency_status,
        artifact_available=artifact_available,
    )
    db.add(action_result)
    db.commit()
    db.refresh(action_result)
    return action_result


def mark_artifact_available(db: Session, result_id: int, project_id: int) -> ActionResult | None:
    """Mark an action result as having a downloadable artifact."""
    result = get_action_result(db, project_id, result_id)
    if result is None:
        return None
    result.artifact_available = True
    db.commit()
    db.refresh(result)
    return result


def mark_applied(
    db: Session,
    result: ActionResult,
    user_id: int | None = None,
) -> ActionResult:
    """Mark an action result as applied to the blueprint."""
    result.applied = True
    result.applied_at = datetime.utcnow()
    if user_id is not None:
        result.applied_by = user_id
    db.commit()
    db.refresh(result)
    return result


def get_action_result(db: Session, project_id: int, result_id: int) -> ActionResult | None:
    """Get an action result by ID, ensuring it belongs to the project."""
    return (
        db.query(ActionResult)
        .filter(ActionResult.id == result_id, ActionResult.project_id == project_id)
        .first()
    )


def list_action_results(
    db: Session,
    project_id: int,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[ActionResult], int]:
    """List action results for a project with pagination."""
    query = db.query(ActionResult).filter(ActionResult.project_id == project_id)
    total = query.count()
    items = query.order_by(desc(ActionResult.created_at)).offset(offset).limit(limit).all()
    return items, total


def get_current_blueprint_revision(db: Session, project_id: int) -> int:
    """Get the current blueprint revision number for a project."""
    max_rev = (
        db.query(func.max(BlueprintRevision.revision))
        .filter(BlueprintRevision.project_id == project_id)
        .scalar()
    )
    return max_rev or 0


def create_blueprint_revision(
    db: Session,
    project: Project,
    section: str,
    source_action: str,
    action_result_id: int | None,
    previous_section: dict[str, Any] | None,
    applied_by: int | None = None,
) -> BlueprintRevision:
    """Create a new blueprint revision entry."""
    revision = get_current_blueprint_revision(db, project.id) + 1
    bp_revision = BlueprintRevision(
        project_id=project.id,
        revision=revision,
        section=section,
        source_action=source_action,
        action_result_id=action_result_id,
        previous_section=_serialize(previous_section),
        applied_by=applied_by,
    )
    db.add(bp_revision)
    db.commit()
    db.refresh(bp_revision)
    return bp_revision


def get_blueprint_revisions(
    db: Session,
    project_id: int,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[BlueprintRevision], int]:
    """List blueprint revisions for a project with pagination."""
    query = db.query(BlueprintRevision).filter(BlueprintRevision.project_id == project_id)
    total = query.count()
    items = query.order_by(desc(BlueprintRevision.created_at)).offset(offset).limit(limit).all()
    return items, total


def action_result_to_dict(result: ActionResult) -> dict[str, Any]:
    """Convert ActionResult model to dict for API responses."""
    return {
        "id": result.id,
        "project_id": result.project_id,
        "action_id": result.action_id,
        "status": result.status,
        "input": _deserialize(result.input),
        "result": _deserialize(result.result),
        "section": result.section,
        "warnings": _deserialize(result.warnings),
        "provider": result.provider,
        "blueprint_revision": result.blueprint_revision,
        "applied": result.applied,
        "applied_at": result.applied_at.isoformat() if result.applied_at else None,
        "applied_by": result.applied_by,
        "created_at": result.created_at.isoformat(),
        "completed_at": result.completed_at.isoformat() if result.completed_at else None,
        "quality": result.quality,
        "completeness": result.completeness,
        "consistency_status": result.consistency_status,
    }


def blueprint_revision_to_dict(rev: BlueprintRevision) -> dict[str, Any]:
    """Convert BlueprintRevision model to dict for API responses."""
    return {
        "id": rev.id,
        "project_id": rev.project_id,
        "revision": rev.revision,
        "section": rev.section,
        "source_action": rev.source_action,
        "action_result_id": rev.action_result_id,
        "previous_section": _deserialize(rev.previous_section),
        "applied_by": rev.applied_by,
        "created_at": rev.created_at,
    }
