"""Phase 5 — AI Review and Validation: quality report + section regeneration."""

import pytest

from app.services.ai.v3_architect import quality_review
from tests.test_projects import PROJECT_PAYLOAD


@pytest.fixture()
def generated_project(client, auth_headers, drain_jobs):
    project_id = client.post("/api/v1/projects", json=PROJECT_PAYLOAD, headers=auth_headers).json()["id"]
    resp = client.post(f"/api/v1/projects/{project_id}/generate", headers=auth_headers)
    assert resp.status_code == 202
    drain_jobs()
    return project_id, auth_headers


def test_quality_report_scores(client, generated_project):
    project_id, headers = generated_project
    project = client.get(f"/api/v1/projects/{project_id}", headers=headers).json()
    report = project["blueprint"]["validation"]["quality_report"]

    assert 0 <= report["overall_quality"] <= 100
    assert 0 <= report["production_readiness_score"] <= 100
    assert report["readiness"] in ("Production Ready", "Ready with Minor Gaps", "Needs Attention")
    assert report["summary"].endswith("fail, 0 warn.")


def test_quality_review_checks_include_new_areas(client, generated_project):
    project_id, headers = generated_project
    project = client.get(f"/api/v1/projects/{project_id}", headers=headers).json()
    checks = project["blueprint"]["validation"]["checks"]
    areas = {check["area"] for check in checks}
    assert "Unused tables" in areas
    assert "Missing entities" in areas
    assert project["blueprint"]["validation"]["passed"] is True


def test_unused_table_detected():
    blueprint = {
        "analysis": {"functional_requirements": [{"title": "Book appointments"}]},
        "business_processes": {"workflows": [{"name": "Booking"}]},
        "api": {"endpoints": [{"path": "/appointments", "method": "GET", "description": "List appointments"}],
                "business_workflow_mapping": [{"workflow": "Booking", "endpoints": ["/appointments"]}]},
        "database": {
            "tables": [
                {"name": "appointments", "columns": [{"name": "id", "type": "SERIAL PRIMARY KEY"}], "relationships": [], "indexes": []},
                {"name": "widgets", "columns": [{"name": "id", "type": "SERIAL PRIMARY KEY"}], "relationships": [], "indexes": []},
            ],
            "seed_data": None,
        },
        "ui_ux": {"screens": [{"name": "Booking screen"}]},
        "testing": {"api_tests": [{"endpoint": "/appointments"}]},
        "security": {"security_score": 85},
        "performance": {"performance_score": 85},
        "documentation": {"readme": "# x"},
        "deployment": {"dockerfile": "FROM python"},
        "scalability": {"scenarios": [{"users": 100}]},
        "architecture": {"high_level_architecture": "graph TD"},
    }
    review = quality_review(blueprint)
    unused = next(c for c in review["checks"] if c["area"] == "Unused tables")
    assert unused["status"] == "warn"
    assert "widgets" in unused["message"]
    assert "appointments" not in unused["message"]
    assert review["passed"] is True


def test_missing_entity_detected():
    blueprint = {
        "analysis": {"functional_requirements": [{"title": "Manage patients"}]},
        "business_processes": {"workflows": [{"name": "Admission"}]},
        "api": {
            "endpoints": [
                {"path": "/appointments", "method": "GET", "description": "List appointments"},
                {"path": "/patients", "method": "POST", "description": "Register a patient"},
                {"path": "/auth/login", "method": "POST", "description": "Login"},
                {"path": "/workflows/admission/execute", "method": "POST", "description": "Run admission"},
            ]
        },
        "database": {
            "tables": [{"name": "appointments", "columns": [], "relationships": [], "indexes": []}],
            "seed_data": None,
        },
        "ui_ux": {"screens": []},
        "testing": {"api_tests": []},
        "security": {"security_score": 85},
        "performance": {"performance_score": 85},
        "documentation": {"readme": "# x"},
        "deployment": {"dockerfile": "FROM python"},
        "scalability": {"scenarios": [{"users": 100}]},
        "architecture": {"high_level_architecture": "graph TD"},
    }
    review = quality_review(blueprint)
    missing = next(c for c in review["checks"] if c["area"] == "Missing entities")
    assert missing["status"] == "fail"
    assert "patients" in missing["message"]
    assert review["passed"] is False


def test_regenerate_section_endpoint(client, generated_project):
    project_id, headers = generated_project
    before = client.get(f"/api/v1/projects/{project_id}", headers=headers).json()

    resp = client.post(
        f"/api/v1/projects/{project_id}/regenerate-section",
        json={"section": "api"},
        headers=headers,
    )
    assert resp.status_code == 200
    after = resp.json()

    assert after["status"] == "complete"
    assert after["blueprint"]["api"]["endpoints"]
    assert after["blueprint"]["api"]["base_url"] == "/api/v1"
    # Only the api section was touched — other sections are preserved.
    assert after["blueprint"]["database"] == before["blueprint"]["database"]
    assert after["blueprint"]["architecture"] == before["blueprint"]["architecture"]
    # Validation was re-run on the regenerated blueprint.
    assert "validation" in after["blueprint"]
    assert "quality_report" in after["blueprint"]["validation"]


def test_regenerate_section_requires_blueprint(client, auth_headers):
    project_id = client.post("/api/v1/projects", json=PROJECT_PAYLOAD, headers=auth_headers).json()["id"]
    resp = client.post(
        f"/api/v1/projects/{project_id}/regenerate-section",
        json={"section": "api"},
        headers=auth_headers,
    )
    assert resp.status_code == 400


def test_regenerate_section_unknown_section(client, generated_project):
    project_id, headers = generated_project
    resp = client.post(
        f"/api/v1/projects/{project_id}/regenerate-section",
        json={"section": "nope"},
        headers=headers,
    )
    assert resp.status_code == 422
