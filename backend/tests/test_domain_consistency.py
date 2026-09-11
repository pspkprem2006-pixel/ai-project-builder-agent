"""V4 Bug Fix Sprint #1 — Domain Consistency & Context Isolation.

Every blueprint generation builds a fresh Domain Context from the user input,
agents are constrained to that domain, and a semantic consistency checker
rejects/regenerates sections that reference vocabulary from another domain.
"""

import json

import pytest

from app.services.ai.domain_context import build_domain_context, find_forbidden_terms
from app.services.ai.reasoning import generate_blueprint
from app.services.ai.semantic_consistency import (
    failing_sections,
    scan_section,
    semantic_consistency_review,
)
from app.services.ai.v3_architect import quality_review
from tests.test_projects import PROJECT_PAYLOAD

CITY_PAYLOAD = {
    "name": "CityOS AI",
    "description": (
        "City operations platform: traffic signals, public buses, waste collection "
        "and municipal services for the metropolitan region."
    ),
    "category": "Smart City",
    "target_users": "City administrators, operations staff",
    "features": [
        "Traffic light control",
        "Bus route management",
        "Waste collection",
        "Citizen services",
    ],
    "preferred_frontend": "React",
    "preferred_backend": "FastAPI",
    "database": "PostgreSQL",
    "auth_method": "JWT",
    "deployment_platform": "Docker",
    "language": "Python",
}


def test_detect_domain_custom_fallback_not_saas():
    ctx = build_domain_context(
        {
            "name": "Legal Archive Manager",
            "description": "Organize legal contracts, clauses and compliance notes with full-text search.",
            "category": "Legal",
            "features": ["Contract search", "Clause review"],
        }
    )
    assert ctx["primary_domain"] == "custom"
    assert ctx["is_custom_domain"] is True


def _section_blob_without_audit(blueprint: dict) -> str:
    """All generated content, excluding the audit payloads (metadata and
    validation legitimately list the forbidden vocabulary of other domains)."""
    sections = {k: v for k, v in blueprint.items() if k not in ("metadata", "validation")}
    return json.dumps(sections, ensure_ascii=False, default=str).lower()


def test_smart_city_domain_detected():
    ctx = build_domain_context(CITY_PAYLOAD)
    assert ctx["primary_domain"] == "smart_city"
    assert ctx["domain_label"] == "Smart City Management"
    assert "traffic_signals" in [t["name"] for t in ctx["tables"]]


def test_hospital_forbids_smart_city_vocabulary():
    ctx = build_domain_context(PROJECT_PAYLOAD)
    assert ctx["primary_domain"] == "hospital"
    assert "traffic signal" in ctx["forbidden_vocabulary"]
    assert "waste collection" in ctx["forbidden_vocabulary"]


def test_find_forbidden_terms_word_boundary():
    hits = find_forbidden_terms("Run the traffic signal controller", ["traffic signal", "patient"])
    assert hits == ["traffic signal"]
    assert find_forbidden_terms("citizens dashboard", ["traffic signal"]) == []


def test_city_blueprint_has_no_hospital_content():
    blueprint = generate_blueprint(CITY_PAYLOAD)
    blob = _section_blob_without_audit(blueprint)
    for term in ("hospital", "patient", "doctor", "prescription", "pharmacy"):
        assert term not in blob, f"cross-domain leak in CityOS blueprint: {term}"
    review = semantic_consistency_review(blueprint)
    assert review["skipped"] is False
    assert review["semantic_score"] == 100
    assert failing_sections(blueprint) == []


def test_hospital_blueprint_has_no_smart_city_content():
    blueprint = generate_blueprint(PROJECT_PAYLOAD)
    blob = _section_blob_without_audit(blueprint)
    for term in ("traffic signal", "traffic light", "waste collection", "bus route", "municipal"):
        assert term not in blob, f"cross-domain leak in hospital blueprint: {term}"
    review = semantic_consistency_review(blueprint)
    assert review["semantic_score"] == 100


def test_cross_domain_contamination_is_flagged():
    blueprint = generate_blueprint(PROJECT_PAYLOAD)
    blueprint["documentation"]["readme"] = (
        "# Hospital\n\nTraffic signals and waste collection trucks are managed by city staff.\n"
    )
    entry = scan_section("documentation", blueprint, blueprint["metadata"]["domain_context"])
    assert entry["status"] == "FAIL"
    assert "traffic signal" in entry["forbidden_terms"]
    review = semantic_consistency_review(blueprint)
    assert review["semantic_score"] < 100
    assert "documentation" in failing_sections(blueprint)


def test_quality_review_reports_semantic_consistency():
    blueprint = generate_blueprint(PROJECT_PAYLOAD)
    review = quality_review(blueprint)
    checks = {check["area"]: check for check in review["checks"]}
    assert "Semantic consistency" in checks
    assert checks["Semantic consistency"]["status"] == "pass"
    assert review["quality_report"]["semantic_consistency_score"] == 100
    assert review["semantic_consistency"]["semantic_score"] == 100


