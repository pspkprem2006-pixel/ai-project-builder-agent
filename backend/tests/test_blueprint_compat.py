"""Phase 6: legacy blueprint (V1/V2) compatibility and codegen error handling.

Covers the canonical normalization layer (``app/services/blueprint_compat.py``)
and the API contract: legacy projects must load, export, generate code, render
diagrams, and produce PM/workspace artifacts; expected incompatibilities map to
HTTP 400; unexpected generator failures map to a safe HTTP 500.
"""

from __future__ import annotations

import copy
import io
import zipfile

import pytest
from fastapi.testclient import TestClient

from app.database import SessionLocal
from app.main import app
from app.models.project import Project
from app.services.blueprint_compat import (
    CANONICAL_SECTIONS,
    BlueprintIncompatibleError,
    detect_blueprint_version,
    is_canonical_v3,
    normalize_blueprint,
)
from tests.test_projects import PROJECT_PAYLOAD

LEGACY_EXTRAS = ("folder_structure", "git_commits", "recommendations")


def legacy_blueprint(version: str = "1.0") -> dict:
    blueprint = {
        "project": {
            "name": "Legacy App",
            "category": "Healthcare",
            "stack": {
                "frontend": "React",
                "backend": "FastAPI",
                "database": "PostgreSQL",
                "auth": "JWT",
                "deployment": "Docker",
            },
        },
        "metadata": {"version": version, "generated_at": "2025-01-01T00:00:00Z", "provider": "template"},
        "analysis": {
            "problem_statement": "Digitize clinic operations.",
            "objectives": ["Objective"],
            "target_audience": "Staff",
            "functional_requirements": [{"id": "F1", "requirement": "Register patients"}],
            "non_functional_requirements": [{"id": "N1", "requirement": "Fast responses"}],
            "technology_recommendations": [{"name": "FastAPI", "why": "Type-safe"}],
            "complexity_analysis": {
                "overall": "Low",
                "factors": ["Small scope", "One team"],
                "recommendation": "Proceed",
            },
            "estimated_development_time": "4-6 weeks",
            "estimated_team_size": 2,
            "suggested_improvements": ["Improvement"],
            "risks": [{"risk": "Scope creep", "severity": "Low", "mitigation": "Freeze scope"}],
        },
        "architecture": {"patterns": [], "components": [], "design_decisions": []},
        "folder_structure": {"tree": "legacy-app/\n  src/"},
        "database": {
            "tables": [
                {
                    "name": "users",
                    "purpose": "Registered users.",
                    "columns": [
                        {"name": "id", "type": "INTEGER", "constraints": ["PK"], "description": "Primary key"}
                    ],
                }
            ]
        },
        "api": {
            "endpoints": [
                {
                    "path": "/users",
                    "method": "GET",
                    "description": "List users.",
                    "authentication": "None",
                }
            ]
        },
        "ui_ux": {"screens": [], "forms": [], "user_journeys": []},
        "roadmap": {
            "summary": "Ship soon.",
            "total_estimated_hours": 100,
            "weekly_milestones": [],
            "critical_path": [],
            "team_plan": [],
        },
        "git_commits": {"history": [{"hash": "a1b2c3", "message": "chore: init"}]},
        "testing": {"strategy": "Unit first.", "types": {"unit": [], "integration": [], "e2e": []}},
        "deployment": {"platform": "Docker", "environment_variables": [], "ci_cd_pipeline": []},
        "documentation": {"api_docs": "OpenAPI"},
        "recommendations": {"libraries": [{"name": "pytest", "why": "Speed"}]},
    }
    if version == "2.0":
        for key in LEGACY_EXTRAS:
            blueprint.pop(key, None)
        blueprint.update(
            {
                "domain_understanding": {"primary_users": [], "domain_glossary": [], "nouns": []},
                "business_processes": {"workflows": [], "business_rules": [], "role_permissions": []},
                "technology_selection": {"selected_stack": [], "decision_matrix": []},
            }
        )
    return blueprint


