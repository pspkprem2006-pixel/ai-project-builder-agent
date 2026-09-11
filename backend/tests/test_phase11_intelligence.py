"""Phase 11 — action results become project intelligence.

Covers action history (create / list / retrieve / ownership / pagination),
apply semantics (valid, invalid data, wrong section, stale revision,
unauthorized, transactional rollback, unrelated sections preserved),
blueprint revisions (increment, source action, previous state, concurrent
uniqueness), deterministic fallbacks for all six Phase 10 actions, artifact
generation (CI/CD + test scaffolding, ZIP traversal protection, secret
exclusion), and the real Hospital Management System + Food Delivery Platform
E2E workflows.
"""

from __future__ import annotations

import copy
import io
import zipfile

import pytest
from sqlalchemy.exc import IntegrityError

from app.database import SessionLocal
from tests.test_phase10_e2e import FOOD_DELIVERY_PAYLOAD
from tests.test_projects import PROJECT_PAYLOAD


def _create_generated_project(client, headers, payload=PROJECT_PAYLOAD):
    project_id = client.post("/api/v1/projects", json=payload, headers=headers).json()["id"]
    resp = client.post(f"/api/v1/projects/{project_id}/generate", headers=headers)
    assert resp.status_code == 202
    return project_id


def _run_action(client, headers, project_id, action_id, inputs=None):
    resp = client.post(
        f"/api/v1/projects/{project_id}/actions/{action_id}",
        json={"inputs": inputs or {}},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _second_user_headers(client):
    import uuid

    email = f"other-{uuid.uuid4().hex[:8]}@example.com"
    resp = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "password123", "full_name": "Other User"},
    )
    assert resp.status_code == 201, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


def _history(client, headers, project_id, limit=50, offset=0):
    resp = client.get(
        f"/api/v1/projects/{project_id}/actions/history?limit={limit}&offset={offset}",
        headers=headers,
    )
    assert resp.status_code == 200
    return resp.json()


# ---------------------------------------------------------------------------
# Action history: create, list, retrieve, ownership, pagination
# ---------------------------------------------------------------------------


def test_history_created_on_execution(client, auth_headers, drain_jobs):
    project_id = _create_generated_project(client, auth_headers)
    drain_jobs()
    body = _run_action(client, auth_headers, project_id, "security-audit")
    history = _history(client, auth_headers, project_id)
    assert history["total"] == 1
    item = history["items"][0]
    assert item["action_id"] == "security-audit"
    assert item["status"] == body["status"]
    assert item["provider"] == body["provider"]
    assert item["applied"] is False
    assert item["warning_count"] >= 0
    assert item["created_at"]


def test_history_requires_auth(client, auth_headers, drain_jobs):
    project_id = _create_generated_project(client, auth_headers)
    drain_jobs()
    assert client.get(f"/api/v1/projects/{project_id}/actions/history").status_code == 401


def test_history_foreign_project_404(client, auth_headers, drain_jobs):
    project_id = _create_generated_project(client, auth_headers)
    drain_jobs()
    _run_action(client, auth_headers, project_id, "security-audit")
    other = _second_user_headers(client)
    assert client.get(f"/api/v1/projects/{project_id}/actions/history", headers=other).status_code == 404


def test_history_pagination(client, auth_headers, drain_jobs):
    project_id = _create_generated_project(client, auth_headers)
    drain_jobs()
    for action_id in ("security-audit", "generate-test-strategy", "generate-ci-cd", "generate-risk-register"):
        _run_action(client, auth_headers, project_id, action_id)

    page1 = _history(client, auth_headers, project_id, limit=2, offset=0)
    assert len(page1["items"]) == 2
    assert page1["total"] == 4
    page2 = _history(client, auth_headers, project_id, limit=2, offset=2)
    assert len(page2["items"]) == 2
    page3 = _history(client, auth_headers, project_id, limit=2, offset=4)
    assert page3["items"] == []
    ids1 = {item["id"] for item in page1["items"]}
    ids2 = {item["id"] for item in page2["items"]}
    assert not ids1 & ids2  # no overlap between pages


