"""Phase 12 — blueprint revision history, compare and safe rollback.

Covers the deterministic diff engine (field add/remove/change, unordered
array semantics, edge cases), the revision APIs (list with summaries,
detail with snapshots, compare consecutive/non-consecutive/same/invalid
revisions, pagination, ownership), safe rollback (confirmation, stale
expected-current-revision 409, section-level restore as a NEW revision,
history preserved, secrets rejected / placeholders allowed, snapshot-less
422), legacy V1/V2 compatibility, and the real Hospital Management System
E2E workflow.
"""

from __future__ import annotations

import copy
import json

from app.database import SessionLocal
from app.services.blueprint_diff import diff_json, summarize_diff
from tests.test_blueprint_compat import legacy_blueprint
from tests.test_phase11_intelligence import (
    _create_generated_project,
    _history,
    _run_action,
    _second_user_headers,
)
from tests.test_projects import PROJECT_PAYLOAD

# ---------------------------------------------------------------------------
# Deterministic diff engine (Part 22 edge cases)
# ---------------------------------------------------------------------------


def test_diff_detects_added_removed_changed_fields():
    items = diff_json(
        {"name": "Old", "drop": {"x": 1}},
        {"name": "New", "added": [1, 2]},
    )
    by_path = {item.path: item for item in items}
    assert by_path[("name",)].op == "change"
    assert by_path[("name",)].before == "Old"
    assert by_path[("name",)].after == "New"
    assert by_path[("drop",)].op == "remove"
    assert by_path[("added",)].op == "add"
    assert by_path[("added",)].after == [1, 2]


def test_diff_null_to_value_and_value_to_null():
    items = diff_json({"a": None}, {"a": 5})
    assert len(items) == 1
    assert items[0].op == "change"
    assert items[0].before is None
    assert items[0].after == 5

    items = diff_json({"a": 5}, {"a": None})
    assert len(items) == 1
    assert items[0].op == "change"
    assert items[0].after is None


def test_diff_empty_containers():
    assert diff_json({}, {}) == []
    assert diff_json([], []) == []
    items = diff_json({"a": {}}, {"a": {"b": []}})
    assert len(items) == 1
    assert items[0].op == "add"
    assert items[0].path == ("a", "b")
    items = diff_json({}, {"a": {}})
    assert len(items) == 1 and items[0].op == "add"
    items = diff_json({"a": []}, {"a": [1]})
    assert len(items) == 1 and items[0].op == "add"
    assert items[0].after == 1


def test_diff_arrays_are_unordered_but_report_additions_and_removals():
    # Reordering is NOT a change (apply merges lists wholesale; the V3
    # contract does not preserve list order across actions).
    assert diff_json([1, 2, 3], [3, 2, 1]) == []
    items = diff_json([1, 2], [2, 3])
    removed = [i for i in items if i.op == "remove"]
    added = [i for i in items if i.op == "add"]
    assert [i.before for i in removed] == [1]
    assert [i.after for i in added] == [3]


def test_diff_modified_object_in_array_surfaces_as_remove_add():
    items = diff_json([{"id": 1, "x": "a"}], [{"id": 1, "x": "b"}])
    ops = sorted(item.op for item in items)
    assert ops == ["add", "remove"]


def test_diff_identical_values_empty_and_deterministic():
    before = {"a": [1, {"b": "x"}], "c": {"d": 3}}
    after = {"a": [{"b": "x"}, 1], "c": {"d": 3}}
    assert diff_json(before, after) == []
    first = diff_json({"a": {"x": 1}}, {"a": {"y": 2}})
    second = diff_json({"a": {"x": 1}}, {"a": {"y": 2}})
    assert [item.path for item in first] == [item.path for item in second]


def test_diff_does_not_mutate_inputs():
    before = {"nested": {"list": [1, 2]}}
    after = {"nested": {"list": [2, 3]}}
    diff_json(before, after)
    assert before == {"nested": {"list": [1, 2]}}
    assert after == {"nested": {"list": [2, 3]}}


def test_summary_lines_are_human_readable():
    items = diff_json(
        {"api": {"endpoints": [{"path": "/a"}, {"path": "/b"}]}},
        {"api": {"endpoints": [{"path": "/a"}, {"path": "/b"}, {"path": "/c"}, {"path": "/d"}]}},
    )
    lines = summarize_diff(items)
    assert lines == ["Added 2 API endpoints"]


