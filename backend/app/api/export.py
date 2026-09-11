from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.database import get_db
from app.models.project import Project
from app.models.user import User
from app.services.blueprint_compat import BlueprintIncompatibleError, normalize_blueprint
from app.services.export.exporters import to_docx, to_json, to_pdf, to_zip
from app.services.export.markdown import render_blueprint

router = APIRouter(prefix="/projects", tags=["Export"])

FORMATS: dict[str, tuple[str, str]] = {
    "markdown": ("text/markdown; charset=utf-8", "md"),
    "json": ("application/json; charset=utf-8", "json"),
    "zip": ("application/zip", "zip"),
    "pdf": ("application/pdf", "pdf"),
    "docx": ("application/vnd.openxmlformats-officedocument.wordprocessingml.document", "docx"),
}


@router.get("/{project_id}/export")
def export_project(
    project_id: int,
    format: str = "markdown",
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project = db.get(Project, project_id)
    if project is None or project.user_id != user.id:
        raise HTTPException(status_code=404, detail="Project not found")
    if project.blueprint is None:
        raise HTTPException(status_code=400, detail="Project has no blueprint yet. Generate it first.")
    if format not in FORMATS:
        raise HTTPException(status_code=400, detail=f"Unsupported format. Choose from: {', '.join(FORMATS)}")

    try:
        blueprint = normalize_blueprint(project.blueprint)
    except BlueprintIncompatibleError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    media_type, ext = FORMATS[format]
    slug = "".join(c if c.isalnum() or c in "-_" else "-" for c in project.name.lower())[:60]

    if format == "markdown":
        content = render_blueprint(blueprint).encode("utf-8")
    elif format == "json":
        content = to_json(blueprint)
    elif format == "zip":
        content = to_zip(blueprint)
    elif format == "pdf":
        content = to_pdf(blueprint)
    else:
        content = to_docx(blueprint)

    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{slug}-blueprint.{ext}"'},
    )
