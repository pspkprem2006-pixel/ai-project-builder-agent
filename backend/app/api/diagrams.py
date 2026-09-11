"""API endpoints for the diagram generation agent.

Diagrams are rendered from the stored blueprint on every request, so they
always reflect the latest blueprint — regeneration is automatic whenever the
blueprint changes.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.database import get_db
from app.models.project import Project
from app.models.user import User
from app.services.blueprint_compat import BlueprintIncompatibleError, normalize_blueprint
from app.services.diagrams.registry import DIAGRAMS, generate_diagram

router = APIRouter(prefix="/projects", tags=["Diagrams"])

EXPORT_FORMATS = {"mmd": "text/vnd.mermaid", "md": "text/markdown"}


class DiagramOut(BaseModel):
    id: str
    label: str
    description: str
    category: str
    format: str = "mermaid"


class DiagramSourceOut(BaseModel):
    id: str
    title: str
    format: str = "mermaid"
    source: str
    generated_at: str
    blueprint_generated_at: str | None


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


def _blueprint_generated_at(project: Project) -> str | None:
    blueprint = project.blueprint or {}
    metadata = blueprint.get("metadata") or {}
    generated_at = metadata.get("generated_at")
    if generated_at:
        return str(generated_at)
    return project.updated_at.isoformat() if project.updated_at else None


@router.get("/{project_id}/diagrams", response_model=list[DiagramOut])
def list_diagrams(
    project_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _get_blueprint(project_id, db, user)
    return [
        DiagramOut(
            id=diagram_id,
            label=info["label"],
            description=info["description"],
            category=info["category"],
        )
        for diagram_id, info in DIAGRAMS.items()
    ]


@router.get("/{project_id}/diagrams/{diagram_id}", response_model=DiagramSourceOut)
def get_diagram_source(
    project_id: int,
    diagram_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project = _get_blueprint(project_id, db, user)
    if diagram_id not in DIAGRAMS:
        raise HTTPException(status_code=404, detail=f"Unknown diagram '{diagram_id}'")
    source = generate_diagram(diagram_id, _get_normalized_blueprint(project))
    return DiagramSourceOut(
        id=diagram_id,
        title=DIAGRAMS[diagram_id]["label"],
        source=source,
        generated_at=datetime.now(UTC).isoformat(),
        blueprint_generated_at=_blueprint_generated_at(project),
    )


@router.get("/{project_id}/diagrams/{diagram_id}/export")
def export_diagram(
    project_id: int,
    diagram_id: str,
    format: str = "mmd",
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project = _get_blueprint(project_id, db, user)
    if diagram_id not in DIAGRAMS:
        raise HTTPException(status_code=404, detail=f"Unknown diagram '{diagram_id}'")
    if format not in EXPORT_FORMATS:
        supported = ", ".join(EXPORT_FORMATS)
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported export format '{format}'. Use one of: {supported}",
        )
    source = generate_diagram(diagram_id, _get_normalized_blueprint(project))
    if format == "md":
        body = f"```mermaid\n{source}\n```\n"
        media_type = EXPORT_FORMATS["md"]
    else:
        body = source
        media_type = EXPORT_FORMATS["mmd"]
    slug = "".join(c if c.isalnum() or c in "-_" else "-" for c in project.name.lower())[:60] or "project"
    return Response(
        content=body,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{slug}-{diagram_id}.{format}"'},
    )
