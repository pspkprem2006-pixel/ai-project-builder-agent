"""API endpoints for the AI code generation engine.

Consumes the stored blueprint and returns generated starter projects as
downloadable ZIP archives.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.database import get_db
from app.models.project import Project
from app.models.user import User
from app.services.blueprint_compat import BlueprintIncompatibleError, normalize_blueprint
from app.services.codegen.base import build_zip
from app.services.codegen.registry import GENERATORS, generator_files, generator_manifest

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/projects", tags=["Codegen"])


class GeneratorOut(BaseModel):
    id: str
    label: str
    description: str
    section: str


class ManifestFile(BaseModel):
    path: str
    bytes: int


class ManifestOut(BaseModel):
    generator: str
    files: list[ManifestFile]
    total_bytes: int


def _get_blueprint(project_id: int, db: Session, user: User) -> Project:
    project = db.get(Project, project_id)
    if project is None or project.user_id != user.id:
        raise HTTPException(status_code=404, detail="Project not found")
    if project.blueprint is None:
        raise HTTPException(status_code=400, detail="Project has no blueprint yet. Generate it first.")
    return project


def _get_normalized_blueprint(project: Project) -> dict:
    """Canonicalize the stored blueprint, mapping expected incompatibilities to HTTP 400."""
    try:
        return normalize_blueprint(project.blueprint)
    except BlueprintIncompatibleError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _safe_generator_call(project_id: int, generator_id: str, blueprint: dict, *, manifest: bool):
    """Run a generator, splitting expected failures from unexpected bugs.

    Expected failures (invalid blueprint data, unknown generator) become
    HTTP 400/404; unexpected exceptions are logged and become a generic
    HTTP 500 that never leaks internals.
    """
    try:
        if manifest:
            return generator_manifest(generator_id, blueprint)
        return generator_files(generator_id, blueprint)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception(
            "Unexpected code generation failure: generator=%s project_id=%s manifest=%s",
            generator_id,
            project_id,
            manifest,
        )
        raise HTTPException(
            status_code=500,
            detail="Code generation failed unexpectedly. Please try again later.",
        ) from exc


@router.get("/{project_id}/codegen/generators", response_model=list[GeneratorOut])
def list_generators(
    project_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _get_blueprint(project_id, db, user)
    return [
        GeneratorOut(id=gid, label=info["label"], description=info["description"], section=info["section"])
        for gid, info in GENERATORS.items()
    ]


@router.get("/{project_id}/codegen/{generator_id}/manifest", response_model=ManifestOut)
def generator_manifest_endpoint(
    project_id: int,
    generator_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project = _get_blueprint(project_id, db, user)
    if generator_id not in GENERATORS:
        raise HTTPException(status_code=404, detail=f"Unknown generator '{generator_id}'")
    blueprint = _get_normalized_blueprint(project)
    files = _safe_generator_call(project_id, generator_id, blueprint, manifest=True)
    return ManifestOut(
        generator=generator_id,
        files=[ManifestFile(**f) for f in files],
        total_bytes=sum(f["bytes"] for f in files),
    )


@router.get("/{project_id}/codegen/{generator_id}")
def download_generated_project(
    project_id: int,
    generator_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project = _get_blueprint(project_id, db, user)
    if generator_id not in GENERATORS:
        raise HTTPException(status_code=404, detail=f"Unknown generator '{generator_id}'")
    blueprint = _get_normalized_blueprint(project)

    files = _safe_generator_call(project_id, generator_id, blueprint, manifest=False)
    try:
        zip_bytes = build_zip(files)
    except Exception as exc:
        logger.exception(
            "Unexpected code generation packaging failure: generator=%s project_id=%s",
            generator_id,
            project_id,
        )
        raise HTTPException(
            status_code=500,
            detail="Code generation failed unexpectedly. Please try again later.",
        ) from exc
    slug = "".join(c if c.isalnum() or c in "-_" else "-" for c in project.name.lower())[:60]
    return Response(
        content=zip_bytes,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{slug}-{generator_id}.zip"'},
    )
