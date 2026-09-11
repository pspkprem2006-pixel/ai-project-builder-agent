"""Request safety: body size cap, field length caps, ZIP path safety.

Concrete issues fixed in Phase 8:
- no default body size limit (memory exhaustion) -> 413 middleware
- unbounded free-text fields (oversized rows) -> schema max_length
- LLM/user-influenced content could reach ZIP entry paths (zip-slip on the
  user's machine when extracting) -> safe_zip_path in build_zip
"""

import io
import zipfile

import pytest

from app.services.codegen.base import build_zip, safe_zip_path
from tests.test_projects import PROJECT_PAYLOAD


@pytest.fixture()
def generated_project(client, auth_headers, drain_jobs):
    project_id = client.post("/api/v1/projects", json=PROJECT_PAYLOAD, headers=auth_headers).json()["id"]
    resp = client.post(f"/api/v1/projects/{project_id}/generate", headers=auth_headers)
    assert resp.status_code == 202
    drain_jobs()
    return project_id, auth_headers


# ---------------------------------------------------------------------------
# Body size cap
# ---------------------------------------------------------------------------


def test_oversized_body_rejected_413(client, auth_headers):
    payload = dict(PROJECT_PAYLOAD)
    payload["description"] = "x" * (2_100_000)
    resp = client.post("/api/v1/projects", json=payload, headers=auth_headers)
    assert resp.status_code == 413
    assert resp.json()["detail"] == "Request body too large"


def test_large_but_acceptable_body_passes(client, auth_headers):
    payload = dict(PROJECT_PAYLOAD)
    payload["description"] = "x" * 4000
    resp = client.post("/api/v1/projects", json=payload, headers=auth_headers)
    assert resp.status_code == 201


# ---------------------------------------------------------------------------
# Schema field caps
# ---------------------------------------------------------------------------


def test_oversized_description_rejected_422(client, auth_headers):
    payload = dict(PROJECT_PAYLOAD)
    payload["description"] = "x" * 5001
    resp = client.post("/api/v1/projects", json=payload, headers=auth_headers)
    assert resp.status_code == 422


def test_oversized_target_users_rejected_422(client, auth_headers):
    payload = dict(PROJECT_PAYLOAD)
    payload["target_users"] = "x" * 2001
    resp = client.post("/api/v1/projects", json=payload, headers=auth_headers)
    assert resp.status_code == 422


def test_too_many_features_rejected_422(client, auth_headers):
    payload = dict(PROJECT_PAYLOAD)
    payload["features"] = ["f"] * 101
    resp = client.post("/api/v1/projects", json=payload, headers=auth_headers)
    assert resp.status_code == 422


def test_login_password_length_capped(client):
    resp = client.post(
        "/api/v1/auth/login", json={"email": "a@example.com", "password": "x" * 129}
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# ZIP entry path safety
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "path",
    [
        "../evil.py",
        "a/../../evil.py",
        "/absolute/evil.py",
        "C:/windows/evil.py",
        "c:\\windows\\evil.py",
        "",
    ],
)
def test_safe_zip_path_rejects_unsafe_entries(path):
    with pytest.raises(ValueError):
        safe_zip_path(path)


def test_safe_zip_path_accepts_normal_entries():
    assert safe_zip_path("app/main.py") == "app/main.py"
    assert safe_zip_path("src/app/(app)/patients/page.js") == "src/app/(app)/patients/page.js"


def test_build_zip_rejects_traversal_entries():
    with pytest.raises(ValueError):
        build_zip({"src/app.py": "ok", "../escape.py": "evil"})


def test_build_zip_entries_are_relative_and_contained():
    data = build_zip({"src/app.py": "print(1)", "docs/readme.md": "hi"})
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        for name in zf.namelist():
            assert not name.startswith("/")
            assert ".." not in name.split("/")
            assert not (len(name) >= 2 and name[1] == ":")


def _seed_blueprint(client, auth_headers, blueprint):
    project_id = client.post("/api/v1/projects", json=PROJECT_PAYLOAD, headers=auth_headers).json()["id"]
    from app.database import SessionLocal
    from app.models.project import Project

    with SessionLocal() as db:
        project = db.get(Project, project_id)
        project.blueprint = blueprint
        db.commit()
    return project_id


def _hostile_blueprint(table_name: str) -> dict:
    return {
        "project": {"id": 1, "name": "Hostile", "description": "x", "category": "x", "features": [], "stack": {}},
        "metadata": {"version": "3.0", "provider": "template", "generated_at": "2026-01-01T00:00:00"},
        "analysis": {"requirements": [], "features": []},
        "domain_understanding": {},
        "business_processes": {},
        "technology_selection": {},
        "technology_evaluation": {},
        "design_decisions": {},
        "tradeoffs": {},
        "architecture": {},
        "database": {
            "tables": [
                {
                    "name": table_name,
                    "description": "x",
                    "columns": [{"name": "id", "type": "SERIAL PRIMARY KEY", "constraints": ["PK"], "description": ""}],
                    "indexes": [],
                    "relationships": [],
                }
            ]
        },
        "api": {
            "endpoints": [
                {
                    "method": "GET",
                    "path": "/api/v1/x",
                    "description": "x",
                    "authentication": True,
                    "status_codes": [200],
                    "validation_rules": [],
                }
            ]
        },
        "ui_ux": {},
        "security": {},
        "performance": {},
        "scalability": {},
        "cost_estimation": {},
        "business_risks": {},
        "roadmap": {},
        "product_evolution": {},
        "adr": {},
        "testing": {},
        "documentation": {},
        "validation": {},
        "deployment": {},
    }


def test_hostile_blueprint_cannot_produce_traversal_zip(client, auth_headers):
    """A crafted table name must never yield ../ entries in a generated ZIP."""
    project_id = _seed_blueprint(client, auth_headers, _hostile_blueprint("../evil"))
    resp = client.get(f"/api/v1/projects/{project_id}/codegen/nextjs", headers=auth_headers)
    assert resp.status_code == 500
    body = resp.json()
    assert "evil" not in body["detail"]
    assert body["detail"] == "Code generation failed unexpectedly. Please try again later."


def test_normal_blueprint_zip_entries_are_safe(client, generated_project):
    """Regression guard across every generator with a real (template) blueprint."""
    project_id, headers = generated_project
    for generator_id in ("sql", "prisma", "sqlalchemy", "fastapi", "express", "spring", "react", "nextjs"):
        resp = client.get(f"/api/v1/projects/{project_id}/codegen/{generator_id}", headers=headers)
        assert resp.status_code == 200, generator_id
        with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
            for name in zf.namelist():
                assert not name.startswith("/"), (generator_id, name)
                assert ".." not in name.split("/"), (generator_id, name)
                assert not (len(name) >= 2 and name[1] == ":"), (generator_id, name)
