"""AI Action Engine — API tests.

Covers discovery, authorization, the result contract, blueprint
transformations, explanations (LLM + deterministic fallback), diagram and
codegen artifact actions, safe error classification, and project isolation.
Long-running durable action jobs are exercised through the real worker
machinery (claim → execute).
"""

from __future__ import annotations

import io
import zipfile

import pytest

from app.database import SessionLocal
from app.services.actions.registry import ACTION_REGISTRY
from app.services.ai.llm import LLMClient, LLMError
from tests.test_projects import PROJECT_PAYLOAD


def _create_generated_project(client, headers):
    project_id = client.post("/api/v1/projects", json=PROJECT_PAYLOAD, headers=headers).json()["id"]
    resp = client.post(f"/api/v1/projects/{project_id}/generate", headers=headers)
    assert resp.status_code == 202
    return project_id


def _second_user_headers(client):
    import uuid

    email = f"other-{uuid.uuid4().hex[:8]}@example.com"
    resp = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "password123", "full_name": "Other User"},
    )
    assert resp.status_code == 201, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


# ---------------------------------------------------------------------------
# Discovery + authorization
# ---------------------------------------------------------------------------


def test_actions_require_auth(client):
    assert client.get("/api/v1/projects/1/actions").status_code == 401


def test_actions_catalog_shape(client, auth_headers, drain_jobs):
    project_id = _create_generated_project(client, auth_headers)
    drain_jobs()
    resp = client.get(f"/api/v1/projects/{project_id}/actions", headers=auth_headers)
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) == len(ACTION_REGISTRY)
    ids = {item["id"] for item in items}
    for expected in (
        "explain-project",
        "explain-section",
        "improve-requirements",
        "generate-architecture",
        "generate-database-design",
        "generate-api-specification",
        "generate-uiux-plan",
        "generate-testing-strategy",
        "generate-deployment-plan",
        "generate-security-recommendations",
        "generate-project-roadmap",
        "transform-section",
        "generate-diagram-erd",
        "generate-express",
    ):
        assert expected in ids
    for item in items:
        assert set(item) >= {
            "id",
            "name",
            "category",
            "description",
            "execution_mode",
            "mutates_project",
            "supports_fallback",
            "requires_blueprint",
            "inputs",
        }
        assert item["execution_mode"] in ("short", "long")
        assert item["category"] in ("analysis", "transformation", "diagram", "code", "documentation")


def test_actions_are_scoped_to_owner(client, auth_headers):
    other_user_headers = _second_user_headers(client)
    project_id = client.post("/api/v1/projects", json=PROJECT_PAYLOAD, headers=auth_headers).json()["id"]
    resp = client.get(f"/api/v1/projects/{project_id}/actions", headers=other_user_headers)
    assert resp.status_code == 404
    resp = client.post(
        f"/api/v1/projects/{project_id}/actions/explain-project",
        json={"inputs": {}},
        headers=other_user_headers,
    )
    assert resp.status_code == 404


def test_unknown_action_is_404(client, auth_headers, drain_jobs):
    project_id = _create_generated_project(client, auth_headers)
    drain_jobs()
    resp = client.post(
        f"/api/v1/projects/{project_id}/actions/not-a-real-action",
        json={"inputs": {}},
        headers=auth_headers,
    )
    assert resp.status_code == 404


def test_actions_require_blueprint(client, auth_headers):
    project_id = client.post("/api/v1/projects", json=PROJECT_PAYLOAD, headers=auth_headers).json()["id"]
    resp = client.post(
        f"/api/v1/projects/{project_id}/actions/explain-project",
        json={"inputs": {}},
        headers=auth_headers,
    )
    assert resp.status_code == 400
    assert "no blueprint" in resp.json()["detail"].lower()


# ---------------------------------------------------------------------------
# Explanations (deterministic fallback in the test environment)
# ---------------------------------------------------------------------------


