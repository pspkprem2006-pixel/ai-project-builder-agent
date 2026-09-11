from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=5000)
    category: str = Field(default="General", max_length=200)
    target_users: str = Field(default="", max_length=2000)
    features: list[str] = Field(default_factory=list, max_length=100)
    preferred_frontend: str = Field(default="React", max_length=200)
    preferred_backend: str = Field(default="FastAPI", max_length=200)
    database: str = Field(default="PostgreSQL", max_length=200)
    auth_method: str = Field(default="JWT", max_length=200)
    deployment_platform: str = Field(default="Docker", max_length=200)
    language: str = Field(default="TypeScript", max_length=200)


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    category: str | None = Field(default=None, max_length=200)
    target_users: str | None = Field(default=None, max_length=2000)
    features: list[str] | None = Field(default=None, max_length=100)
    preferred_frontend: str | None = Field(default=None, max_length=200)
    preferred_backend: str | None = Field(default=None, max_length=200)
    database: str | None = Field(default=None, max_length=200)
    auth_method: str | None = Field(default=None, max_length=200)
    deployment_platform: str | None = Field(default=None, max_length=200)
    language: str | None = Field(default=None, max_length=200)


class ProjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    name: str
    description: str
    category: str
    target_users: str
    features: list[str]
    preferred_frontend: str
    preferred_backend: str
    database: str
    auth_method: str
    deployment_platform: str
    language: str
    status: str
    blueprint: dict[str, Any] | None
    ai_provider: str
    generation_error: str | None
    created_at: datetime
    updated_at: datetime
    last_generated_at: datetime | None


class ProjectListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str
    category: str
    status: str
    ai_provider: str
    preferred_frontend: str
    preferred_backend: str
    database: str
    created_at: datetime
    updated_at: datetime
    last_generated_at: datetime | None


class ProjectListOut(BaseModel):
    items: list[ProjectListItem]
    total: int
    page: int
    page_size: int


class ProjectStatistics(BaseModel):
    total_projects: int
    completed: int
    in_progress: int
    drafts: int
    by_category: dict[str, int]
    by_status: dict[str, int]
    by_stack: dict[str, int]
    last_generated_at: datetime | None


class AISuggestion(BaseModel):
    title: str
    detail: str
    category: str


class GenerateResponse(BaseModel):
    status: str
    detail: str
    project_id: int
    job_id: int | None = None


class GenerationJobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    status: str
    current_stage: str
    progress: int
    attempt_count: int
    error_message: str | None = None
    created_at: datetime | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None


class RegenerateSectionRequest(BaseModel):
    section: str = Field(min_length=1, max_length=64)


class TemplatesOut(BaseModel):
    templates: list[ProjectCreate]


class ExportResponse(BaseModel):
    filename: str
    format: str