def test_quality_review_fails_on_cross_domain_content():
    blueprint = generate_blueprint(PROJECT_PAYLOAD)
    blueprint["database"]["tables"].append(
        {
            "name": "traffic_signals",
            "purpose": "Traffic signal controller and junction monitoring",
            "columns": [{"name": "id", "type": "SERIAL PRIMARY KEY", "constraints": ["PK"], "description": "Id"}],
            "indexes": [],
            "relationships": [],
        }
    )
    review = quality_review(blueprint)
    semantic = next(check for check in review["checks"] if check["area"] == "Semantic consistency")
    assert semantic["status"] == "fail"
    assert review["passed"] is False


def test_readme_is_dynamic_from_domain_context():
    blueprint = generate_blueprint(CITY_PAYLOAD)
    readme = blueprint["documentation"]["readme"]
    assert "# CityOS AI" in readme
    assert "## Business Overview" in readme
    assert "## Key Modules" in readme
    assert "Smart City" in readme


@pytest.fixture()
def generated_project(client, auth_headers, drain_jobs):
    project_id = client.post("/api/v1/projects", json=PROJECT_PAYLOAD, headers=auth_headers).json()["id"]
    resp = client.post(f"/api/v1/projects/{project_id}/generate", headers=auth_headers)
    assert resp.status_code == 202
    drain_jobs()
    return project_id, auth_headers


def test_generated_project_preserves_domain_context(client, generated_project):
    project_id, headers = generated_project
    project = client.get(f"/api/v1/projects/{project_id}", headers=headers).json()
    metadata = project["blueprint"]["metadata"]
    ctx = metadata["domain_context"]
    assert ctx["primary_domain"] == "hospital"
    assert ctx["forbidden_vocabulary"]
    assert metadata["version"] == "3.0"


def test_generated_project_attaches_debug_report(client, generated_project):
    project_id, headers = generated_project
    project = client.get(f"/api/v1/projects/{project_id}", headers=headers).json()
    debug = project["blueprint"]["metadata"]["debug_report"]
    assert debug["context"]["primary_domain"] == "hospital"
    assert debug["semantic_consistency"]["score"] == 100
    assert debug["semantic_consistency"]["skipped"] is False


def test_validation_gate_rejects_wrong_domain_output():
    """An agent that emits another domain is rejected by the semantic gate
    — mirroring the CityOS -> Healthcare regression scenario."""
    ctx = build_domain_context(CITY_PAYLOAD)
    wrong_output = {
        "identified_domain": "healthcare",
        "domain_label": "Healthcare",
        "summary": "A Hospital management system that books patient appointments with doctors.",
    }
    entry = scan_section("domain_understanding", {"domain_understanding": wrong_output}, ctx)
    assert entry["status"] == "FAIL"
    assert any(term in entry["forbidden_terms"] for term in ("hospital", "patient", "doctor", "healthcare"))


def test_regenerate_section_keeps_domain_context(client, generated_project):
    project_id, headers = generated_project
    resp = client.post(
        f"/api/v1/projects/{project_id}/regenerate-section",
        json={"section": "api"},
        headers=headers,
    )
    assert resp.status_code == 200
    ctx = resp.json()["blueprint"]["metadata"]["domain_context"]
    assert ctx["primary_domain"] == "hospital"
    assert "traffic signal" in ctx["forbidden_vocabulary"]


def test_codegen_artifacts_are_domain_isolated():
    from app.services.codegen.backend import generate_fastapi
    from app.services.codegen.database import generate_sql, generate_sqlalchemy
    from app.services.codegen.frontend import generate_nextjs

    blueprint = generate_blueprint(CITY_PAYLOAD)
    blueprint["project"] = {
        "name": CITY_PAYLOAD["name"],
        "stack": {
            "frontend": CITY_PAYLOAD["preferred_frontend"],
            "backend": CITY_PAYLOAD["preferred_backend"],
            "database": CITY_PAYLOAD["database"],
            "auth": CITY_PAYLOAD["auth_method"],
            "deployment": CITY_PAYLOAD["deployment_platform"],
        },
    }
    tables = {t["name"] for t in blueprint["database"]["tables"]}
    assert {"citizens", "traffic_signals", "waste_collections"}.issubset(tables)
    assert "hospitals" not in tables

    blob = json.dumps(
        {
            **generate_sql(blueprint),
            **generate_sqlalchemy(blueprint),
            **generate_fastapi(blueprint),
            **generate_nextjs(blueprint),
            "readme": blueprint["documentation"]["readme"],
        },
        default=str,
    ).lower()
    for term in ("hospital", "patient", "doctor", "prescription", "pharmacy"):
        assert term not in blob, f"cross-domain leak in generated code: {term}"