def v3_blueprint(version: str = "3.0") -> dict:
    blueprint = legacy_blueprint(version)
    for key in LEGACY_EXTRAS:
        blueprint.pop(key, None)
    blueprint.update(
        {
            "domain_understanding": {"primary_users": [], "domain_glossary": [], "nouns": []},
            "business_processes": {"workflows": [], "business_rules": [], "role_permissions": []},
            "technology_selection": {"selected_stack": [], "decision_matrix": []},
            "technology_evaluation": {"summary": "OK", "categories": []},
            "design_decisions": {"summary": "OK", "decisions": []},
            "tradeoffs": {"summary": "OK", "tradeoffs": []},
            "security": {"summary": "OK", "security_score": 80, "assessment": [], "owasp": [], "privacy": {}},
            "performance": {"summary": "OK", "checklist": [], "bottlenecks": [], "database_tuning": {}},
            "scalability": {"summary": "OK", "scenarios": []},
            "cost_estimation": {"summary": "OK", "currency": "USD", "breakdown": []},
            "business_risks": {"summary": "OK", "risks": []},
            "product_evolution": {"summary": "OK", "versions": []},
            "adr": {"summary": "OK", "records": []},
            "validation": {"summary": "OK", "checks": [], "gaps": [], "consistency_fixes": []},
        }
    )
    return blueprint


# ---------------------------------------------------------------------------
# Unit: version detection
# ---------------------------------------------------------------------------


def test_detect_version_from_metadata():
    assert detect_blueprint_version(legacy_blueprint("1.0")) == "1.0"
    assert detect_blueprint_version(legacy_blueprint("2.0")) == "2.0"
    assert detect_blueprint_version(v3_blueprint("3.0")) == "3.0"


def test_detect_version_heuristic_without_metadata():
    v1 = legacy_blueprint("1.0")
    v1.pop("metadata")
    assert detect_blueprint_version(v1) == "1.0"

    v2 = legacy_blueprint("2.0")
    v2.pop("metadata")
    assert detect_blueprint_version(v2) == "2.0"

    v3 = v3_blueprint()
    v3.pop("metadata")
    assert detect_blueprint_version(v3) == "3.0"


def test_is_canonical_v3():
    assert is_canonical_v3(v3_blueprint())
    assert not is_canonical_v3(legacy_blueprint("1.0"))
    assert not is_canonical_v3(legacy_blueprint("2.0"))
    assert not is_canonical_v3([])


# ---------------------------------------------------------------------------
# Unit: normalization
# ---------------------------------------------------------------------------


def test_v3_passthrough_is_identical():
    v3 = v3_blueprint()
    normalized = normalize_blueprint(v3)
    assert normalized == v3
    assert normalized is not v3  # deep copy


def test_normalize_v1_fills_all_canonical_sections():
    normalized = normalize_blueprint(legacy_blueprint("1.0"))
    assert all(section in normalized for section in CANONICAL_SECTIONS)


def test_normalize_v1_preserves_legacy_extras_and_common_keys():
    v1 = legacy_blueprint("1.0")
    normalized = normalize_blueprint(v1)
    for key in LEGACY_EXTRAS:
        assert normalized[key] == v1[key]
    assert normalized["project"] == v1["project"]
    assert normalized["metadata"]["version"] == "1.0"
    assert normalized["metadata"]["legacy_version"] == "1.0"
    assert normalized["metadata"]["generated_at"] == v1["metadata"]["generated_at"]


def test_normalize_v1_stubs_are_honest():
    normalized = normalize_blueprint(legacy_blueprint("1.0"))
    for section in (
        "domain_understanding",
        "business_processes",
        "technology_selection",
        "security",
        "performance",
        "scalability",
        "cost_estimation",
        "business_risks",
        "product_evolution",
        "adr",
        "validation",
    ):
        stub = normalized[section]
        assert stub["available"] is False
        assert stub["legacy_notice"] is True
        assert "legacy blueprint (version 1.0)" in stub["summary"]
        assert "Regenerate" in stub["summary"]


