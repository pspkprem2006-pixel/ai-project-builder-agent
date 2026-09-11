"""API endpoints for the Engineering Workspace download center.

Exposes a catalog of every downloadable artifact for a project, a combined
ZIP bundling all generated assets, and the importable API collections
(OpenAPI / Postman) derived from the blueprint.
"""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.database import get_db
from app.models.project import Project
from app.models.user import User
from app.services.blueprint_compat import BlueprintIncompatibleError, normalize_blueprint
from app.services.export.api_collection import COLLECTION_FORMATS, build_openapi, build_postman
from app.services.export.workspace import build_artifact_catalog, build_assets_zip

router = APIRouter(prefix="/projects", tags=["Workspace"])


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


@router.get("/{project_id}/workspace/artifacts")
def list_artifacts(
    project_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project = _get_blueprint(project_id, db, user)
    return build_artifact_catalog(project.id, project.name)


@router.get("/{project_id}/workspace/export")
def export_workspace(
    project_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project = _get_blueprint(project_id, db, user)
    content = build_assets_zip(project.name, _get_normalized_blueprint(project))
    return Response(
        content=content,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{_slug(project.name)}-assets.zip"'},
    )


@router.get("/{project_id}/api-collection")
def export_api_collection(
    project_id: int,
    format: str = "postman",
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project = _get_blueprint(project_id, db, user)
    if format not in COLLECTION_FORMATS:
        supported = ", ".join(COLLECTION_FORMATS)
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported format '{format}'. Use one of: {supported}",
        )
    blueprint = _get_normalized_blueprint(project)
    if format == "openapi":
        document = build_openapi(blueprint)
        suffix = "openapi"
    else:
        document = build_postman(blueprint)
        suffix = "postman"
    return Response(
        content=json.dumps(document, indent=2, ensure_ascii=False),
        media_type="application/json; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{_slug(project.name)}-{suffix}.json"'},
    )