def test_summary_falls_back_to_generic_wording():
    items = diff_json({"a": {"b": 1, "c": 2}}, {"a": {"b": 3, "c": 4}})
    lines = summarize_diff(items)
    assert lines == ["Changed 2 fields"]


def test_summary_empty_for_no_changes():
    assert summarize_diff([]) == []


# ---------------------------------------------------------------------------
# Revision list / detail API
# ---------------------------------------------------------------------------


def _revisions(client, headers, project_id, limit=20, offset=0):
    resp = client.get(
        f"/api/v1/projects/{project_id}/revisions?limit={limit}&offset={offset}",
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _apply_latest(client, headers, project_id, action_id):
    result_id = _history(client, headers, project_id)["items"][0]["id"]
    resp = client.post(
        f"/api/v1/projects/{project_id}/actions/history/{result_id}/apply",
        json={"confirm": True},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_revision_list_empty_for_legacy_project(client, auth_headers, drain_jobs):
    project_id = _create_generated_project(client, auth_headers)
    drain_jobs()
    body = _revisions(client, auth_headers, project_id)
    assert body["items"] == []
    assert body["total"] == 0


def test_revision_list_requires_auth(client, auth_headers, drain_jobs):
    project_id = _create_generated_project(client, auth_headers)
    drain_jobs()
    assert client.get(f"/api/v1/projects/{project_id}/revisions").status_code == 401


def test_revision_list_foreign_project_404(client, auth_headers, drain_jobs):
    project_id = _create_generated_project(client, auth_headers)
    drain_jobs()
    other = _second_user_headers(client)
    assert client.get(f"/api/v1/projects/{project_id}/revisions", headers=other).status_code == 404


def test_revision_list_after_applies(client, auth_headers, drain_jobs):
    project_id = _create_generated_project(client, auth_headers)
    drain_jobs()
    for action_id in ("generate-test-strategy", "generate-ci-cd"):
        _run_action(client, auth_headers, project_id, action_id)
        _apply_latest(client, auth_headers, project_id, action_id)

    body = _revisions(client, auth_headers, project_id)
    assert body["total"] == 2
    newest = body["items"][0]
    assert newest["revision"] == 2
    assert newest["source_action"] == "generate-ci-cd"
    assert newest["section"] == "deployment"
    assert newest["applied_by"] is not None
    assert newest["summary"]
    oldest = body["items"][1]
    assert oldest["revision"] == 1
    assert oldest["source_action"] == "generate-test-strategy"
    assert oldest["section"] == "testing"


def test_revision_list_pagination(client, auth_headers, drain_jobs):
    project_id = _create_generated_project(client, auth_headers)
    drain_jobs()
    for action_id in ("generate-test-strategy", "generate-ci-cd", "generate-risk-register"):
        _run_action(client, auth_headers, project_id, action_id)
        _apply_latest(client, auth_headers, project_id, action_id)

    page1 = _revisions(client, auth_headers, project_id, limit=2, offset=0)
    assert len(page1["items"]) == 2
    assert page1["total"] == 3
    page2 = _revisions(client, auth_headers, project_id, limit=2, offset=2)
    assert len(page2["items"]) == 1
    assert page2["items"][0]["revision"] == 1
    revs1 = {item["revision"] for item in page1["items"]}
    revs2 = {item["revision"] for item in page2["items"]}
    assert not revs1 & revs2


def test_revision_detail_snapshots_and_diff(client, auth_headers, drain_jobs):
    project_id = _create_generated_project(client, auth_headers)
    drain_jobs()
    blueprint = client.get(f"/api/v1/projects/{project_id}", headers=auth_headers).json()["blueprint"]
    previous_testing = copy.deepcopy(blueprint["testing"])

    _run_action(client, auth_headers, project_id, "generate-test-strategy")
    applied = _apply_latest(client, auth_headers, project_id, "generate-test-strategy")
    assert applied["revision"] == 1

    resp = client.get(f"/api/v1/projects/{project_id}/revisions/1", headers=auth_headers)
    assert resp.status_code == 200
    detail = resp.json()
    assert detail["revision"] == 1
    assert detail["source_action"] == "generate-test-strategy"
    assert detail["section"] == "testing"
    assert detail["action_result_id"] is not None
    assert detail["applied_by"] is not None
    assert detail["previous_section"] == previous_testing
    assert isinstance(detail["current_section"], dict)
    assert detail["changed"]
    assert detail["summary"][0] == "Changed testing section"
    # Only revision data is exposed — never unrelated project data.
    assert "blueprint" not in detail
    assert set(detail.keys()) <= {
        "revision", "created_at", "source_action", "section", "action_result_id",
        "applied_by", "previous_section", "current_section", "changed", "summary",
    }


def test_revision_detail_invalid_revision_404(client, auth_headers, drain_jobs):
    project_id = _create_generated_project(client, auth_headers)
    drain_jobs()
    assert client.get(f"/api/v1/projects/{project_id}/revisions/99", headers=auth_headers).status_code == 404


def test_revision_detail_foreign_project_404(client, auth_headers, drain_jobs):
    project_id = _create_generated_project(client, auth_headers)
    drain_jobs()
    _run_action(client, auth_headers, project_id, "generate-test-strategy")
    _apply_latest(client, auth_headers, project_id, "generate-test-strategy")
    other = _second_user_headers(client)
    assert client.get(f"/api/v1/projects/{project_id}/revisions/1", headers=other).status_code == 404


# ---------------------------------------------------------------------------
# Compare API
# ---------------------------------------------------------------------------


def _three_revisions(client, auth_headers, project_id):
    """Apply test-strategy (rev 1), ci-cd (rev 2), risk-register (rev 3)."""
    for action_id in (
        "generate-test-strategy",
        "generate-ci-cd",
        "generate-risk-register",
    ):
        _run_action(client, auth_headers, project_id, action_id)
        _apply_latest(client, auth_headers, project_id, action_id)


def test_compare_different_sections(client, auth_headers, drain_jobs):
    project_id = _create_generated_project(client, auth_headers)
    drain_jobs()
    _three_revisions(client, auth_headers, project_id)

    resp = client.get(
        f"/api/v1/projects/{project_id}/revisions/compare?from_revision=1&to_revision=2",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["from_revision"]["section"] == "testing"
    assert body["from_revision"]["revision"] == 1
    assert body["from_revision"]["changed"]
    assert body["to_revision"]["section"] == "deployment"
    assert body["to_revision"]["revision"] == 2
    assert body["to_revision"]["changed"]
    # Different sections: no combined diff, each side reports its own change.
    assert body["combined"] is None


def test_compare_same_section_consecutive_and_non_consecutive(client, auth_headers, drain_jobs):
    project_id = _create_generated_project(client, auth_headers)
    drain_jobs()

    # Two applies to the SAME section (testing): revisions 1 and 2.
    for _ in range(2):
        _run_action(client, auth_headers, project_id, "generate-test-strategy")
        _apply_latest(client, auth_headers, project_id, "generate-test-strategy")
    _run_action(client, auth_headers, project_id, "generate-ci-cd")
    _apply_latest(client, auth_headers, project_id, "generate-ci-cd")  # revision 3

    resp = client.get(
        f"/api/v1/projects/{project_id}/revisions/compare?from_revision=1&to_revision=2",
        headers=auth_headers,
    )
    body = resp.json()
    assert body["combined"] is not None
    assert body["combined"]["section"] == "testing"
    assert body["combined"]["revision"] == 2
    # combined.before = the state AT revision 1, combined.after = state AT revision 2.
    assert body["combined"]["before"] == body["from_revision"]["after"]
    assert body["combined"]["after"] == body["to_revision"]["after"]
    assert body["combined"]["before"] is not None
    assert body["combined"]["after"] is not None

    # Non-consecutive compare (1 → 3) works too.
    resp = client.get(
        f"/api/v1/projects/{project_id}/revisions/compare?from_revision=1&to_revision=3",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["combined"] is None  # different sections


def test_compare_same_revision_yields_empty_diff(client, auth_headers, drain_jobs):
    project_id = _create_generated_project(client, auth_headers)
    drain_jobs()
    _three_revisions(client, auth_headers, project_id)

    resp = client.get(
        f"/api/v1/projects/{project_id}/revisions/compare?from_revision=2&to_revision=2",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    # Each side still describes what revision 2 itself did (deployment changed).
    assert body["from_revision"]["section"] == "deployment"
    assert body["from_revision"]["changed"]
    # Comparing the revision to ITSELF is an empty net diff.
    assert body["combined"]["changed"] == []
    assert body["combined"]["summary"] == []


def test_compare_invalid_revision_404(client, auth_headers, drain_jobs):
    project_id = _create_generated_project(client, auth_headers)
    drain_jobs()
    _three_revisions(client, auth_headers, project_id)
    resp = client.get(
        f"/api/v1/projects/{project_id}/revisions/compare?from_revision=1&to_revision=99",
        headers=auth_headers,
    )
    assert resp.status_code == 404


def test_compare_foreign_project_404(client, auth_headers, drain_jobs):
    project_id = _create_generated_project(client, auth_headers)
    drain_jobs()
    _three_revisions(client, auth_headers, project_id)
    other = _second_user_headers(client)
    resp = client.get(
        f"/api/v1/projects/{project_id}/revisions/compare?from_revision=1&to_revision=2",
        headers=other,
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Safe rollback (restore)
# ---------------------------------------------------------------------------


def test_restore_requires_confirmation(client, auth_headers, drain_jobs):
    project_id = _create_generated_project(client, auth_headers)
    drain_jobs()
    _three_revisions(client, auth_headers, project_id)
    resp = client.post(
        f"/api/v1/projects/{project_id}/revisions/1/restore",
        json={"confirm": False},
        headers=auth_headers,
    )
    assert resp.status_code == 400


def test_restore_creates_new_revision_and_restores_section_only(
    client, auth_headers, drain_jobs
):
    project_id = _create_generated_project(client, auth_headers)
    drain_jobs()
    blueprint_before = client.get(f"/api/v1/projects/{project_id}", headers=auth_headers).json()["blueprint"]
    original_testing = copy.deepcopy(blueprint_before["testing"])

    _three_revisions(client, auth_headers, project_id)
    # The applies legitimately changed deployment and business_risks; capture
    # their state AFTER the applies so we can prove restore touches nothing.
    blueprint_applied = client.get(f"/api/v1/projects/{project_id}", headers=auth_headers).json()["blueprint"]
    applied_deployment = copy.deepcopy(blueprint_applied["deployment"])
    applied_risks = copy.deepcopy(blueprint_applied["business_risks"])
    assert applied_deployment != blueprint_before["deployment"]  # ci-cd applied

    resp = client.post(
        f"/api/v1/projects/{project_id}/revisions/1/restore",
        json={"confirm": True, "expected_current_revision": 3},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["revision"] == 4
    assert body["section"] == "testing"
    assert "restored from Revision 1" in body["message"]

    blueprint = client.get(f"/api/v1/projects/{project_id}", headers=auth_headers).json()["blueprint"]
    assert blueprint["testing"] == original_testing  # restored
    assert blueprint["deployment"] == applied_deployment  # untouched by restore
    assert blueprint["business_risks"] == applied_risks  # untouched by restore

    # History is preserved: restore is a NEW revision, never a rewrite.
    revisions = _revisions(client, auth_headers, project_id)
    assert revisions["total"] == 4
    newest = revisions["items"][0]
    assert newest["revision"] == 4
    assert newest["source_action"] == "restore-revision"
    assert newest["section"] == "testing"
    assert newest["applied_by"] is not None
    assert [item["revision"] for item in revisions["items"]] == [4, 3, 2, 1]


def test_restore_stale_expected_revision_409(client, auth_headers, drain_jobs):
    project_id = _create_generated_project(client, auth_headers)
    drain_jobs()
    _three_revisions(client, auth_headers, project_id)
    resp = client.post(
        f"/api/v1/projects/{project_id}/revisions/1/restore",
        json={"confirm": True, "expected_current_revision": 2},
        headers=auth_headers,
    )
    assert resp.status_code == 409
    assert "revision 3" in resp.json()["detail"]
    # Nothing changed.
    assert _revisions(client, auth_headers, project_id)["total"] == 3


def test_restore_unknown_revision_404(client, auth_headers, drain_jobs):
    project_id = _create_generated_project(client, auth_headers)
    drain_jobs()
    resp = client.post(
        f"/api/v1/projects/{project_id}/revisions/9/restore",
        json={"confirm": True},
        headers=auth_headers,
    )
    assert resp.status_code == 404


def test_restore_foreign_project_404(client, auth_headers, drain_jobs):
    project_id = _create_generated_project(client, auth_headers)
    drain_jobs()
    _three_revisions(client, auth_headers, project_id)
    other = _second_user_headers(client)
    resp = client.post(
        f"/api/v1/projects/{project_id}/revisions/1/restore",
        json={"confirm": True},
        headers=other,
    )
    assert resp.status_code == 404


def test_restore_snapshotless_revision_422(client, auth_headers, drain_jobs):
    project_id = _create_generated_project(client, auth_headers)
    drain_jobs()
    with SessionLocal() as db:
        from app.models.blueprint_revision import BlueprintRevision

        db.add(
            BlueprintRevision(
                project_id=project_id,
                revision=1,
                section="testing",
                source_action="generate-test-strategy",
                previous_section=None,
            )
        )
        db.commit()

    resp = client.post(
        f"/api/v1/projects/{project_id}/revisions/1/restore",
        json={"confirm": True},
        headers=auth_headers,
    )
    assert resp.status_code == 422
    assert "snapshot" in resp.json()["detail"].lower()


def test_restore_rejects_secret_like_snapshots(client, auth_headers, drain_jobs):
    project_id = _create_generated_project(client, auth_headers)
    drain_jobs()
    with SessionLocal() as db:
        from app.models.blueprint_revision import BlueprintRevision

        db.add(
            BlueprintRevision(
                project_id=project_id,
                revision=1,
                section="deployment",
                source_action="generate-ci-cd",
                previous_section=json.dumps({"env": {"API_KEY": "sk-proj-abcdefghijklmnop"}}),
            )
        )
        db.commit()

    resp = client.post(
        f"/api/v1/projects/{project_id}/revisions/1/restore",
        json={"confirm": True},
        headers=auth_headers,
    )
    assert resp.status_code == 422
    assert "secret" in resp.json()["detail"].lower()
    assert _revisions(client, auth_headers, project_id)["total"] == 1  # nothing new created


def test_restore_allows_secret_placeholders(client, auth_headers, drain_jobs):
    project_id = _create_generated_project(client, auth_headers)
    drain_jobs()
    placeholder_section = {
        "ci": {"deploy_token": "${{ secrets.DEPLOY_TOKEN }}", "api_key_env": "${API_KEY}"}
    }
    with SessionLocal() as db:
        from app.models.blueprint_revision import BlueprintRevision

        db.add(
            BlueprintRevision(
                project_id=project_id,
                revision=1,
                section="deployment",
                source_action="generate-ci-cd",
                previous_section=json.dumps(placeholder_section),
            )
        )
        db.commit()

    resp = client.post(
        f"/api/v1/projects/{project_id}/revisions/1/restore",
        json={"confirm": True},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    blueprint = client.get(f"/api/v1/projects/{project_id}", headers=auth_headers).json()["blueprint"]
    assert blueprint["deployment"] == placeholder_section


def test_restore_is_reversible_and_concurrent_safe(client, auth_headers, drain_jobs):
    project_id = _create_generated_project(client, auth_headers)
    drain_jobs()
    _three_revisions(client, auth_headers, project_id)

    for expected in (3, 4):
        resp = client.post(
            f"/api/v1/projects/{project_id}/revisions/1/restore",
            json={"confirm": True, "expected_current_revision": expected},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["revision"] == expected + 1

    # Two restores → two distinct revisions; the DB-unique index guarantees
    # concurrent restores can never claim the same number.
    assert _revisions(client, auth_headers, project_id)["total"] == 5


# ---------------------------------------------------------------------------
# Legacy V1/V2 blueprints keep working (Part 18)
# ---------------------------------------------------------------------------


def test_legacy_v1_blueprint_revision_api_graceful(client, auth_headers):
    project_id = client.post("/api/v1/projects", json=PROJECT_PAYLOAD, headers=auth_headers).json()["id"]
    legacy = legacy_blueprint(version="1.0")
    from app.models.project import Project

    with SessionLocal() as db:
        project = db.get(Project, project_id)
        project.blueprint = copy.deepcopy(legacy)
        db.commit()

    body = _revisions(client, auth_headers, project_id)
    assert body["total"] == 0
    assert body["items"] == []
    assert client.get(f"/api/v1/projects/{project_id}/revisions/1", headers=auth_headers).status_code == 404
    assert (
        client.get(f"/api/v1/projects/{project_id}/revisions/compare?from_revision=1&to_revision=1", headers=auth_headers).status_code
        == 404
    )


# ---------------------------------------------------------------------------
# E2E — Hospital Management System (Part 24)
# ---------------------------------------------------------------------------


def test_hospital_e2e_revisions_compare_restore(client, auth_headers, drain_jobs):
    project_id = client.post("/api/v1/projects", json=PROJECT_PAYLOAD, headers=auth_headers).json()["id"]
    assert client.post(f"/api/v1/projects/{project_id}/generate", headers=auth_headers).status_code == 202
    drain_jobs()
    blueprint = client.get(f"/api/v1/projects/{project_id}", headers=auth_headers).json()["blueprint"]
    original_testing = copy.deepcopy(blueprint["testing"])
    original_deployment = copy.deepcopy(blueprint["deployment"])

    # 1. Apply test strategy → revision 1 (testing)
    _run_action(client, auth_headers, project_id, "generate-test-strategy")
    assert _apply_latest(client, auth_headers, project_id, "generate-test-strategy")["revision"] == 1

    # 2. Apply CI/CD → revision 2 (deployment)
    _run_action(client, auth_headers, project_id, "generate-ci-cd")
    assert _apply_latest(client, auth_headers, project_id, "generate-ci-cd")["revision"] == 2

    # 3. Apply risk register → revision 3 (business_risks)
    _run_action(client, auth_headers, project_id, "generate-risk-register")
    assert _apply_latest(client, auth_headers, project_id, "generate-risk-register")["revision"] == 3

    applied_blueprint = client.get(f"/api/v1/projects/{project_id}", headers=auth_headers).json()["blueprint"]
    applied_deployment = copy.deepcopy(applied_blueprint["deployment"])
    applied_risks = copy.deepcopy(applied_blueprint["business_risks"])

    # 4. History has all three revisions, newest first
    revisions = _revisions(client, auth_headers, project_id)
    assert [item["revision"] for item in revisions["items"]] == [3, 2, 1]
    assert all(item["summary"] for item in revisions["items"])

    # 5. View revision 2 detail (deployment, created by generate-ci-cd)
    detail = client.get(f"/api/v1/projects/{project_id}/revisions/2", headers=auth_headers).json()
    assert detail["section"] == "deployment"
    assert detail["source_action"] == "generate-ci-cd"
    assert detail["previous_section"] == original_deployment
    assert detail["changed"]

    # 6. Compare revision 1 → 2 (different sections: each side shows its change)
    compare = client.get(
        f"/api/v1/projects/{project_id}/revisions/compare?from_revision=1&to_revision=2",
        headers=auth_headers,
    ).json()
    assert compare["from_revision"]["revision"] == 1
    assert compare["from_revision"]["section"] == "testing"
    assert compare["to_revision"]["revision"] == 2
    assert compare["to_revision"]["section"] == "deployment"
    assert compare["combined"] is None

    # 7. Restore revision 1 → new revision 4, only testing restored
    restored = client.post(
        f"/api/v1/projects/{project_id}/revisions/1/restore",
        json={"confirm": True, "expected_current_revision": 3},
        headers=auth_headers,
    ).json()
    assert restored["revision"] == 4
    assert restored["section"] == "testing"

    blueprint = client.get(f"/api/v1/projects/{project_id}", headers=auth_headers).json()["blueprint"]
    assert blueprint["testing"] == original_testing
    assert blueprint["deployment"] == applied_deployment
    assert blueprint["business_risks"] == applied_risks

    # 8. History is preserved: revisions 1-3 remain, restore is revision 4
    revisions = _revisions(client, auth_headers, project_id)
    assert [item["revision"] for item in revisions["items"]] == [4, 3, 2, 1]
    assert revisions["items"][0]["source_action"] == "restore-revision"

    # 9. Stale rollback → 409 (blueprint is at revision 4, not 3)
    stale = client.post(
        f"/api/v1/projects/{project_id}/revisions/2/restore",
        json={"confirm": True, "expected_current_revision": 3},
        headers=auth_headers,
    )
    assert stale.status_code == 409

    # 10. Restore without a confirm → 400
    assert (
        client.post(
            f"/api/v1/projects/{project_id}/revisions/2/restore",
            json={"confirm": False},
            headers=auth_headers,
        ).status_code
        == 400
    )

    # 11. A foreign user sees none of this.
    other = _second_user_headers(client)
    assert client.get(f"/api/v1/projects/{project_id}/revisions", headers=other).status_code == 404
    assert client.get(f"/api/v1/projects/{project_id}/revisions/4", headers=other).status_code == 404
    assert (
        client.post(
            f"/api/v1/projects/{project_id}/revisions/1/restore",
            json={"confirm": True},
            headers=other,
        ).status_code
        == 404
    )
