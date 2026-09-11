"""Registry of code generators exposed through the API.

Each generator receives the structured blueprint dict and returns a mapping of
``file path -> file content``.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from app.services.codegen.backend import generate_express, generate_fastapi
from app.services.codegen.database import generate_prisma, generate_sql, generate_sqlalchemy
from app.services.codegen.frontend import generate_nextjs, generate_react
from app.services.codegen.spring import generate_spring

GeneratorFn = Callable[[dict[str, Any]], dict[str, str]]


class GeneratorInfo:
    def __init__(self, generator_id: str, label: str, description: str, section: str, files: int) -> None:
        self.id = generator_id
        self.label = label
        self.description = description
        self.section = section
        self.files = files


GENERATORS: dict[str, dict[str, Any]] = {
    "sql": {
        "label": "SQL (PostgreSQL)",
        "description": "Complete PostgreSQL schema: tables, indexes, constraints, migrations and seed data.",
        "section": "database",
        "handler": generate_sql,
    },
    "prisma": {
        "label": "Prisma Schema",
        "description": "Prisma ORM schema with models, relations and a seed script.",
        "section": "database",
        "handler": generate_prisma,
    },
    "sqlalchemy": {
        "label": "SQLAlchemy Models",
        "description": "SQLAlchemy 2.0 models, database setup and Alembic scaffolding.",
        "section": "database",
        "handler": generate_sqlalchemy,
    },
    "fastapi": {
        "label": "FastAPI",
        "description": "FastAPI REST API with JWT auth, CRUD, validation, tests and Swagger.",
        "section": "backend",
        "handler": generate_fastapi,
    },
    "express": {
        "label": "Express.js",
        "description": "Express.js REST API with JWT auth, Zod validation, tests and OpenAPI docs.",
        "section": "backend",
        "handler": generate_express,
    },
    "spring": {
        "label": "Spring Boot",
        "description": "Spring Boot 3 API with JWT security, JPA, validation, tests and Swagger.",
        "section": "backend",
        "handler": generate_spring,
    },
    "react": {
        "label": "React (Vite)",
        "description": "React SPA with routing, JWT login, dashboard and CRUD screens.",
        "section": "frontend",
        "handler": generate_react,
    },
    "nextjs": {
        "label": "Next.js",
        "description": "Next.js App Router application with auth pages, dashboard and CRUD screens.",
        "section": "frontend",
        "handler": generate_nextjs,
    },
}


def generator_files(generator_id: str, blueprint: dict[str, Any]) -> dict[str, str]:
    """Run a generator by id, returning the file map."""
    generator = GENERATORS.get(generator_id)
    if generator is None:
        raise KeyError(f"Unknown generator: {generator_id}")
    return generator["handler"](blueprint)


def generator_manifest(generator_id: str, blueprint: dict[str, Any]) -> list[dict[str, str | int]]:
    files = generator_files(generator_id, blueprint)
    return [{"path": path, "bytes": len(content.encode("utf-8"))} for path, content in files.items()]
