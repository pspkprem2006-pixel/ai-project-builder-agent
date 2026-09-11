"""Blueprint revision history, compare and safe rollback logic.

Every read here works on *section-level* snapshots only: revision entries
store the previous state of the section they changed, so the diff engine
never needs the whole blueprint and never produces whole-blueprint diffs.
History is append-only; restoring a revision creates a NEW revision entry
with ``source_action="restore-revision"`` and never rewrites the trail.
"""

from __future__ import annotations

import copy
from typing import Any

from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.models.blueprint_revision import BlueprintRevision
from app.models.project import Project
from app.models.user import User
from app.services.action_results import (
    _contains_secrets,
    _deserialize,
    create_blueprint_revision,
    get_blueprint_revisions,
)
from app.services.blueprint_compat import normalize_blueprint
from app.services.blueprint_diff import DiffItem, diff_json, summarize_diff

SOURCE_ACTION_RESTORE = "restore-revision"


class RevisionRestoreError(ValueError):
    """Expected restore failure (no snapshot, secrets, missing section)."""


def get_revision(
    db: Session,
    project_id: int,
    revision_number: int,
) -> BlueprintRevision | None:
    return (
        db.query(BlueprintRevision)
        .filter(
            BlueprintRevision.project_id == project_id,
            BlueprintRevision.revision == revision_number,
        )
        .first()
    )


def section_label(section: str) -> str:
    return section.replace("_", " ")


def _applied_by(db: Session, project_id: int, revision: BlueprintRevision) -> int | None:
    """Resolve the user who caused a revision.

    Action-triggered revisions carry ``applied_by`` directly; for older
    rows (created before the column existed) it falls back to the linked
    action result.
    """
    if revision.applied_by is not None:
        return revision.applied_by
    return _applied_by_from_result(db, project_id, revision.action_result_id)


def _applied_by_from_result(db: Session, project_id: int, action_result_id: int) -> int | None:
    from app.models.action_result import ActionResult

    row = (
        db.query(ActionResult.applied_by)
        .filter(
            ActionResult.id == action_result_id,
            ActionResult.project_id == project_id,
        )
        .first()
    )
    return row[0] if row else None


def _after_state(db: Session, project: Project, revision: BlueprintRevision) -> Any:
    """Section state immediately after *revision* was applied.

    Walks back through every later revision that touched the same section,
    restoring their ``previous_section`` snapshots in reverse order. If no
    later revision touched the section, the current blueprint section is
    the state after the revision.
    """
    blueprint = normalize_blueprint(project.blueprint or {})
    state = copy.deepcopy(blueprint.get(revision.section))
    later = (
        db.query(BlueprintRevision.revision, BlueprintRevision.previous_section)
        .filter(
            BlueprintRevision.project_id == project.id,
            BlueprintRevision.section == revision.section,
            BlueprintRevision.revision > revision.revision,
        )
        .order_by(BlueprintRevision.revision.desc())
        .all()
    )
    for _number, previous in later:
        snapshot = _deserialize(previous)
        if snapshot is not None:
            state = copy.deepcopy(snapshot)
    return state


def _change(
    db: Session,
    project: Project,
    revision: BlueprintRevision,
) -> dict[str, Any]:
    """Diff + summary for the change *revision* itself introduced."""
    before = _deserialize(revision.previous_section)
    after = _after_state(db, project, revision)
    items = diff_json(before, after)
    summary = _summary_with_lead(revision.section, items)
    return {
        "before": before,
        "after": after,
        "changed": items,
        "summary": summary,
    }


def _summary_with_lead(section: str, items: list[DiffItem]) -> list[str]:
    if not items:
        return []
    return [f"Changed {section_label(section)} section"] + summarize_diff(items)


def list_revisions_with_summary(
    db: Session,
    project: Project,
    limit: int,
    offset: int,
) -> tuple[list[dict[str, Any]], int]:
    """Paginated revision list, newest first, each with a computed summary.

    Summaries are computed with a single batched query across the project's
    revision trail (per-section next-snapshot lookup), so listing stays
    cheap regardless of history length.
    """
    revisions, total = get_blueprint_revisions(db, project.id, limit, offset)

    rows = (
        db.query(
            BlueprintRevision.revision,
            BlueprintRevision.section,
            BlueprintRevision.previous_section,
        )
        .filter(BlueprintRevision.project_id == project.id)
        .order_by(BlueprintRevision.revision)
        .all()
    )
    by_section: dict[str, list[tuple[int, str | None]]] = {}
    for number, section, previous in rows:
        by_section.setdefault(section, []).append((number, previous))

    blueprint = normalize_blueprint(project.blueprint or {})
    items: list[dict[str, Any]] = []
    for revision in revisions:
        after: Any = copy.deepcopy(blueprint.get(revision.section))
        for number, previous in by_section.get(revision.section, []):
            if number > revision.revision:
                snapshot = _deserialize(previous)
                if snapshot is not None:
                    after = copy.deepcopy(snapshot)
        before = _deserialize(revision.previous_section)
        items_list = diff_json(before, after)
        items.append(
            {
                "revision": revision.revision,
                "created_at": revision.created_at.isoformat(),
                "source_action": revision.source_action,
                "section": revision.section,
                "action_result_id": revision.action_result_id,
                "applied_by": revision.applied_by,
                "summary": _summary_with_lead(revision.section, items_list),
            }
        )
    return items, total


