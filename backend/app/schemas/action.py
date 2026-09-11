"""AI Action Engine — API contracts.

The action engine exposes a small, uniform surface over the existing
generation, diagram and code-generation services. Every action returns the
same result envelope so the frontend can distinguish success, deterministic
fallback, validation failures and LLM failures without parsing section shapes.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

ActionStatus = Literal[
    "success",
    "fallback",  # deterministic fallback used (no LLM, or LLM failed)
    "validation_failed",
    "llm_failed",
    "error",
    "accepted",  # long-running action: a durable job was created
]

QualityStatus = Literal["valid", "invalid", "partial"]


class ActionMetaOut(BaseModel):
    """Static metadata for one action, used for discovery and the UI."""

    id: str
    name: str
    category: Literal["analysis", "transformation", "diagram", "code", "documentation"]
    description: str
    execution_mode: Literal["short", "long"]
    mutates_project: bool
    supports_fallback: bool
    requires_blueprint: bool
    inputs: dict[str, Any] = {}
    apply_mode: Literal["none", "patch", "replace", "merge"] = "none"
    depends_on: list[str] = Field(default_factory=list)


class ActionCatalogOut(BaseModel):
    items: list[ActionMetaOut]


class ActionExecuteRequest(BaseModel):
    """Per-action inputs. Validated by each action's input schema."""

    inputs: dict[str, Any] = Field(default_factory=dict, max_length=50)


class ArtifactInfo(BaseModel):
    kind: Literal["codegen-zip", "diagram", "ci-cd", "test-scaffold"] = "codegen-zip"
    filename: str
    download_url: str


class ActionResultOut(BaseModel):
    action_id: str
    status: ActionStatus
    message: str | None = None
    result: dict[str, Any] | None = None
    section: str | None = None
    warnings: list[str] = Field(default_factory=list)
    provider: str | None = None
    artifact: ArtifactInfo | None = None
    job_id: int | None = None
    quality: QualityStatus | None = None
    completeness: int | None = None
    consistency_status: str | None = None


class ActionHistoryItem(BaseModel):
    """Lightweight action history entry for listing."""

    id: int
    action_id: str
    action_name: str
    status: str
    provider: str | None = None
    section: str | None = None
    warning_count: int = 0
    applied: bool = False
    applied_at: str | None = None
    created_at: str
    completed_at: str | None = None
    quality: QualityStatus | None = None
    completeness: int | None = None


class ActionHistoryOut(BaseModel):
    items: list[ActionHistoryItem]
    total: int
    limit: int
    offset: int


class ActionDetailOut(BaseModel):
    """Full action result detail."""

    id: int
    project_id: int
    action_id: str
    status: str
    input: dict[str, Any] | None = None
    result: dict[str, Any] | None = None
    section: str | None = None
    warnings: list[str] = Field(default_factory=list)
    provider: str | None = None
    blueprint_revision: int
    applied: bool = False
    applied_at: str | None = None
    applied_by: int | None = None
    created_at: str
    completed_at: str | None = None
    quality: QualityStatus | None = None
    completeness: int | None = None
    consistency_status: str | None = None


class ActionApplyRequest(BaseModel):
    """Request to apply an action result to the blueprint."""

    confirm: bool = True


class ActionApplyResponse(BaseModel):
    """Response after applying an action result."""

    success: bool
    message: str
    revision: int | None = None
    section: str | None = None
