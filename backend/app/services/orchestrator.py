"""Blueprint orchestration service.

Coordinates the multi-agent pipeline and persists results onto a Project.

Execution is durable: the HTTP layer only creates a ``GenerationJob``; a
dedicated worker process claims and runs the pipeline (see
``app.services.generation_jobs`` and ``app.worker``).
"""
from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.models.project import Project
from app.services.ai.agents import regenerate_section as regenerate_section_agent
from app.services.ai.reasoning import generate_blueprint
from app.services.memory import get_memory_store


def project_to_input(project: Project) -> dict[str, Any]:
    return {
        "name": project.name,
        "description": project.description,
        "category": project.category,
        "target_users": project.target_users,
        "features": project.features or [],
        "preferred_frontend": project.preferred_frontend,
        "preferred_backend": project.preferred_backend,
        "database": project.database,
        "auth_method": project.auth_method,
        "deployment_platform": project.deployment_platform,
        "language": project.language,
    }


def persist_blueprint(db: Session, project: Project, blueprint: dict[str, Any], provider: str) -> Project:
    """Persist a finished blueprint onto the project and mark it complete.

    Called by the generation worker after ``run_pipeline`` succeeds.
    """
    blueprint["project"] = {
        "id": project.id,
        "name": project.name,
        "description": project.description,
        "category": project.category,
        "features": project.features,
        "stack": {
            "frontend": project.preferred_frontend,
            "backend": project.preferred_backend,
            "database": project.database,
            "auth": project.auth_method,
            "deployment": project.deployment_platform,
        },
    }
    blueprint["metadata"] = {
        **(blueprint.get("metadata") or {}),
        "generated_at": datetime.now(UTC).isoformat(),
        "provider": provider,
        "version": "3.0",
    }
    project.blueprint = blueprint
    project.ai_provider = provider
    project.status = "complete"
    project.last_generated_at = datetime.now(UTC)
    project.generation_error = None

    from contextlib import suppress

    with suppress(Exception):
        get_memory_store().add(
            project.id,
            project.user_id,
            f"{project.name}: {project.description[:150]}",
            blueprint,
        )
    db.commit()
    return project


def regenerate_section_for_project(db: Session, project: Project, section: str) -> Project:
    """Regenerate a single blueprint section and re-run the blueprint review.

    ``regenerate_section`` mutates ``project.blueprint`` in place, so the
    re-assignment below is identity-identical and SQLAlchemy would otherwise
    skip the flush — mark the JSON column modified explicitly.
    """
    from sqlalchemy.orm.attributes import flag_modified

    blueprint = regenerate_section_agent(section, project.blueprint or {}, project_to_input(project))
    project.blueprint = blueprint
    flag_modified(project, "blueprint")
    project.status = "complete"
    project.generation_error = None
    project.last_generated_at = datetime.now(UTC)
    db.commit()
    return project


def duplicate_project(db: Session, source: Project, name: str | None = None) -> Project:
    """Create a copy of a project including its blueprint."""
    copy = Project(
        user_id=source.user_id,
        name=(name or f"{source.name} (copy)")[:200],
        description=source.description,
        category=source.category,
        target_users=source.target_users,
        features=source.features,
        preferred_frontend=source.preferred_frontend,
        preferred_backend=source.preferred_backend,
        database=source.database,
        auth_method=source.auth_method,
        deployment_platform=source.deployment_platform,
        language=source.language,
        status=source.status,
        blueprint=json.loads(json.dumps(source.blueprint)) if source.blueprint else None,
        ai_provider=source.ai_provider,
    )
    db.add(copy)
    db.commit()
    db.refresh(copy)
    return copy


def template_preview(input_data: dict[str, Any]) -> dict[str, Any]:
    """Generate a preview blueprint without persisting anything."""
    return generate_blueprint(input_data)
