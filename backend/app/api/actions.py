"""AI Action Engine — HTTP surface.

    GET  /projects/{id}/actions                → action catalog (discovery)
    POST /projects/{id}/actions/{action_id}    → execute (short: synchronous
                                                 result; long: 202 + durable job)

Long-running action status and cancellation reuse the existing job endpoints
(``GET /projects/{id}/jobs``, ``GET .../jobs/{job_id}``, ``POST .../cancel``)
because durable action jobs ride the same worker machinery as generation.
"""

from __future__ import annotations

import contextlib
import logging
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.api.deps import get_current_user, get_db
from app.models.project import Project
from app.models.user import User
from app.schemas.action import (
    ActionApplyRequest,
    ActionApplyResponse,
    ActionCatalogOut,
    ActionDetailOut,
    ActionExecuteRequest,
    ActionHistoryItem,
    ActionHistoryOut,
    ActionMetaOut,
    ActionResultOut,
)
from app.services.action_results import (
    action_result_to_dict,
    create_action_result,
    create_blueprint_revision,
    get_action_result,
    get_current_blueprint_revision,
)
from app.services.actions.executor import execute_action
from app.services.actions.registry import ACTION_REGISTRY, get_action
from app.services.generation_jobs import create_action_job

router = APIRouter(prefix="/projects", tags=["AI Actions"])


def _get_owned_project(project_id: int, db: Session, user: User):
    from app.models.project import Project

    project = db.get(Project, project_id)
    if project is None or project.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return project


def _require_blueprint(project) -> None:
    if project.blueprint is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Project has no blueprint yet. Generate it first.",
        )


@router.get("/{project_id}/actions", response_model=ActionCatalogOut)
def list_actions(
    project_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Discover every action available for a project (ownership checked)."""
    _get_owned_project(project_id, db, user)
    return ActionCatalogOut(
        items=[
            ActionMetaOut(
                id=action.id,
                name=action.name,
                category=action.category,
                description=action.description,
                execution_mode=action.execution_mode,
                mutates_project=action.mutates_project,
                supports_fallback=action.supports_fallback,
                requires_blueprint=action.requires_blueprint,
                inputs=action.inputs,
                apply_mode=action.apply_mode,
                depends_on=action.depends_on,
            )
            for action in ACTION_REGISTRY.values()
        ]
    )


@router.post("/{project_id}/actions/{action_id}", response_model=ActionResultOut)
def execute_action_route(
    project_id: int,
    action_id: str,
    payload: ActionExecuteRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Execute one AI action against the project's blueprint.

    Short actions run synchronously inside this request. Long-running actions
    are enqueued as durable generation jobs (same worker/lease/retry machinery)
    and return ``accepted`` with a ``job_id``.
    """
    action = ACTION_REGISTRY.get(action_id)
    if action is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Unknown action '{action_id}'.")
    project = _get_owned_project(project_id, db, user)
    if action.requires_blueprint:
        _require_blueprint(project)

    if action.execution_mode == "long":
        from sqlalchemy.exc import IntegrityError

        try:
            job = create_action_job(db, project.id, action_id, payload.inputs)
        except IntegrityError:
            # One active job per project (generation or action): the durable
            # worker guarantees atomic blueprint writes, so a second job cannot
            # start while another is running.
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A job is already running for this project. Wait for it to finish.",
            ) from None
        return ActionResultOut(
            action_id=action_id,
            status="accepted",
            message="Action queued. Poll the project or job for status.",
            job_id=job.id,
        )

    result = execute_action(action_id, project, payload.inputs or {}, db)
    result.action_id = action_id
    if result.status == "error":
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=result.message)
    if result.status == "validation_failed":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=result.message or f"Invalid inputs for action '{action_id}'.",
        )

    # Persist action result for history
    from app.services.action_results import (
        create_action_result,
        get_current_blueprint_revision,
    )

    revision = get_current_blueprint_revision(db, project.id)
    create_action_result(
        db=db,
        project=project,
        action_id=action_id,
        status=result.status,
        input_data=payload.inputs,
        result_data=result.result,
        section=result.section,
        warnings=result.warnings,
        provider=result.provider,
        blueprint_revision=revision,
        artifact_available=result.artifact is not None,
    )

    return result