def revision_detail(
    db: Session,
    project: Project,
    revision: BlueprintRevision,
) -> dict[str, Any]:
    blueprint = normalize_blueprint(project.blueprint or {})
    change = _change(db, project, revision)
    return {
        "revision": revision.revision,
        "created_at": revision.created_at.isoformat(),
        "source_action": revision.source_action,
        "section": revision.section,
        "action_result_id": revision.action_result_id,
        "applied_by": _applied_by(db, project.id, revision),
        "previous_section": _deserialize(revision.previous_section),
        "current_section": copy.deepcopy(blueprint.get(revision.section)),
        "changed": change["changed"],
        "summary": change["summary"],
    }


def _change_entry(
    db: Session,
    project: Project,
    revision: BlueprintRevision,
) -> dict[str, Any]:
    change = _change(db, project, revision)
    return {
        "revision": revision.revision,
        "created_at": revision.created_at.isoformat(),
        "source_action": revision.source_action,
        "section": revision.section,
        "action_result_id": revision.action_result_id,
        "applied_by": _applied_by(db, project.id, revision),
        "before": change["before"],
        "after": change["after"],
        "changed": change["changed"],
        "summary": change["summary"],
    }


def compare_revisions(
    db: Session,
    project: Project,
    from_revision: BlueprintRevision,
    to_revision: BlueprintRevision,
) -> dict[str, Any]:
    """Compare two revisions (consecutive or not, any order, same or different).

    Each side reports its own section/state/diff. When both revisions
    touched the same section, ``combined`` carries the net change between
    the state at ``from_revision`` and the state at ``to_revision``.
    """
    from_entry = _change_entry(db, project, from_revision)
    to_entry = _change_entry(db, project, to_revision)

    combined = None
    if from_revision.section == to_revision.section:
        combined_items = diff_json(from_entry["after"], to_entry["after"])
        combined = {
            **from_entry,
            "revision": to_revision.revision,
            "before": from_entry["after"],
            "after": to_entry["after"],
            "changed": combined_items,
            "summary": _summary_with_lead(to_revision.section, combined_items),
        }

    return {
        "from_revision": from_entry,
        "to_revision": to_entry,
        "combined": combined,
    }


def restore_revision(
    db: Session,
    project: Project,
    revision: BlueprintRevision,
    user: User,
) -> BlueprintRevision:
    """Restore *revision*'s section snapshot as a NEW revision.

    - Only the section that revision changed is touched.
    - The snapshot is validated before it is written (secrets are rejected,
      placeholders such as ``${{ secrets.X }}`` remain allowed).
    - The new revision records the pre-restore section state, so the restore
      itself is part of the history and fully reversible.
    - One database transaction: the unique (project_id, revision) index
      makes concurrent restores/applies safe (loser gets IntegrityError).
    """
    snapshot = _deserialize(revision.previous_section)
    if snapshot is None:
        raise RevisionRestoreError("No snapshot is available for this revision.")
    if not isinstance(snapshot, dict):
        raise RevisionRestoreError("The stored snapshot for this revision is not a section.")
    if _contains_secrets(snapshot):
        raise RevisionRestoreError(
            "The snapshot contains secret-like values and cannot be restored."
        )

    blueprint = project.blueprint
    if not isinstance(blueprint, dict) or revision.section not in blueprint:
        raise RevisionRestoreError(
            f"Section '{revision.section}' is no longer present in the blueprint."
        )

    previous = copy.deepcopy(blueprint[revision.section])
    blueprint[revision.section] = copy.deepcopy(snapshot)
    project.blueprint = blueprint
    flag_modified(project, "blueprint")

    return create_blueprint_revision(
        db=db,
        project=project,
        section=revision.section,
        source_action=SOURCE_ACTION_RESTORE,
        action_result_id=revision.action_result_id,
        previous_section=previous,
        applied_by=user.id,
    )


def restore_message(new_revision: BlueprintRevision, source: BlueprintRevision) -> str:
    return (
        f"Revision {new_revision.revision} created. "
        f"{section_label(source.section)} restored from Revision {source.revision}."
    )