def test_history_detail_retrieval(client, auth_headers, drain_jobs):
    project_id = _create_generated_project(client, auth_headers)
    drain_jobs()
    body = _run_action(client, auth_headers, project_id, "generate-risk-register")
    history = _history(client, auth_headers, project_id)
    result_id = history["items"][0]["id"]
    resp = client.get(f"/api/v1/projects/{project_id}/actions/history/{result_id}", headers=auth_headers)
    assert resp.status_code == 200
    detail = resp.json()
    assert detail["id"] == result_id
    assert detail["project_id"] == project_id
    assert detail["action_id"] == "generate-risk-register"
    assert detail["status"] == body["status"]
    assert isinstance(detail["result"], dict)
    assert "quality" in detail
    assert "completeness" in detail
    assert detail["blueprint_revision"] >= 0


def test_history_detail_foreign_access_404(client, auth_headers, drain_jobs):
    project_id = _create_generated_project(client, auth_headers)
    drain_jobs()
    _run_action(client, auth_headers, project_id, "security-audit")
    result_id = _history(client, auth_headers, project_id)["items"][0]["id"]
    other = _second_user_headers(client)
    resp = client.get(f"/api/v1/projects/{project_id}/actions/history/{result_id}", headers=other)
    assert resp.status_code == 404


def test_history_detail_unknown_404(client, auth_headers, drain_jobs):
    project_id = _create_generated_project(client, auth_headers)
    drain_jobs()
    resp = client.get(f"/api/v1/projects/{project_id}/actions/history/999999", headers=auth_headers)
    assert resp.status_code == 404


def test_history_quality_fields(client, auth_headers, drain_jobs):
    project_id = _create_generated_project(client, auth_headers)
    drain_jobs()
    _run_action(client, auth_headers, project_id, "security-audit")
    item = _history(client, auth_headers, project_id)["items"][0]
    assert item["quality"] in ("valid", "invalid", "partial")


# ---------------------------------------------------------------------------
# Apply: valid, invalid result, wrong section, stale revision, unauthorized,
#        transactional rollback, unrelated sections preserved
# ---------------------------------------------------------------------------