def test_normalize_v1_derives_complexity_score_from_legacy_data():
    normalized = normalize_blueprint(legacy_blueprint("1.0"))
    score = normalized["analysis"]["complexity_score"]
    assert score["level"] == "Low"
    assert score["score"] is None
    assert "Small scope" in score["reasoning"]
    assert score["estimated_time"] == "4-6 weeks"
    assert score["estimated_team"]["total"] == 2
    # Original V1 keys remain untouched.
    assert normalized["analysis"]["complexity_analysis"]["overall"] == "Low"


def test_normalize_v2_preserves_present_sections():
    v2 = legacy_blueprint("2.0")
    normalized = normalize_blueprint(v2)
    assert normalized["domain_understanding"] == v2["domain_understanding"]
    assert normalized["technology_selection"] == v2["technology_selection"]
    assert normalized["metadata"]["legacy_version"] == "2.0"


def test_normalize_is_idempotent():
    v1 = normalize_blueprint(legacy_blueprint("1.0"))
    assert normalize_blueprint(v1) == v1
    v3 = v3_blueprint()
    assert normalize_blueprint(v3) == v3


def test_normalize_does_not_mutate_input():
    v1 = legacy_blueprint("1.0")
    original = copy.deepcopy(v1)
    normalize_blueprint(v1)
    assert v1 == original


def test_normalize_v3_with_missing_section_is_repaired_without_legacy_marker():
    v3 = v3_blueprint()
    del v3["validation"]
    normalized = normalize_blueprint(v3)
    assert normalized["validation"]["available"] is False
    assert "legacy_version" not in normalized["metadata"]


def test_normalize_preserves_unknown_extra_keys():
    v1 = legacy_blueprint("1.0")
    v1["custom_field"] = {"anything": True}
    normalized = normalize_blueprint(v1)
    assert normalized["custom_field"] == {"anything": True}


def test_normalize_rejects_non_object_blueprints():
    for bad in (None, [], "nope", 42):
        with pytest.raises(BlueprintIncompatibleError):
            normalize_blueprint(bad)


# ---------------------------------------------------------------------------
# API: helper to seed a legacy blueprint directly into the DB
# ---------------------------------------------------------------------------


def _seed_blueprint(client, auth_headers, blueprint: dict) -> int:
    project_id = client.post("/api/v1/projects", json=PROJECT_PAYLOAD, headers=auth_headers).json()["id"]
    with SessionLocal() as db:
        project = db.get(Project, project_id)
        project.blueprint = blueprint
        db.commit()
    return project_id


def _stored_blueprint(project_id: int) -> dict:
    with SessionLocal() as db:
        return db.get(Project, project_id).blueprint


# ---------------------------------------------------------------------------
# API: legacy project loads and exports
# ---------------------------------------------------------------------------


def test_get_legacy_project_returns_v3_contract(client, auth_headers):
    project_id = _seed_blueprint(client, auth_headers, legacy_blueprint("1.0"))
    resp = client.get(f"/api/v1/projects/{project_id}", headers=auth_headers)
    assert resp.status_code == 200
    blueprint = resp.json()["blueprint"]
    assert all(section in blueprint for section in CANONICAL_SECTIONS)
    assert "folder_structure" in blueprint
    assert blueprint["metadata"]["legacy_version"] == "1.0"
    # Stored blueprint is untouched by normalization.
    assert "security" not in _stored_blueprint(project_id)


@pytest.mark.parametrize("export_format", ["markdown", "json", "zip"])
def test_export_legacy_project_all_formats(client, auth_headers, export_format):
    project_id = _seed_blueprint(client, auth_headers, legacy_blueprint("1.0"))
    resp = client.get(f"/api/v1/projects/{project_id}/export?format={export_format}", headers=auth_headers)
    assert resp.status_code == 200
    if export_format == "markdown":
        assert b"not present in the legacy blueprint" in resp.content
    elif export_format == "json":
        body = resp.json()
        assert all(section in body for section in CANONICAL_SECTIONS)
        assert "folder_structure" in body  # legacy info preserved, not dropped
    else:
        assert resp.content[:2] == b"PK"