@router.get("/{project_id}/actions/history", response_model=ActionHistoryOut)
def list_action_history(
    project_id: int,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """List action execution history for a project."""
    _get_owned_project(project_id, db, user)

    from app.services.action_results import list_action_results

    results, total = list_action_results(db, project_id, limit=limit, offset=offset)


    items = []
    for r in results:
        action = get_action(r.action_id)
        warning_count = 0
        if r.warnings:
            import json

            with contextlib.suppress(TypeError, ValueError):
                warning_count = len(json.loads(r.warnings))
        items.append(
            ActionHistoryItem(
                id=r.id,
                action_id=r.action_id,
                action_name=action.name if action else r.action_id,
                status=r.status,
                provider=r.provider,
                section=r.section,
                warning_count=warning_count,
                applied=r.applied,
                applied_at=r.applied_at.isoformat() if r.applied_at else None,
                created_at=r.created_at.isoformat(),
                completed_at=r.completed_at.isoformat() if r.completed_at else None,
                quality=r.quality,
                completeness=r.completeness,
            )
        )

    return ActionHistoryOut(items=items, total=total, limit=limit, offset=offset)


@router.get("/{project_id}/actions/history/{result_id}", response_model=ActionDetailOut)
def get_action_history_detail(
    project_id: int,
    result_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Get full details of an action execution result."""
    _get_owned_project(project_id, db, user)


    result = get_action_result(db, project_id, result_id)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Action result not found")

    return ActionDetailOut(**action_result_to_dict(result))


def _safe_merge_section(existing: dict[str, Any], new_data: dict[str, Any], mode: str) -> dict[str, Any]:
    """Safely merge new data into existing section based on mode.

    - patch/merge: recursive merge, preserving existing keys not in new_data
    - replace: completely replace the section
    """
    import copy
    result = copy.deepcopy(existing)

    if mode == "replace":
        return new_data

    # patch/merge: recursively merge dicts, preserve other keys
    def merge_dict(target: dict, source: dict) -> dict:
        for key, value in source.items():
            if key in target and isinstance(target[key], dict) and isinstance(value, dict):
                target[key] = merge_dict(target[key], value)
            else:
                target[key] = value
        return target

    return merge_dict(result, new_data)


def _check_dependencies(action_id: str, blueprint: dict[str, Any], db: Session) -> tuple[bool, list[str]]:
    """Check if action dependencies are satisfied in the blueprint.

    Returns (dependencies_satisfied, missing_sections).
    """

    action = get_action(action_id)
    if not action or not action.depends_on:
        return True, []

    missing = []
    for dep in action.depends_on:
        if dep not in blueprint or not blueprint[dep]:
            missing.append(dep)

    return len(missing) == 0, missing


@router.post("/{project_id}/actions/history/{result_id}/apply", response_model=ActionApplyResponse)
def apply_action_result(
    project_id: int,
    result_id: int,
    payload: ActionApplyRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Apply an action result to the project blueprint.

    Only actions with apply_mode != 'none' can be applied.
    The result must not be stale (blueprint revision must match).
    Dependencies must be satisfied.
    Result must pass validation.
    """
    from app.services.action_results import (
        _validate_action_result,
        get_action_result,
        get_current_blueprint_revision,
    )

    _get_owned_project(project_id, db, user)

    result = get_action_result(db, project_id, result_id)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Action result not found")

    action = get_action(result.action_id)
    if action is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Action not found")

    if action.apply_mode == "none":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Action '{result.action_id}' does not support blueprint application.",
        )

    if result.applied:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This action result has already been applied to the blueprint.",
        )

    # Check for stale result
    current_revision = get_current_blueprint_revision(db, project_id)
    if result.blueprint_revision != current_revision:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Action result is based on blueprint revision {result.blueprint_revision}, "
                f"but current revision is {current_revision}. Please re-run the action."
            ),
        )

    # Check dependencies
    project = db.get(Project, project_id)
    if project is None or project.blueprint is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Project has no blueprint")

    deps_ok, missing = _check_dependencies(result.action_id, project.blueprint, db)
    if not deps_ok:
        missing_sections = ", ".join(missing)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Action '{result.action_id}' requires missing sections: "
                f"{missing_sections}. Generate them first."
            ),
        )

    # Validate result before applying
    result_data = result.result
    if isinstance(result_data, str):
        import json
        try:
            result_data = json.loads(result_data)
        except (TypeError, ValueError):
            result_data = {}

    valid, errors = _validate_action_result(result.action_id, result_data, result.section, project.blueprint)
    if not valid:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="; ".join(errors),
        )

    if not payload.confirm:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Confirmation required to apply action result.",
        )

    # Store previous section for revision (deep copy)
    previous_section = None
    if result.section and result.section in project.blueprint:
        import copy
        previous_section = copy.deepcopy(project.blueprint[result.section])

    # Apply the result to the blueprint using safe merge
    blueprint = project.blueprint
    applicable_modes = ("patch", "merge", "replace")
    if result.section and isinstance(result_data, dict) and action.apply_mode in applicable_modes:
        # Only modify the intended section, preserve others byte-for-byte
        blueprint[result.section] = _safe_merge_section(
            blueprint.get(result.section, {}),
            result_data,
            action.apply_mode,
        )

    # Mark blueprint as modified and persist
    project.blueprint = blueprint
    flag_modified(project, "blueprint")

    # Create revision entry and mark applied in ONE transaction. The unique
    # (project_id, revision) index makes concurrent applies safe: exactly one
    # request wins the revision number; the loser rolls back atomically.
    try:
        create_blueprint_revision(
            db=db,
            project=project,
            section=result.section or "unknown",
            source_action=result.action_id,
            action_result_id=result.id,
            previous_section=previous_section,
            applied_by=user.id,
        )
        result.applied = True
        result.applied_at = datetime.utcnow()
        result.applied_by = user.id
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Another blueprint update happened concurrently. "
                "Re-run the action and apply the fresh result."
            ),
        ) from None

    return ActionApplyResponse(
        success=True,
        message=f"Applied {action.name} to blueprint section '{result.section or 'project'}'",
        revision=current_revision + 1,
        section=result.section,
    )