def test_apply_valid_result_merges_section(client, auth_headers, drain_jobs):
    project_id = _create_generated_project(client, auth_headers)
    drain_jobs()
    before = client.get(f"/api/v1/projects/{project_id}", headers=auth_headers).json()["blueprint"]

    _run_action(client, auth_headers, project_id, "generate-test-strategy")
    result_id = _history(client, auth_headers, project_id)["items"][0]["id"]

    resp = client.post(
        f"/api/v1/projects/{project_id}/actions/history/{result_id}/apply",
        json={"confirm": True},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["success"] is True
    assert body["section"] == "testing"
    assert body["revision"] == 1

    after = client.get(f"/api/v1/projects/{project_id}", headers=auth_headers).json()["blueprint"]
    # The testing section changed; every unrelated section stayed identical.
    assert after["testing"] != before["testing"]
    for section in before:
        if section not in ("testing", "metadata", "validation"):
            assert before[section] == after[section], f"Section '{section}' changed unexpectedly"
    # Original keys in testing are preserved (merge, not replace).
    for key in ("summary",):
        assert key in after["testing"]


def test_apply_read_only_action_rejected(client, auth_headers, drain_jobs):
    project_id = _create_generated_project(client, auth_headers)
    drain_jobs()
    _run_action(client, auth_headers, project_id, "security-audit")  # apply_mode = none
    result_id = _history(client, auth_headers, project_id)["items"][0]["id"]
    resp = client.post(
        f"/api/v1/projects/{project_id}/actions/history/{result_id}/apply",
        json={"confirm": True},
        headers=auth_headers,
    )
    assert resp.status_code == 400
    assert "does not support" in resp.json()["detail"]


def test_apply_invalid_result_data_422(client, auth_headers, drain_jobs):
    project_id = _create_generated_project(client, auth_headers)
    drain_jobs()
    # Insert a result row whose data embeds a literal secret value.
    with SessionLocal() as db:
        from app.models.project import Project
        from app.services.action_results import create_action_result

        project = db.get(Project, project_id)
        create_action_result(
            db=db,
            project=project,
            action_id="generate-test-strategy",
            status="success",
            input_data={},
            result_data={"summary": "x", "password": "super-secret-abc12345"},
            section="testing",
            warnings=[],
            provider="deterministic",
            blueprint_revision=0,
        )
    result_id = _history(client, auth_headers, project_id)["items"][0]["id"]
    resp = client.post(
        f"/api/v1/projects/{project_id}/actions/history/{result_id}/apply",
        json={"confirm": True},
        headers=auth_headers,
    )
    assert resp.status_code == 422
    assert "secrets" in resp.json()["detail"].lower() or "credential" in resp.json()["detail"].lower()


def test_apply_wrong_section_rejected(client, auth_headers, drain_jobs):
    project_id = _create_generated_project(client, auth_headers)
    drain_jobs()
    with SessionLocal() as db:
        from app.models.project import Project
        from app.services.action_results import create_action_result

        project = db.get(Project, project_id)
        create_action_result(
            db=db,
            project=project,
            action_id="generate-test-strategy",
            status="success",
            input_data={},
            result_data={"summary": "misplaced"},
            section="analysis",  # wrong section for this action
            warnings=[],
            provider="deterministic",
            blueprint_revision=0,
        )
    result_id = _history(client, auth_headers, project_id)["items"][0]["id"]
    resp = client.post(
        f"/api/v1/projects/{project_id}/actions/history/{result_id}/apply",
        json={"confirm": True},
        headers=auth_headers,
    )
    assert resp.status_code == 422
    assert "cannot apply to section" in resp.json()["detail"]


def test_apply_requires_confirmation(client, auth_headers, drain_jobs):
    project_id = _create_generated_project(client, auth_headers)
    drain_jobs()
    _run_action(client, auth_headers, project_id, "generate-test-strategy")
    result_id = _history(client, auth_headers, project_id)["items"][0]["id"]
    resp = client.post(
        f"/api/v1/projects/{project_id}/actions/history/{result_id}/apply",
        json={"confirm": False},
        headers=auth_headers,
    )
    assert resp.status_code == 400
    assert "Confirmation required" in resp.json()["detail"]


def test_apply_stale_revision_rejected(client, auth_headers, drain_jobs):
    project_id = _create_generated_project(client, auth_headers)
    drain_jobs()
    _run_action(client, auth_headers, project_id, "generate-test-strategy")
    stale_result_id = _history(client, auth_headers, project_id)["items"][0]["id"]

    # Bump the revision by applying a roadmap transform result (replace mode).
    _run_action(client, auth_headers, project_id, "improve-requirements", {"section": "analysis"})
    fresh_result_id = _history(client, auth_headers, project_id)["items"][0]["id"]
    resp = client.post(
        f"/api/v1/projects/{project_id}/actions/history/{fresh_result_id}/apply",
        json={"confirm": True},
        headers=auth_headers,
    )
    assert resp.status_code == 200

    # The earlier result is now stale → 409, blueprint untouched again.
    resp = client.post(
        f"/api/v1/projects/{project_id}/actions/history/{stale_result_id}/apply",
        json={"confirm": True},
        headers=auth_headers,
    )
    assert resp.status_code == 409
    assert "based on blueprint revision 0" in resp.json()["detail"].lower()


def test_apply_foreign_user_404(client, auth_headers, drain_jobs):
    project_id = _create_generated_project(client, auth_headers)
    drain_jobs()
    _run_action(client, auth_headers, project_id, "generate-test-strategy")
    result_id = _history(client, auth_headers, project_id)["items"][0]["id"]
    other = _second_user_headers(client)
    resp = client.post(
        f"/api/v1/projects/{project_id}/actions/history/{result_id}/apply",
        json={"confirm": True},
        headers=other,
    )
    assert resp.status_code == 404


def test_apply_twice_conflict(client, auth_headers, drain_jobs):
    project_id = _create_generated_project(client, auth_headers)
    drain_jobs()
    _run_action(client, auth_headers, project_id, "generate-test-strategy")
    result_id = _history(client, auth_headers, project_id)["items"][0]["id"]
    first = client.post(
        f"/api/v1/projects/{project_id}/actions/history/{result_id}/apply",
        json={"confirm": True},
        headers=auth_headers,
    )
    assert first.status_code == 200
    second = client.post(
        f"/api/v1/projects/{project_id}/actions/history/{result_id}/apply",
        json={"confirm": True},
        headers=auth_headers,
    )
    assert second.status_code == 409
    assert "already been applied" in second.json()["detail"]


def test_apply_transactional_rollback(client, auth_headers, drain_jobs):
    """A failed apply must not partially commit anything."""
    project_id = _create_generated_project(client, auth_headers)
    drain_jobs()
    before = client.get(f"/api/v1/projects/{project_id}", headers=auth_headers).json()["blueprint"]

    with SessionLocal() as db:
        from app.models.project import Project
        from app.services.action_results import create_action_result

        project = db.get(Project, project_id)
        create_action_result(
            db=db,
            project=project,
            action_id="generate-test-strategy",
            status="success",
            input_data={},
            result_data={"summary": "x", "password": "super-secret-abc12345"},
            section="testing",
            warnings=[],
            provider="deterministic",
            blueprint_revision=0,
        )
    result_id = _history(client, auth_headers, project_id)["items"][0]["id"]
    resp = client.post(
        f"/api/v1/projects/{project_id}/actions/history/{result_id}/apply",
        json={"confirm": True},
        headers=auth_headers,
    )
    assert resp.status_code == 422

    after = client.get(f"/api/v1/projects/{project_id}", headers=auth_headers).json()["blueprint"]
    assert after == before  # no partial commit
    item = _history(client, auth_headers, project_id)["items"][0]
    assert item["applied"] is False
    with SessionLocal() as db:
        from app.services.action_results import get_current_blueprint_revision

        assert get_current_blueprint_revision(db, project_id) == 0  # no revision created


# ---------------------------------------------------------------------------
# Blueprint revisions
# ---------------------------------------------------------------------------


def test_revision_increment_and_audit_trail(client, auth_headers, drain_jobs):
    project_id = _create_generated_project(client, auth_headers)
    drain_jobs()
    blueprint = client.get(f"/api/v1/projects/{project_id}", headers=auth_headers).json()["blueprint"]
    previous_testing = copy.deepcopy(blueprint["testing"])

    _run_action(client, auth_headers, project_id, "generate-test-strategy")
    result_id = _history(client, auth_headers, project_id)["items"][0]["id"]
    resp = client.post(
        f"/api/v1/projects/{project_id}/actions/history/{result_id}/apply",
        json={"confirm": True},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["revision"] == 1

    with SessionLocal() as db:
        from app.models.blueprint_revision import BlueprintRevision

        rev = (
            db.query(BlueprintRevision)
            .filter(BlueprintRevision.project_id == project_id)
            .order_by(BlueprintRevision.revision.desc())
            .first()
        )
        assert rev is not None
        assert rev.revision == 1
        assert rev.source_action == "generate-test-strategy"
        assert rev.section == "testing"
        import json as _json

        assert _json.loads(rev.previous_section) == previous_testing  # safe snapshot

        from app.services.action_results import get_current_blueprint_revision

        assert get_current_blueprint_revision(db, project_id) == 1


def test_revision_unique_constraint_enforced_by_db(client, auth_headers, drain_jobs):
    """Two writers cannot both claim revision N — the database enforces it."""
    project_id = _create_generated_project(client, auth_headers)
    drain_jobs()
    with SessionLocal() as db:
        from app.models.blueprint_revision import BlueprintRevision

        db.add(
            BlueprintRevision(
                project_id=project_id, revision=1, section="testing", source_action="generate-test-strategy"
            )
        )
        db.commit()
        db.add(
            BlueprintRevision(
                project_id=project_id, revision=1, section="testing", source_action="generate-test-strategy"
            )
        )
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()


# ---------------------------------------------------------------------------
# Deterministic fallbacks (Part 13)
# ---------------------------------------------------------------------------


def test_fallback_security_audit_meaningful(client, auth_headers, drain_jobs):
    project_id = _create_generated_project(client, auth_headers)
    drain_jobs()
    body = _run_action(client, auth_headers, project_id, "security-audit")
    assert body["status"] == "fallback"
    result = body["result"]
    assert "summary" in result
    assert "findings" in result
    assert result["findings"]
    for finding in result["findings"]:
        assert finding["category"] in (
            "authentication",
            "authorization",
            "data_protection",
            "input_validation",
            "api_security",
            "secrets_management",
            "dependencies",
            "infrastructure",
            "deployment",
            "logging_monitoring",
            "domain_specific",
        )
        assert finding["status"] in ("identified_risk", "potential_risk", "missing_information", "recommendation")
        assert finding["severity"] in ("critical", "high", "medium", "low", "informational")
        assert finding["title"]
    assert "owasp_mapping" in result
    full = str(result).lower()
    # Absence is reported as "not specified", never as a confirmed vulnerability.
    assert "is vulnerable" not in full
    assert "not specified in the blueprint" in full
    assert "context" in result
    assert "note" in result


def test_fallback_test_strategy_derived_from_sections(client, auth_headers, drain_jobs):
    project_id = _create_generated_project(client, auth_headers)
    drain_jobs()
    body = _run_action(client, auth_headers, project_id, "generate-test-strategy")
    assert body["status"] == "fallback"
    assert body["section"] == "testing"
    result = body["result"]
    assert "api_tests" in result
    assert "database_tests" in result
    assert "frontend_tests" in result
    assert "tools" in result
    assert "coverage_targets" in result
    assert result["coverage_targets"]["unit"] == "not specified in the blueprint"
    assert "summary" in result
    assert "context" in result
    assert "note" in result


def test_fallback_ci_cd_from_detected_stack(client, auth_headers, drain_jobs):
    project_id = _create_generated_project(client, auth_headers)
    drain_jobs()
    body = _run_action(client, auth_headers, project_id, "generate-ci-cd")
    assert body["status"] == "fallback"
    assert body["section"] == "deployment"
    result = body["result"]
    assert result["platform"] == "GitHub Actions"
    assert any(stage["name"] == "install" for stage in result["pipeline_stages"])
    assert any(stage["name"] == "test" for stage in result["pipeline_stages"])
    assert "secrets" in result["environment_strategy"]["secrets_management"].lower()
    assert "context" in result
    assert "note" in result


def test_fallback_sprint_plan_derived_from_roadmap(client, auth_headers, drain_jobs):
    project_id = _create_generated_project(client, auth_headers)
    drain_jobs()
    body = _run_action(client, auth_headers, project_id, "generate-sprint-plan")
    assert body["status"] == "fallback"
    result = body["result"]
    assert "epics" in result
    assert "sprints" in result
    assert "team_composition" in result
    if result["epics"]:
        epic = result["epics"][0]
        assert "id" in epic
        assert "priority" in epic
        assert epic["priority"] in ("Must Have", "Should Have", "Nice to Have")
    assert "context" in result
    assert "note" in result


def test_fallback_risk_register_structure(client, auth_headers, drain_jobs):
    project_id = _create_generated_project(client, auth_headers)
    drain_jobs()
    body = _run_action(client, auth_headers, project_id, "generate-risk-register")
    assert body["status"] == "fallback"
    assert body["section"] == "business_risks"
    result = body["result"]
    assert result["risks"]
    assert result["risk_matrix"]
    for risk in result["risks"]:
        assert "id" in risk
        assert "category" in risk
        assert risk["likelihood"] in ("Low", "Medium", "High")
        assert risk["impact"] in ("Low", "Medium", "High")
        assert risk["severity"] in ("Low", "Medium", "High", "Critical")
        assert "mitigation" in risk
        assert "owner_role" in risk
        assert "monitoring_signal" in risk
        assert risk["status"] in ("open", "mitigated", "accepted", "transferred")
    assert "context" in result
    assert "note" in result


def test_fallback_compliance_no_legal_claims(client, auth_headers, drain_jobs):
    project_id = _create_generated_project(client, auth_headers)
    drain_jobs()
    body = _run_action(client, auth_headers, project_id, "generate-compliance-map")
    assert body["status"] == "fallback"
    result = body["result"]
    assert result["frameworks"]
    for framework in result["frameworks"]:
        assert framework["relevance"] in ("required", "potentially_relevant", "not_applicable")
        assert "controls" in framework
        for control in framework["controls"]:
            assert control["status"] in ("implemented", "partially_implemented", "missing", "not_assessed")
    assert "disclaimer" in result
    assert "not legal advice" in result["disclaimer"].lower()
    assert "is compliant" not in str(result).lower()
    assert "context" in result
    assert "note" in result


# ---------------------------------------------------------------------------
# Artifacts: CI artifact, test scaffold, ZIP traversal, secret exclusion
# ---------------------------------------------------------------------------


def _download_artifact(client, headers, project_id, action_id):
    resp = client.post(f"/api/v1/projects/{project_id}/actions/{action_id}/artifact", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "success"
    assert body["artifact"] is not None
    download = client.get(body["artifact"]["download_url"], headers=headers)
    assert download.status_code == 200
    assert download.headers["content-type"] == "application/zip"
    with zipfile.ZipFile(io.BytesIO(download.content)) as zf:
        names = zf.namelist()
        assert names
        for name in names:
            assert not name.startswith("/")
            assert ".." not in name
        return names, {n: zf.read(n).decode("utf-8", errors="replace") for n in names}


def test_ci_cd_artifact_generation(client, auth_headers, drain_jobs):
    project_id = _create_generated_project(client, auth_headers)
    drain_jobs()
    names, contents = _download_artifact(client, auth_headers, project_id, "generate-ci-cd")
    assert ".github/workflows/ci.yml" in names
    assert "actions/checkout@v4" in contents[".github/workflows/ci.yml"]
    # History records the artifact generation.
    history = _history(client, auth_headers, project_id)
    assert history["items"][0]["action_id"] == "generate-ci-cd"


def test_test_scaffold_artifact_generation(client, auth_headers, drain_jobs):
    project_id = _create_generated_project(client, auth_headers)
    drain_jobs()
    names, contents = _download_artifact(client, auth_headers, project_id, "generate-test-strategy")
    assert any(name.startswith("tests/") for name in names)
    assert "pytest.ini" in names  # FastAPI backend → pytest scaffold
    all_text = "\n".join(contents.values()).lower()
    assert "generated test scaffolding" in all_text


def test_artifact_zip_entries_are_path_safe(client, auth_headers, drain_jobs):
    project_id = _create_generated_project(client, auth_headers)
    drain_jobs()
    names, _ = _download_artifact(client, auth_headers, project_id, "generate-ci-cd")
    for name in names:
        assert "/" not in name.replace("\\", "/").split("/")[:-1]  # no nested .. implied
        assert ".." not in name
        assert not name.startswith("/")


def test_artifact_contains_no_secrets(client, auth_headers, drain_jobs):
    project_id = _create_generated_project(client, auth_headers)
    drain_jobs()
    _, contents = _download_artifact(client, auth_headers, project_id, "generate-ci-cd")
    text = "\n".join(contents.values())
    lower = text.lower()
    # Words like "secrets" are fine as references; literal values are not.
    for bad in ("api_key=", "password=", "sk-", "ghp_", "AKIA"):
        assert bad not in lower, f"Found potential secret literal '{bad}' in CI artifact"


def test_artifact_insufficient_stack_returns_none(client, auth_headers, drain_jobs):
    """The builder refuses to emit an artifact when the stack is too thin."""
    from app.services.actions.artifacts import build_ci_cd_artifact, build_test_scaffold

    project_id = _create_generated_project(client, auth_headers)
    drain_jobs()
    with SessionLocal() as db:
        from app.models.project import Project

        project = db.get(Project, project_id)
        project.preferred_backend = ""
        project.preferred_frontend = ""
        project.database = ""
        project.deployment_platform = ""
        db.commit()
        # Empty blueprint → no project fields, no selected_stack, no technology.
        assert build_ci_cd_artifact(project, {}) is None
        assert build_test_scaffold(project, {}) is None


# ---------------------------------------------------------------------------
# E2E: Hospital Management System (Part 22 workflow)
# ---------------------------------------------------------------------------


def test_hospital_e2e_action_intelligence_flow(client, auth_headers, drain_jobs):
    project_id = _create_generated_project(client, auth_headers, PROJECT_PAYLOAD)
    drain_jobs()

    # 1. Blueprint generated (drained above).

    # 2-5. Run the specialized actions.
    _run_action(client, auth_headers, project_id, "security-audit")
    test_strategy = _run_action(client, auth_headers, project_id, "generate-test-strategy")
    ci_cd = _run_action(client, auth_headers, project_id, "generate-ci-cd")
    _run_action(client, auth_headers, project_id, "generate-risk-register")
    assert test_strategy["status"] == "fallback"
    assert ci_cd["status"] == "fallback"

    # 6. View action history.
    history = _history(client, auth_headers, project_id)
    assert history["total"] >= 4

    # 7. Apply one supported result (generate-test-strategy → testing section).
    test_strategy_id = None
    stale_ci_id = None
    for item in history["items"]:
        if item["action_id"] == "generate-test-strategy":
            test_strategy_id = item["id"]
        if item["action_id"] == "generate-ci-cd":
            stale_ci_id = item["id"]
    assert test_strategy_id is not None
    assert stale_ci_id is not None

    before = client.get(f"/api/v1/projects/{project_id}", headers=auth_headers).json()["blueprint"]
    resp = client.post(
        f"/api/v1/projects/{project_id}/actions/history/{test_strategy_id}/apply",
        json={"confirm": True},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["revision"] == 1

    # 8. Blueprint revision increments.
    with SessionLocal() as db:
        from app.services.action_results import get_current_blueprint_revision

        assert get_current_blueprint_revision(db, project_id) == 1

    # 9. Unrelated sections remain unchanged.
    after = client.get(f"/api/v1/projects/{project_id}", headers=auth_headers).json()["blueprint"]
    for section in before:
        if section not in ("testing", "metadata", "validation"):
            assert before[section] == after[section], f"Section '{section}' changed unexpectedly"

    # 10. Run another action (read-only).
    _run_action(client, auth_headers, project_id, "generate-sprint-plan")

    # 11-12. Attempt to apply the stale CI/CD result (based on revision 0).
    resp = client.post(
        f"/api/v1/projects/{project_id}/actions/history/{stale_ci_id}/apply",
        json={"confirm": True},
        headers=auth_headers,
    )
    assert resp.status_code == 409
    assert "based on blueprint revision 0" in resp.json()["detail"].lower()

    # 13. Generate CI artifact.
    names, contents = _download_artifact(client, auth_headers, project_id, "generate-ci-cd")
    assert ".github/workflows/ci.yml" in names

    # 14. Generate test scaffold.
    names, _ = _download_artifact(client, auth_headers, project_id, "generate-test-strategy")
    assert any(name.startswith("tests/") for name in names)


# ---------------------------------------------------------------------------
# E2E: Food Delivery Platform — domain-specific fallback analysis
# ---------------------------------------------------------------------------


def test_food_delivery_domain_specific_fallbacks(client, auth_headers, drain_jobs):
    project_id = _create_generated_project(client, auth_headers, FOOD_DELIVERY_PAYLOAD)
    drain_jobs()

    # Security audit fallback is grounded in the food-delivery domain.
    body = _run_action(client, auth_headers, project_id, "security-audit")
    assert body["status"] == "fallback"
    full = str(body["result"]).lower()
    assert any(term in full for term in ("restaurant", "order", "delivery", "menu", "food"))

    # Risk register fallback uses domain vocabulary from the blueprint context.
    body = _run_action(client, auth_headers, project_id, "generate-risk-register")
    assert body["status"] == "fallback"
    full = str(body["result"]).lower()
    assert any(term in full for term in ("restaurant", "order", "delivery", "menu"))

    # Compliance fallback must not surface HIPAA for a food-delivery domain
    # and must carry the disclaimer.
    body = _run_action(client, auth_headers, project_id, "generate-compliance-map")
    assert body["status"] == "fallback"
    result = body["result"]
    framework_names = [f["framework"].lower() for f in result["frameworks"]]
    assert "hipaa" not in framework_names
    assert "not legal advice" in result["disclaimer"].lower()


def test_hospital_food_domain_isolation_in_fallback(client, auth_headers, drain_jobs):
    """Hospital fallback never borrows food-delivery vocabulary."""
    project_id = _create_generated_project(client, auth_headers, PROJECT_PAYLOAD)
    drain_jobs()
    body = _run_action(client, auth_headers, project_id, "security-audit")
    full = str(body["result"]).lower()
    for term in ("restaurant", "courier", "dish", "chef", "kitchen", "takeaway", "meal", "recipe"):
        assert term not in full, f"Found food term '{term}' in hospital fallback"
    assert any(term in full for term in ("patient", "health", "hospital", "clinic", "medical"))