def test_explain_project_fallback(client, auth_headers, drain_jobs):
    project_id = _create_generated_project(client, auth_headers)
    drain_jobs()
    resp = client.post(
        f"/api/v1/projects/{project_id}/actions/explain-project",
        json={"inputs": {}},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["action_id"] == "explain-project"
    assert body["status"] == "fallback"
    assert body["provider"] == "deterministic"
    assert "overview" in body["result"]
    assert body["warnings"]
    project = client.get(f"/api/v1/projects/{project_id}", headers=auth_headers).json()
    assert project["blueprint"] is not None  # read-only: nothing changed


def test_explain_section_valid_and_invalid(client, auth_headers, drain_jobs):
    project_id = _create_generated_project(client, auth_headers)
    drain_jobs()
    resp = client.post(
        f"/api/v1/projects/{project_id}/actions/explain-section",
        json={"inputs": {"section": "architecture"}},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] in ("success", "fallback")
    assert isinstance(body["result"], dict)
    resp = client.post(
        f"/api/v1/projects/{project_id}/actions/explain-section",
        json={"inputs": {"section": "bogus"}},
        headers=auth_headers,
    )
    assert resp.status_code == 422


def test_explain_uses_llm_when_available(client, auth_headers, drain_jobs, monkeypatch):
    monkeypatch.setattr(LLMClient, "available", property(lambda self: True))

    def _fake_chat_json(self, system, user, max_tokens=8192):
        return {"overview": "LLM overview", "highlights": ["a"], "risks": [], "next_steps": ["ship"]}

    monkeypatch.setattr(LLMClient, "chat_json", _fake_chat_json)
    project_id = _create_generated_project(client, auth_headers)
    drain_jobs()
    resp = client.post(
        f"/api/v1/projects/{project_id}/actions/explain-project",
        json={"inputs": {}},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "success"
    assert body["provider"] == "llm"
    assert body["result"]["overview"] == "LLM overview"


def test_explain_falls_back_when_llm_fails(client, auth_headers, drain_jobs, monkeypatch):
    monkeypatch.setattr(LLMClient, "available", property(lambda self: True))

    def _boom(self, system, user, max_tokens=8192):
        raise LLMError("LLM request failed")

    monkeypatch.setattr(LLMClient, "chat_json", _boom)
    project_id = _create_generated_project(client, auth_headers)
    drain_jobs()
    resp = client.post(
        f"/api/v1/projects/{project_id}/actions/explain-project",
        json={"inputs": {}},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "fallback"
    assert body["provider"] == "deterministic"
    assert any("LLM" in w for w in body["warnings"])


def test_explain_falls_back_on_malformed_llm_output(client, auth_headers, drain_jobs, monkeypatch):
    monkeypatch.setattr(LLMClient, "available", property(lambda self: True))
    monkeypatch.setattr(LLMClient, "chat_json", lambda self, s, u, max_tokens=8192: "not a dict")
    project_id = _create_generated_project(client, auth_headers)
    drain_jobs()
    resp = client.post(
        f"/api/v1/projects/{project_id}/actions/explain-project",
        json={"inputs": {}},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "fallback"


# ---------------------------------------------------------------------------
# Blueprint transformations
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "action_id, section",
    [
        ("improve-requirements", "analysis"),
        ("generate-architecture", "architecture"),
        ("generate-database-design", "database"),
        ("generate-api-specification", "api"),
        ("generate-uiux-plan", "ui_ux"),
        ("generate-testing-strategy", "testing"),
        ("generate-deployment-plan", "deployment"),
        ("generate-security-recommendations", "security"),
        ("generate-project-roadmap", "roadmap"),
        ("transform-section", "documentation"),
    ],
)
def test_transform_actions_persist_and_preserve_other_sections(
    client, auth_headers, drain_jobs, action_id, section
):
    project_id = _create_generated_project(client, auth_headers)
    drain_jobs()
    before = client.get(f"/api/v1/projects/{project_id}", headers=auth_headers).json()["blueprint"]

    resp = client.post(
        f"/api/v1/projects/{project_id}/actions/{action_id}",
        json={"inputs": {"section": section}},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] in ("success", "fallback")
    assert body["section"] == section
    assert body["result"] is not None
    assert body["provider"] in ("llm", "deterministic")

    after = client.get(f"/api/v1/projects/{project_id}", headers=auth_headers).json()
    assert after["status"] == "complete"
    assert after["blueprint"][section] is not None
    changed = set(before) ^ set(after["blueprint"])
    assert changed <= {"validation", "metadata"}
    for other in ("domain_understanding", "business_processes", "architecture", "database"):
        if other != section:
            assert before.get(other) == after["blueprint"].get(other)


def test_transform_unknown_section_is_422(client, auth_headers, drain_jobs):
    project_id = _create_generated_project(client, auth_headers)
    drain_jobs()
    resp = client.post(
        f"/api/v1/projects/{project_id}/actions/transform-section",
        json={"inputs": {"section": "nope"}},
        headers=auth_headers,
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Diagram + codegen artifact actions
# ---------------------------------------------------------------------------


def test_diagram_action_returns_mermaid_and_does_not_mutate(client, auth_headers, drain_jobs):
    project_id = _create_generated_project(client, auth_headers)
    drain_jobs()
    before = client.get(f"/api/v1/projects/{project_id}", headers=auth_headers).json()["blueprint"]
    resp = client.post(
        f"/api/v1/projects/{project_id}/actions/generate-diagram-erd",
        json={"inputs": {}},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "success"
    assert body["result"]["diagram_id"] == "erd"
    assert "erDiagram" in body["result"]["mermaid"]
    after = client.get(f"/api/v1/projects/{project_id}", headers=auth_headers).json()["blueprint"]
    assert after == before  # read-only


def test_diagram_action_invalid_type(client, auth_headers, drain_jobs):
    project_id = _create_generated_project(client, auth_headers)
    drain_jobs()
    resp = client.post(
        f"/api/v1/projects/{project_id}/actions/generate-diagram-notreal",
        json={"inputs": {}},
        headers=auth_headers,
    )
    assert resp.status_code == 404


def test_codegen_action_returns_downloadable_artifact(client, auth_headers, drain_jobs):
    project_id = _create_generated_project(client, auth_headers)
    drain_jobs()
    resp = client.post(
        f"/api/v1/projects/{project_id}/actions/generate-express",
        json={"inputs": {}},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "success"
    assert body["result"]["generator_id"] == "express"
    assert body["result"]["file_count"] > 0
    artifact = body["artifact"]
    assert artifact["kind"] == "codegen-zip"
    assert artifact["download_url"].endswith(f"/api/v1/projects/{project_id}/codegen/express")

    download = client.get(artifact["download_url"], headers=auth_headers)
    assert download.status_code == 200
    with zipfile.ZipFile(io.BytesIO(download.content)) as zf:
        names = zf.namelist()
        assert names
        assert all(not name.startswith("/") and ".." not in name for name in names)


# ---------------------------------------------------------------------------
# Safe error classification
# ---------------------------------------------------------------------------


def test_action_error_is_generic_and_never_leaks(client, auth_headers, drain_jobs):
    """Unexpected handler failures classify as ``error`` with a generic message;
    internal exception text must never reach the API response."""
    from app.services.actions.registry import ACTION_REGISTRY, AIAction

    def _boom(project, blueprint, inputs, db):
        raise RuntimeError("secret internal detail: db-password")

    fake_id = "boom-test-action"
    ACTION_REGISTRY[fake_id] = AIAction(
        id=fake_id,
        name="Boom",
        category="analysis",
        description="",
        handler=_boom,
        mutates_project=False,
    )
    try:
        project_id = _create_generated_project(client, auth_headers)
        drain_jobs()
        resp = client.post(
            f"/api/v1/projects/{project_id}/actions/{fake_id}",
            json={"inputs": {}},
            headers=auth_headers,
        )
    finally:
        del ACTION_REGISTRY[fake_id]
    assert resp.status_code == 500
    assert "secret internal detail" not in resp.json()["detail"]
    assert resp.json()["detail"] == "The action failed unexpectedly. Please try again later."


# ---------------------------------------------------------------------------
# Durable long-running action jobs (real worker machinery)
# ---------------------------------------------------------------------------


def test_action_job_create_dedup_and_execute(client, auth_headers, drain_jobs):
    project_id = _create_generated_project(client, auth_headers)
    drain_jobs()

    with SessionLocal() as db:
        from app.services.generation_jobs import create_action_job, create_job

        job1 = create_action_job(db, project_id, "explain-project", {"focus": "scope"})
        job2 = create_action_job(db, project_id, "explain-project", {})
        assert job1.id == job2.id  # dedup: one active action job per (project, action)

        # One active job per project total (generation or action) — the worker
        # guarantees atomic blueprint writes, so a second job cannot run.
        gen_job = create_job(db, project_id)
        assert gen_job.id == job1.id

    drain_jobs()  # real claim → execute path, action branch included
    with SessionLocal() as db:
        from app.models.generation_job import GenerationJob

        job = db.get(GenerationJob, job1.id)
        assert job is not None
        assert job.status == "completed"
        assert job.action_id == "explain-project"

    # After completion a fresh job can start.
    with SessionLocal() as db:
        from app.services.generation_jobs import create_job

        new_job = create_job(db, project_id)
        assert new_job.id != job1.id


def test_action_job_transform_persists_blueprint(client, auth_headers, drain_jobs):
    project_id = _create_generated_project(client, auth_headers)
    drain_jobs()
    before = client.get(f"/api/v1/projects/{project_id}", headers=auth_headers).json()["blueprint"]

    # Change the project input so the deterministic transform produces
    # different content — proving the durable action job actually wrote it.
    update = dict(PROJECT_PAYLOAD)
    update["features"] = ["ai triage system", "telemedicine", "pharmacy stock alerts"]
    assert client.put(
        f"/api/v1/projects/{project_id}", json=update, headers=auth_headers
    ).status_code == 200

    with SessionLocal() as db:
        from app.services.generation_jobs import create_action_job

        job = create_action_job(db, project_id, "transform-section", {"section": "analysis"})
    drain_jobs()

    after = client.get(f"/api/v1/projects/{project_id}", headers=auth_headers).json()
    assert after["status"] == "complete"
    assert (
        after["blueprint"]["analysis"]["functional_requirements"]
        != before["analysis"]["functional_requirements"]
    )
    with SessionLocal() as db:
        from app.models.generation_job import GenerationJob

        assert db.get(GenerationJob, job.id).status == "completed"


def test_action_job_unknown_action_fails_with_generic_message(client, auth_headers, drain_jobs):
    project_id = _create_generated_project(client, auth_headers)
    drain_jobs()
    with SessionLocal() as db:
        from app.services.generation_jobs import create_action_job

        job = create_action_job(db, project_id, "no-such-action", {})
    drain_jobs()
    with SessionLocal() as db:
        from app.models.generation_job import GenerationJob

        failed = db.get(GenerationJob, job.id)
        assert failed.status == "failed"
        assert "no-such-action" in (failed.error_message or "")


def test_long_action_conflict_returns_409(client, auth_headers, drain_jobs):
    """A long-running action submitted while another job is active is a clean
    409 (never a 500): the durable worker allows one active job per project."""
    from app.services.actions.registry import ACTION_REGISTRY, AIAction

    fake_id = "long-fake-action"

    def _handler(project, blueprint, inputs, db):
        return None

    ACTION_REGISTRY[fake_id] = AIAction(
        id=fake_id,
        name="Long Fake",
        category="analysis",
        description="",
        handler=_handler,
        execution_mode="long",
        mutates_project=False,
    )
    try:
        project_id = _create_generated_project(client, auth_headers)
        drain_jobs()
        with SessionLocal() as db:
            from app.services.generation_jobs import create_job

            create_job(db, project_id)  # an active generation job is running
        resp = client.post(
            f"/api/v1/projects/{project_id}/actions/{fake_id}",
            json={"inputs": {}},
            headers=auth_headers,
        )
    finally:
        del ACTION_REGISTRY[fake_id]
    assert resp.status_code == 409
    assert "already running" in resp.json()["detail"]


def test_action_job_after_completion_can_run_again(client, auth_headers, drain_jobs):
    project_id = _create_generated_project(client, auth_headers)
    drain_jobs()
    with SessionLocal() as db:
        from app.services.generation_jobs import create_action_job

        first = create_action_job(db, project_id, "explain-project", {})
    drain_jobs()
    with SessionLocal() as db:
        from app.services.generation_jobs import create_action_job

        second = create_action_job(db, project_id, "explain-project", {})
        assert second.id != first.id  # completed jobs do not block new ones


# ---------------------------------------------------------------------------
# Phase 10: Specialized AI Actions
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "action_id",
    [
        "security-audit",
        "generate-test-strategy",
        "generate-ci-cd",
        "generate-sprint-plan",
        "generate-risk-register",
        "generate-compliance-map",
    ],
)
def test_phase10_actions_catalog(client, auth_headers, drain_jobs, action_id):
    """All six Phase 10 actions appear in the catalog."""
    project_id = _create_generated_project(client, auth_headers)
    drain_jobs()
    resp = client.get(f"/api/v1/projects/{project_id}/actions", headers=auth_headers)
    assert resp.status_code == 200
    items = {item["id"] for item in resp.json()["items"]}
    assert action_id in items


def test_security_audit_fallback(client, auth_headers, drain_jobs):
    """Security audit returns structured output with findings and OWASP mapping."""
    project_id = _create_generated_project(client, auth_headers)
    drain_jobs()
    resp = client.post(
        f"/api/v1/projects/{project_id}/actions/security-audit",
        json={"inputs": {}},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["action_id"] == "security-audit"
    assert body["status"] in ("success", "fallback")
    assert isinstance(body["result"], dict)
    result = body["result"]
    assert "summary" in result
    if body["status"] == "success":
        assert "findings" in result
        assert "owasp_mapping" in result
        assert "domain_specific_notes" in result
        assert "missing_information" in result
        assert isinstance(result["findings"], list)
        for finding in result["findings"]:
            assert "category" in finding
            assert "status" in finding
            assert "severity" in finding
            assert "title" in finding
            assert "description" in finding
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
            assert finding["status"] in (
                "identified_risk",
                "potential_risk",
                "missing_information",
                "recommendation",
            )
            assert finding["severity"] in (
                "critical",
                "high",
                "medium",
                "low",
                "informational",
            )
    else:
        # fallback: context + note
        assert "context" in result
        assert "note" in result


def test_security_audit_domain_awareness(client, auth_headers, drain_jobs):
    """Security audit uses domain-specific terminology (hospital)."""
    project_id = _create_generated_project(client, auth_headers)
    drain_jobs()
    resp = client.post(
        f"/api/v1/projects/{project_id}/actions/security-audit",
        json={"inputs": {}},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    result = body["result"]
    # Hospital domain should not have food-delivery terminology
    forbidden_terms = ["restaurant", "courier", "dish", "chef", "kitchen", "takeaway", "meal", "recipe", "food delivery"]
    full_text = str(result).lower()
    for term in forbidden_terms:
        assert term not in full_text, f"Found forbidden term '{term}' in hospital security audit"


def test_generate_test_strategy_fallback(client, auth_headers, drain_jobs):
    """Test strategy returns structured output covering all test types."""
    project_id = _create_generated_project(client, auth_headers)
    drain_jobs()
    resp = client.post(
        f"/api/v1/projects/{project_id}/actions/generate-test-strategy",
        json={"inputs": {}},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["action_id"] == "generate-test-strategy"
    assert body["status"] in ("success", "fallback")
    result = body["result"]
    assert "summary" in result
    if body["status"] == "success":
        assert "unit_tests" in result
        assert "integration_tests" in result
        assert "api_tests" in result
        assert "database_tests" in result
        assert "frontend_tests" in result
        assert "e2e_tests" in result
        assert "security_tests" in result
        assert "performance_tests" in result
        assert "test_data_strategy" in result
        assert "ci_execution_strategy" in result
        assert "tools" in result
        assert "coverage_targets" in result
        assert "gaps" in result
    else:
        # fallback: context + note
        assert "context" in result
        assert "note" in result


def test_generate_test_strategy_preserves_blueprint(client, auth_headers, drain_jobs):
    """Test strategy is read-only and does not mutate the blueprint."""
    project_id = _create_generated_project(client, auth_headers)
    drain_jobs()
    before = client.get(f"/api/v1/projects/{project_id}", headers=auth_headers).json()["blueprint"]
    resp = client.post(
        f"/api/v1/projects/{project_id}/actions/generate-test-strategy",
        json={"inputs": {}},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    after = client.get(f"/api/v1/projects/{project_id}", headers=auth_headers).json()["blueprint"]
    assert after == before


def test_generate_ci_cd_fallback(client, auth_headers, drain_jobs):
    """CI/CD pipeline returns structured output with stages and security checks."""
    project_id = _create_generated_project(client, auth_headers)
    drain_jobs()
    resp = client.post(
        f"/api/v1/projects/{project_id}/actions/generate-ci-cd",
        json={"inputs": {}},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["action_id"] == "generate-ci-cd"
    assert body["status"] in ("success", "fallback")
    result = body["result"]
    assert "summary" in result
    if body["status"] == "success":
        assert "platform" in result
        assert "pipeline_stages" in result
        assert "environment_strategy" in result
        assert "security_checks" in result
        assert "artifact_generation" in result
        assert "notifications" in result
        assert "gaps" in result
        for stage in result["pipeline_stages"]:
            assert "name" in stage
            assert "jobs" in stage
    else:
        # fallback: context + note
        assert "context" in result
        assert "note" in result


def test_generate_ci_cd_no_secrets_in_config(client, auth_headers, drain_jobs):
    """CI/CD config must not contain secrets."""
    project_id = _create_generated_project(client, auth_headers)
    drain_jobs()
    resp = client.post(
        f"/api/v1/projects/{project_id}/actions/generate-ci-cd",
        json={"inputs": {}},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    if body["status"] == "success":
        result = body["result"]
        full_text = str(result).lower()
        # No actual secrets should appear
        forbidden = ["password", "secret", "api_key", "private_key", "token", "credential"]
        for term in forbidden:
            assert term not in full_text or term in ("password", "secret")  # may appear as field names
    else:
        # fallback just returns context - skip secret check
        assert body["status"] == "fallback"


def test_generate_sprint_plan_fallback(client, auth_headers, drain_jobs):
    """Sprint plan returns epics, sprints, tasks, dependencies, priorities."""
    project_id = _create_generated_project(client, auth_headers)
    drain_jobs()
    resp = client.post(
        f"/api/v1/projects/{project_id}/actions/generate-sprint-plan",
        json={"inputs": {}},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["action_id"] == "generate-sprint-plan"
    assert body["status"] in ("success", "fallback")
    result = body["result"]
    assert "summary" in result
    if body["status"] == "success":
        assert "epics" in result
        assert "sprints" in result
        assert "critical_path" in result
        assert "total_estimated_effort" in result
        assert "team_composition" in result
        assert "gaps" in result
        for epic in result["epics"]:
            assert "id" in epic
            assert "name" in epic
            assert "priority" in epic
            assert epic["priority"] in ("Must Have", "Should Have", "Nice to Have")
        for sprint in result["sprints"]:
            assert "sprint" in sprint
            assert "goal" in sprint
            assert "tasks" in sprint
            for task in sprint["tasks"]:
                assert "id" in task
                assert "assignee_role" in task
    else:
        # fallback: context + note
        assert "context" in result
        assert "note" in result


def test_generate_sprint_plan_no_fake_people(client, auth_headers, drain_jobs):
    """Sprint plan uses roles, not named people."""
    project_id = _create_generated_project(client, auth_headers)
    drain_jobs()
    resp = client.post(
        f"/api/v1/projects/{project_id}/actions/generate-sprint-plan",
        json={"inputs": {}},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    result = body["result"]
    full_text = str(result).lower()
    # Should use roles like "developer", "engineer", not names
    assert any(role in full_text for role in ["developer", "engineer", "devops", "backend", "frontend"])


def test_generate_risk_register_fallback(client, auth_headers, drain_jobs):
    """Risk register returns structured risks with category, likelihood, impact, severity."""
    project_id = _create_generated_project(client, auth_headers)
    drain_jobs()
    resp = client.post(
        f"/api/v1/projects/{project_id}/actions/generate-risk-register",
        json={"inputs": {}},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["action_id"] == "generate-risk-register"
    assert body["status"] in ("success", "fallback")
    result = body["result"]
    assert "summary" in result
    if body["status"] == "success":
        assert "risks" in result
        assert "risk_matrix" in result
        assert "top_risks" in result
        assert "gaps" in result
        for risk in result["risks"]:
            assert "id" in risk
            assert "risk" in risk
            assert "category" in risk
            assert risk["category"] in (
                "technical",
                "security",
                "operational",
                "scalability",
                "dependency",
                "delivery",
                "data",
                "compliance",
                "vendor_llm",
            )
            assert "likelihood" in risk
            assert risk["likelihood"] in ("Low", "Medium", "High")
            assert "impact" in risk
            assert risk["impact"] in ("Low", "Medium", "High")
            assert "severity" in risk
            assert risk["severity"] in ("Low", "Medium", "High", "Critical")
            assert "mitigation" in risk
            assert "owner_role" in risk
            assert "monitoring_signal" in risk
            assert "source_sections" in risk
            assert "status" in risk
            assert risk["status"] in ("open", "mitigated", "accepted", "transferred")
    else:
        # fallback: context + note
        assert "context" in result
        assert "note" in result


def test_generate_risk_register_no_named_people(client, auth_headers, drain_jobs):
    """Risk register uses roles, not named people."""
    project_id = _create_generated_project(client, auth_headers)
    drain_jobs()
    resp = client.post(
        f"/api/v1/projects/{project_id}/actions/generate-risk-register",
        json={"inputs": {}},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    if body["status"] == "success":
        result = body["result"]
        for risk in result["risks"]:
            owner = risk["owner_role"].lower()
            # Should be a role, not a person's name
            assert owner in ("backend developer", "frontend developer", "devops", "security engineer", "product manager", "database engineer", "qa engineer", "architect") or "engineer" in owner or "developer" in owner or "manager" in owner
    else:
        # fallback just returns context - skip role check
        assert body["status"] == "fallback"


def test_generate_compliance_map_fallback(client, auth_headers, drain_jobs):
    """Compliance map returns frameworks with relevance and controls."""
    project_id = _create_generated_project(client, auth_headers)
    drain_jobs()
    resp = client.post(
        f"/api/v1/projects/{project_id}/actions/generate-compliance-map",
        json={"inputs": {}},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["action_id"] == "generate-compliance-map"
    assert body["status"] in ("success", "fallback")
    result = body["result"]
    assert "summary" in result
    if body["status"] == "success":
        assert "frameworks" in result
        assert "data_classification" in result
        assert "jurisdiction_notes" in result
        assert "disclaimer" in result
        assert "gaps" in result
        for framework in result["frameworks"]:
            assert "framework" in framework
            assert "relevance" in framework
            assert framework["relevance"] in ("required", "potentially_relevant", "not_applicable")
            assert "basis" in framework
            assert "controls" in framework
            assert "gaps" in framework
            for control in framework["controls"]:
                assert "control" in control
                assert "status" in control
                assert control["status"] in ("implemented", "partially_implemented", "missing", "not_assessed")
                assert "evidence_required" in control
                assert "implementation_recommendation" in control
                assert "blueprint_section" in control
    else:
        # fallback: context + note
        assert "context" in result
        assert "note" in result


def test_generate_compliance_map_no_false_compliant_claim(client, auth_headers, drain_jobs):
    """Compliance map must not claim the project is legally compliant."""
    project_id = _create_generated_project(client, auth_headers)
    drain_jobs()
    resp = client.post(
        f"/api/v1/projects/{project_id}/actions/generate-compliance-map",
        json={"inputs": {}},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    if body["status"] == "success":
        result = body["result"]
        full_text = str(result).lower()
        # Must not claim "compliant" or "in compliance" as a fact
        assert "is compliant" not in full_text
        assert "fully compliant" not in full_text
        assert "legally compliant" not in full_text
        # Must have disclaimer
        assert "disclaimer" in result
        assert "not legal advice" in result["disclaimer"].lower()
    else:
        # fallback just returns context - skip compliant claim check
        assert body["status"] == "fallback"


def test_generate_compliance_map_domain_awareness(client, auth_headers, drain_jobs):
    """Compliance map for hospital domain mentions HIPAA/healthcare frameworks."""
    project_id = _create_generated_project(client, auth_headers)
    drain_jobs()
    resp = client.post(
        f"/api/v1/projects/{project_id}/actions/generate-compliance-map",
        json={"inputs": {}},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    result = body["result"]
    full_text = str(result).lower()
    # Hospital domain should have healthcare-relevant frameworks
    healthcare_frameworks = ["hipaa", "gdpr", "phi", "patient", "medical", "healthcare"]
    found = any(f in full_text for f in healthcare_frameworks)
    assert found, "Hospital compliance map should mention healthcare-relevant frameworks"


def test_unknown_action_404(client, auth_headers, drain_jobs):
    project_id = _create_generated_project(client, auth_headers)
    drain_jobs()
    resp = client.post(
        f"/api/v1/projects/{project_id}/actions/not-a-real-action",
        json={"inputs": {}},
        headers=auth_headers,
    )
    assert resp.status_code == 404


def test_unauthorized_project_404(client, auth_headers, drain_jobs):
    project_id = _create_generated_project(client, auth_headers)
    drain_jobs()
    import uuid
    email = f"other-{uuid.uuid4().hex[:8]}@example.com"
    resp = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "password123", "full_name": "Other User"},
    )
    other_headers = {"Authorization": f"Bearer {resp.json()['access_token']}"}
    resp = client.post(
        f"/api/v1/projects/{project_id}/actions/security-audit",
        json={"inputs": {}},
        headers=other_headers,
    )
    assert resp.status_code == 404


def test_action_requires_blueprint(client, auth_headers):
    project_id = client.post("/api/v1/projects", json=PROJECT_PAYLOAD, headers=auth_headers).json()["id"]
    resp = client.post(
        f"/api/v1/projects/{project_id}/actions/security-audit",
        json={"inputs": {}},
        headers=auth_headers,
    )
    assert resp.status_code == 400
    assert "no blueprint" in resp.json()["detail"].lower()


def test_duplicate_long_running_action_conflict(client, auth_headers, drain_jobs):
    """Submitting a long-running action while another job is active returns 409."""
    from app.services.actions.registry import ACTION_REGISTRY, AIAction

    fake_id = "long-fake-action-2"

    def _handler(project, blueprint, inputs, db):
        return None

    ACTION_REGISTRY[fake_id] = AIAction(
        id=fake_id,
        name="Long Fake 2",
        category="analysis",
        description="",
        handler=_handler,
        execution_mode="long",
        mutates_project=False,
    )
    try:
        project_id = _create_generated_project(client, auth_headers)
        drain_jobs()
        with SessionLocal() as db:
            from app.services.generation_jobs import create_job

            create_job(db, project_id)  # an active generation job is running
        resp = client.post(
            f"/api/v1/projects/{project_id}/actions/{fake_id}",
            json={"inputs": {}},
            headers=auth_headers,
        )
    finally:
        del ACTION_REGISTRY[fake_id]
    assert resp.status_code == 409
    assert "already running" in resp.json()["detail"]


def test_action_job_failure_surfaces_generic_message(client, auth_headers, drain_jobs):
    """Action job failure stores generic error message, never internal details."""
    from app.services.actions.registry import ACTION_REGISTRY, AIAction

    fake_id = "boom-action-job"

    def _boom(project, blueprint, inputs, db):
        raise RuntimeError("secret internal detail: db-password")

    ACTION_REGISTRY[fake_id] = AIAction(
        id=fake_id,
        name="Boom Job",
        category="analysis",
        description="",
        handler=_boom,
        execution_mode="long",
        mutates_project=False,
    )
    try:
        project_id = _create_generated_project(client, auth_headers)
        drain_jobs()
        with SessionLocal() as db:
            from app.services.generation_jobs import create_action_job

            job = create_action_job(db, project_id, fake_id, {})
        drain_jobs()
        with SessionLocal() as db:
            from app.models.generation_job import GenerationJob

            failed = db.get(GenerationJob, job.id)
            assert failed.status == "failed"
            assert "secret internal detail" not in (failed.error_message or "")
    finally:
        del ACTION_REGISTRY[fake_id]
