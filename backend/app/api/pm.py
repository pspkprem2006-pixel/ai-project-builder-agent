"""API endpoints for the project management generator.

The PM model (epics, user stories, sprints, issues, milestones, dependencies,
critical path and burndown estimates) is regenerated from the stored blueprint
on every request, so it always stays synchronized with it.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.database import get_db
from app.models.project import Project
from app.models.user import User
from app.services.blueprint_compat import BlueprintIncompatibleError, normalize_blueprint
from app.services.pm import exporters
from app.services.pm.generator import generate_pm

router = APIRouter(prefix="/projects", tags=["Project Management"])

MEDIA_TYPES = {"json": "application/json", "md": "text/markdown", "csv": "text/csv"}


def _get_blueprint(project_id: int, db: Session, user: User) -> Project:
    project = db.get(Project, project_id)
    if project is None or project.user_id != user.id:
        raise HTTPException(status_code=404, detail="Project not found")
    if project.blueprint is None:
        raise HTTPException(status_code=400, detail="Project has no blueprint yet. Generate it first.")
    return project


def _get_normalized_blueprint(project: Project) -> dict:
    try:
        return normalize_blueprint(project.blueprint)
    except BlueprintIncompatibleError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _slug(name: str) -> str:
    slug = "".join(c if c.isalnum() or c in "-_" else "-" for c in name.lower())[:60]
    return slug or "project"


@router.get("/{project_id}/pm")
def get_pm(
    project_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project = _get_blueprint(project_id, db, user)
    model = generate_pm(_get_normalized_blueprint(project))
    model["generated_at"] = datetime.now(UTC).isoformat()
    blueprint = project.blueprint or {}
    metadata = blueprint.get("metadata") or {}
    model["blueprint_generated_at"] = metadata.get("generated_at") or (
        project.updated_at.isoformat() if project.updated_at else None
    )
    return model


@router.get("/{project_id}/pm/export")
def export_pm(
    project_id: int,
    format: str = "json",
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project = _get_blueprint(project_id, db, user)
    if format not in exporters.EXPORT_FORMATS:
        supported = ", ".join(exporters.EXPORT_FORMATS)
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported export format '{format}'. Use one of: {supported}",
        )
    model = generate_pm(_get_normalized_blueprint(project))
    body = exporters.export(model, format)
    slug = _slug(project.name)
    return Response(
        content=body,
        media_type=MEDIA_TYPES[format],
        headers={"Content-Disposition": f'attachment; filename="{slug}-project-management.{format}"'},
    )