@router.post("/{project_id}/actions/{action_id}/artifact", response_model=ActionResultOut)
def generate_action_artifact(
    project_id: int,
    action_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Generate a deterministic downloadable artifact for an artifact-capable action.

    Only ``generate-ci-cd`` (CI/CD workflows) and ``generate-test-strategy``
    (test scaffolding) support artifacts, and only when the blueprint stack
    contains enough information. No LLM is used and no secrets are ever
    embedded. The generated artifact record appears in the action history.
    """
    from app.services.actions.artifacts import ARTIFACT_ACTIONS, build_ci_cd_artifact, build_test_scaffold

    if action_id not in ARTIFACT_ACTIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Action '{action_id}' does not support artifact generation.",
        )
    project = _get_owned_project(project_id, db, user)
    _require_blueprint(project)

    builder = build_ci_cd_artifact if action_id == "generate-ci-cd" else build_test_scaffold
    files = builder(project, project.blueprint or {})
    if not files:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Not enough stack information to generate this artifact. "
                "Add backend/frontend technology to the project first."
            ),
        )

    revision = get_current_blueprint_revision(db, project.id)
    manifest = [{"path": path, "bytes": len(files[path])} for path in sorted(files)]
    kind = ARTIFACT_ACTIONS[action_id]
    download_url = f"/api/v1/projects/{project_id}/actions/artifacts/{action_id}/download"

    create_action_result(
        db=db,
        project=project,
        action_id=action_id,
        status="success",
        input_data={"artifact": True},
        result_data={"files": manifest, "file_count": len(manifest)},
        section=None,
        warnings=[],
        provider="deterministic",
        blueprint_revision=revision,
        artifact_available=True,
    )

    from app.schemas.action import ArtifactInfo

    return ActionResultOut(
        action_id=action_id,
        status="success",
        message=f"Artifact generated: {len(manifest)} file(s).",
        result={"files": manifest, "file_count": len(manifest)},
        provider="deterministic",
        artifact=ArtifactInfo(
            kind=kind,
            filename="ci-cd-config.zip" if action_id == "generate-ci-cd" else "test-scaffolding.zip",
            download_url=download_url,
        ),
    )


@router.get("/{project_id}/actions/artifacts/{action_id}/download")
def download_action_artifact(
    project_id: int,
    action_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Download a deterministic artifact as a hardened ZIP archive.

    The archive is rebuilt on demand from the current blueprint using the
    same path-safe ZIP pipeline as code generation. Ownership is required.
    """
    from fastapi.responses import Response

    from app.services.actions.artifacts import ARTIFACT_ACTIONS, build_ci_cd_artifact, build_test_scaffold
    from app.services.codegen.base import build_zip

    if action_id not in ARTIFACT_ACTIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Action '{action_id}' does not support artifact generation.",
        )
    project = _get_owned_project(project_id, db, user)
    _require_blueprint(project)

    builder = build_ci_cd_artifact if action_id == "generate-ci-cd" else build_test_scaffold
    files = builder(project, project.blueprint or {})
    if not files:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Not enough stack information to generate this artifact.",
        )
    try:
        zip_bytes = build_zip(files)
    except Exception:  # noqa: BLE001 - never leak internals
        logging.getLogger("action_engine").exception(
            "artifact_zip_failed action=%s project=%s", action_id, project_id
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Artifact generation failed unexpectedly. Please try again later.",
        ) from None
    filename = "ci-cd-config.zip" if action_id == "generate-ci-cd" else "test-scaffolding.zip"
    return Response(
        content=zip_bytes,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