# ---------------------------------------------------------------------------
# API: codegen on legacy projects (H-1) and error handling (H-2)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "generator_id,expected_file",
    [
        ("sql", "schema.sql"),
        ("prisma", "prisma/schema.prisma"),
        ("sqlalchemy", "app/models.py"),
        ("fastapi", "app/main.py"),
        ("express", "src/app.js"),
        ("spring", "pom.xml"),
        ("react", "src/App.jsx"),
        ("nextjs", "src/lib/api.js"),
    ],
)
def test_codegen_on_legacy_blueprint(client, auth_headers, generator_id, expected_file):
    project_id = _seed_blueprint(client, auth_headers, legacy_blueprint("1.0"))
    resp = client.get(f"/api/v1/projects/{project_id}/codegen/{generator_id}", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/zip"
    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        assert expected_file in set(zf.namelist())


def test_manifest_on_legacy_blueprint(client, auth_headers):
    project_id = _seed_blueprint(client, auth_headers, legacy_blueprint("1.0"))
    resp = client.get(f"/api/v1/projects/{project_id}/codegen/fastapi/manifest", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["total_bytes"] > 0


def test_codegen_still_works_for_v3_blueprint(client, auth_headers):
    project_id = _seed_blueprint(client, auth_headers, v3_blueprint())
    resp = client.get(f"/api/v1/projects/{project_id}/codegen/fastapi", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.content[:2] == b"PK"


def test_incompatible_blueprint_maps_to_400(client, auth_headers):
    project_id = _seed_blueprint(client, auth_headers, ["not", "a", "blueprint"])
    for url in (
        f"/api/v1/projects/{project_id}",
        f"/api/v1/projects/{project_id}/codegen/fastapi",
        f"/api/v1/projects/{project_id}/export?format=json",
    ):
        resp = client.get(url, headers=auth_headers)
        assert resp.status_code == 400, url
        assert "not a structured object" in resp.json()["detail"]


def test_unexpected_generator_error_maps_to_safe_500(client, auth_headers, monkeypatch):
    project_id = _seed_blueprint(client, auth_headers, v3_blueprint())
    from app.api import codegen as codegen_api

    def boom(*_args, **_kwargs):
        raise RuntimeError("secret-internal-detail")

    monkeypatch.setattr(codegen_api, "generator_files", boom)
    raw_client = TestClient(app, raise_server_exceptions=False)
    with raw_client:
        resp = raw_client.get(
            f"/api/v1/projects/{project_id}/codegen/fastapi",
            headers=auth_headers,
        )
    assert resp.status_code == 500
    body = resp.text
    assert "secret-internal-detail" not in body
    assert "Code generation failed unexpectedly" in body


def test_invalid_generator_on_legacy_is_404(client, auth_headers):
    project_id = _seed_blueprint(client, auth_headers, legacy_blueprint("1.0"))
    resp = client.get(f"/api/v1/projects/{project_id}/codegen/nope", headers=auth_headers)
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# API: diagrams, PM and workspace on legacy projects
# ---------------------------------------------------------------------------


def test_diagrams_on_legacy_blueprint(client, auth_headers):
    project_id = _seed_blueprint(client, auth_headers, legacy_blueprint("1.0"))
    for diagram_id in ("overview", "erd"):
        resp = client.get(f"/api/v1/projects/{project_id}/diagrams/{diagram_id}", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["source"]  # mermaid source rendered from the normalized blueprint


def test_pm_on_legacy_blueprint(client, auth_headers):
    project_id = _seed_blueprint(client, auth_headers, legacy_blueprint("1.0"))
    resp = client.get(f"/api/v1/projects/{project_id}/pm", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["generated_at"]
    resp = client.get(f"/api/v1/projects/{project_id}/pm/export?format=md", headers=auth_headers)
    assert resp.status_code == 200


def test_workspace_on_legacy_blueprint(client, auth_headers):
    project_id = _seed_blueprint(client, auth_headers, legacy_blueprint("1.0"))
    resp = client.get(f"/api/v1/projects/{project_id}/workspace/export", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.content[:2] == b"PK"
    for collection_format in ("openapi", "postman"):
        resp = client.get(
            f"/api/v1/projects/{project_id}/api-collection?format={collection_format}",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()


# ---------------------------------------------------------------------------
# API: diagrams, PM and workspace on legacy projects
# ---------------------------------------------------------------------------
