"""Blueprint revision history — API contracts.

The revision system is a lightweight, application-level version trail for
section-level blueprint changes. Every apply (and every restore) creates a
new revision entry; history is never rewritten, only appended. All diffs and
summaries are produced deterministically by the diff engine — never by an LLM.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

DiffOp = Literal["add", "remove", "change"]


class DiffItemOut(BaseModel):
    """One deterministic difference (path is relative to a section)."""

    op: DiffOp
    path: list[str] = Field(default_factory=list)
    before: Any = None
    after: Any = None


class RevisionOut(BaseModel):
    """Lightweight revision entry for listing."""

    revision: int
    created_at: str
    source_action: str
    section: str
    action_result_id: int | None = None
    applied_by: int | None = None
    summary: list[str] = Field(default_factory=list)


class RevisionListOut(BaseModel):
    items: list[RevisionOut]
    total: int
    limit: int
    offset: int


class RevisionDetailOut(BaseModel):
    """Full revision detail: metadata, snapshots and a deterministic diff."""

    revision: int
    created_at: str
    source_action: str
    section: str
    action_result_id: int | None = None
    applied_by: int | None = None
    previous_section: Any = None
    current_section: Any = None
    changed: list[DiffItemOut] = Field(default_factory=list)
    summary: list[str] = Field(default_factory=list)


class RevisionChangeEntry(BaseModel):
    """One side of a revision comparison (before/after + diff)."""

    revision: int
    created_at: str
    source_action: str
    section: str
    action_result_id: int | None = None
    applied_by: int | None = None
    before: Any = None
    after: Any = None
    changed: list[DiffItemOut] = Field(default_factory=list)
    summary: list[str] = Field(default_factory=list)


class RevisionCompareOut(BaseModel):
    """Compare two revisions (consecutive or not, same section or not).

    ``combined`` is only populated when both revisions touched the same
    section: it is the net change between the state at ``from_revision``
    and the state at ``to_revision``.
    """

    from_revision: RevisionChangeEntry
    to_revision: RevisionChangeEntry
    combined: RevisionChangeEntry | None = None


class RevisionRestoreRequest(BaseModel):
    """Request to restore a revision's section snapshot as a NEW revision.

    ``expected_current_revision`` is an optional optimistic-concurrency
    guard: if the blueprint has moved past it, the restore is rejected
    with 409 so a stale client can never clobber newer work.
    """

    confirm: bool = False
    expected_current_revision: int | None = None


class RevisionRestoreResponse(BaseModel):
    success: bool
    message: str
    revision: int
    section: str
