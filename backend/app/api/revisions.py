"""Blueprint revision history — HTTP surface.

    GET  /projects/{id}/revisions                    → list (paginated)
    GET  /projects/{id}/revisions/compare            → compare two revisions
    GET  /projects/{id}/revisions/{revision}         → detail + deterministic diff
    POST /projects/{id}/revisions/{revision}/restore → safe rollback (new revision)

Ownership is enforced identically to every other project endpoint: a
foreign user sees 404, never 403 or 200.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.actions import _get_owned_project
from app.api.deps import get_current_user, get_db
from app.models.user import User
from app.schemas.revision import (
    RevisionCompareOut,
    RevisionDetailOut,
    RevisionListOut,
    RevisionRestoreRequest,
    RevisionRestoreResponse,
)
from app.services.action_results import get_current_blueprint_revision
from app.services.revisions import (
    RevisionRestoreError,
    compare_revisions,
    get_revision,
    list_revisions_with_summary,
    restore_message,
    restore_revision,
    revision_detail,
)

router = APIRouter(prefix="/projects", tags=["Blueprint Revisions"])


@router.get("/{project_id}/revisions", response_model=RevisionListOut)
def list_revisions(
    project_id: int,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project = _get_owned_project(project_id, db, user)
    items, total = list_revisions_with_summary(db, project, limit, offset)
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@router.get("/{project_id}/revisions/compare", response_model=RevisionCompareOut)
def compare_revision(
    project_id: int,
    from_revision: int = Query(..., ge=1),
    to_revision: int = Query(..., ge=1),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project = _get_owned_project(project_id, db, user)
    from_rev = get_revision(db, project.id, from_revision)
    if from_rev is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Revision {from_revision} not found",
        )
    to_rev = get_revision(db, project.id, to_revision)
    if to_rev is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Revision {to_revision} not found",
        )
    return compare_revisions(db, project, from_rev, to_rev)


@router.get("/{project_id}/revisions/{revision_number}", response_model=RevisionDetailOut)
def get_revision_detail(
    project_id: int,
    revision_number: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project = _get_owned_project(project_id, db, user)
    revision = get_revision(db, project.id, revision_number)
    if revision is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Revision {revision_number} not found",
        )
    return revision_detail(db, project, revision)


@router.post(
    "/{project_id}/revisions/{revision_number}/restore",
    response_model=RevisionRestoreResponse,
)
def restore_revision_endpoint(
    project_id: int,
    revision_number: int,
    payload: RevisionRestoreRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project = _get_owned_project(project_id, db, user)
    revision = get_revision(db, project.id, revision_number)
    if revision is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Revision {revision_number} not found",
        )

    if not payload.confirm:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Confirmation required to restore a revision.",
        )

    current = get_current_blueprint_revision(db, project.id)
    if payload.expected_current_revision is not None and payload.expected_current_revision != current:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"The blueprint has moved on to revision {current}, but "
                f"{payload.expected_current_revision} was expected. "
                "Refresh the revision history and try again."
            ),
        )

    try:
        new_revision = restore_revision(db, project, revision, user)
    except RevisionRestoreError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from None
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Another blueprint update happened concurrently. "
                "Refresh the revision history and try again."
            ),
        ) from None

    return RevisionRestoreResponse(
        success=True,
        message=restore_message(new_revision, revision),
        revision=new_revision.revision,
        section=new_revision.section,
    )
