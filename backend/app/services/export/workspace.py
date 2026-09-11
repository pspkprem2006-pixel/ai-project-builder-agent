"""Engineering Workspace: artifact catalog and combined project export.

The download center lists every generated asset (blueprint, code, diagrams,
documentation, sprint board, database scripts, API collection) and can bundle
them all into a single project ZIP.
"""

from __future__ import annotations

import io
import json
import re
import zipfile
from typing import Any

from app.config import get_settings
from app.services.codegen.base import build_zip
from app.services.codegen.registry import GENERATORS, generator_files
from app.services.diagrams.registry import DIAGRAMS, generate_diagram
from app.services.export.api_collection import build_openapi, build_postman
from app.services.export.exporters import to_json
from app.services.export.markdown import render_blueprint
from app.services.pm import exporters as pm_exporters
from app.services.pm.generator import generate_pm


def _slug(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug or "project"


def _prefix(path: str) -> str:
    return get_settings().API_V1_PREFIX + path


def build_artifact_catalog(project_id: int, name: str) -> dict[str, Any]:
    """Catalog of every downloadable artifact for the download center UI."""
    slug = _slug(name)
    p = f"/projects/{project_id}"
    return {
        "project_id": project_id,
        "project_name": name,
        "zip_href": _prefix(f"{p}/workspace/export"),
        "groups": [
            {
                "id": "blueprint",
                "label": "Blueprint",
                "description": "The complete software blueprint as a document.",
                "items": [
                    {
                        "id": "markdown",
                        "label": "Blueprint (Markdown)",
                        "href": _prefix(f"{p}/export?format=markdown"),
                        "filename": f"{slug}-blueprint.md",
                        "format": "md",
                    },
                    {
                        "id": "pdf",
                        "label": "Blueprint (PDF)",
                        "href": _prefix(f"{p}/export?format=pdf"),
                        "filename": f"{slug}-blueprint.pdf",
                        "format": "pdf",
                    },
                    {
                        "id": "docx",
                        "label": "Blueprint (Word)",
                        "href": _prefix(f"{p}/export?format=docx"),
                        "filename": f"{slug}-blueprint.docx",
                        "format": "docx",
                    },
                    {
                        "id": "json",
                        "label": "Blueprint (JSON)",
                        "href": _prefix(f"{p}/export?format=json"),
                        "filename": f"{slug}-blueprint.json",
                        "format": "json",
                    },
                ],
            },
            {
                "id": "code",
                "label": "Generated Code",
                "description": "Starter projects generated from the blueprint.",
                "items": [
                    {
                        "id": generator_id,
                        "label": info["label"],
                        "description": info["description"],
                        "href": _prefix(f"{p}/codegen/{generator_id}"),
                        "filename": f"{slug}-{generator_id}.zip",
                        "format": "zip",
                        "section": info["section"],
                    }
                    for generator_id, info in GENERATORS.items()
                ],
            },
            {
                "id": "diagrams",
                "label": "Diagrams",
                "description": "Mermaid diagram sources (view in any Mermaid editor or import into draw.io).",
                "items": [
                    {
                        "id": diagram_id,
                        "label": info["label"],
                        "href": _prefix(f"{p}/diagrams/{diagram_id}/export?format=mmd"),
                        "filename": f"{slug}-{diagram_id}.mmd",
                        "format": "mmd",
                        "category": info["category"],
                    }
                    for diagram_id, info in DIAGRAMS.items()
                ],
            },
            {
                "id": "sprint-board",
                "label": "Sprint Board",
                "description": "Epics, user stories, sprints, milestones and GitHub issues.",
                "items": [
                    {
                        "id": "json",
                        "label": "Board (JSON)",
                        "href": _prefix(f"{p}/pm/export?format=json"),
                        "filename": f"{slug}-project-management.json",
                        "format": "json",
                    },
                    {
                        "id": "markdown",
                        "label": "Board (Markdown)",
                        "href": _prefix(f"{p}/pm/export?format=md"),
                        "filename": f"{slug}-project-management.md",
                        "format": "md",
                    },
                    {
                        "id": "csv",
                        "label": "Board (CSV)",
                        "href": _prefix(f"{p}/pm/export?format=csv"),
                        "filename": f"{slug}-project-management.csv",
                        "format": "csv",
                    },
                ],
            },
            {
                "id": "database",
                "label": "Database Scripts",
                "description": "Schema, seed data and ORM definitions.",
                "items": [
                    {
                        "id": generator_id,
                        "label": info["label"],
                        "description": info["description"],
                        "href": _prefix(f"{p}/codegen/{generator_id}"),
                        "filename": f"{slug}-{generator_id}.zip",
                        "format": "zip",
                        "section": info["section"],
                    }
                    for generator_id, info in GENERATORS.items()
                    if generator_id in ("sql", "prisma", "sqlalchemy")
                ],
            },
            {
                "id": "api-collection",
                "label": "API Collection",
                "description": "Importable OpenAPI / Postman collections of the blueprint's API.",
                "items": [
                    {
                        "id": "openapi",
                        "label": "OpenAPI 3.0 (JSON)",
                        "href": _prefix(f"{p}/api-collection?format=openapi"),
                        "filename": f"{slug}-openapi.json",
                        "format": "json",
                    },
                    {
                        "id": "postman",
                        "label": "Postman Collection",
                        "href": _prefix(f"{p}/api-collection?format=postman"),
                        "filename": f"{slug}-postman.json",
                        "format": "json",
                    },
                ],
            },
            {
                "id": "starter-repo",
                "label": "Starter Repository",
                "description": "Blueprint ZIP with docs, SQL, Docker and deployment files.",
                "items": [
                    {
                        "id": "zip",
                        "label": "Starter repo (ZIP)",
                        "href": _prefix(f"{p}/export?format=zip"),
                        "filename": f"{slug}-blueprint.zip",
                        "format": "zip",
                    },
                ],
            },
        ],
    }


def build_assets_zip(name: str, blueprint: dict[str, Any]) -> bytes:
    """Bundle every generated asset into a single project ZIP."""
    slug = _slug(name)
    root = f"{slug}/"
    doc = blueprint.get("documentation", {})
    db = blueprint.get("database", {})
    buffer = io.BytesIO()

    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(root + "README.md", doc.get("readme", ""))
        zf.writestr(root + "blueprint.md", render_blueprint(blueprint))
        zf.writestr(root + "blueprint.json", to_json(blueprint))

        for filename, key in [
            ("architecture.md", "architecture_documentation"),
            ("api.md", "api_documentation"),
            ("database.md", "database_documentation"),
            ("deployment.md", "deployment_guide"),
            ("installation.md", "installation_guide"),
        ]:
            if doc.get(key):
                zf.writestr(f"{root}docs/{filename}", doc[key])

        for diagram_id in DIAGRAMS:
            try:
                source = generate_diagram(diagram_id, blueprint)
            except Exception:
                source = ""
            zf.writestr(f"{root}diagrams/{diagram_id}.mmd", source)

        try:
            pm = generate_pm(blueprint)
        except Exception:
            pm = {}
        for fmt in ("json", "md", "csv"):
            if pm:
                body = pm_exporters.export(pm, fmt)
                zf.writestr(f"{root}project-management/project-management.{fmt}", body)

        sql = db.get("sql_scripts", {})
        zf.writestr(root + "database/schema.sql", sql.get("create_tables", ""))
        zf.writestr(root + "database/seed.sql", db.get("seed_data", {}).get("sql", ""))
        zf.writestr(
            root + "api/openapi.json",
            json.dumps(build_openapi(blueprint), indent=2, ensure_ascii=False),
        )
        zf.writestr(
            root + "api/postman.json",
            json.dumps(build_postman(blueprint), indent=2, ensure_ascii=False),
        )

        for generator_id in GENERATORS:
            try:
                zip_bytes = build_zip(generator_files(generator_id, blueprint))
            except Exception:
                zip_bytes = b""
            zf.writestr(f"{root}code/{generator_id}.zip", zip_bytes)

    return buffer.getvalue()
