import pytest

from tests.test_projects import PROJECT_PAYLOAD


@pytest.fixture()
def generated_project(client, auth_headers, drain_jobs):
    project_id = client.post("/api/v1/projects", json=PROJECT_PAYLOAD, headers=auth_headers).json()["id"]
    resp = client.post(f"/api/v1/projects/{project_id}/generate", headers=auth_headers)
    assert resp.status_code == 202
    drain_jobs()
    return project_id, auth_headers


def test_list_diagrams(client, generated_project):
    project_id, headers = generated_project
    resp = client.get(f"/api/v1/projects/{project_id}/diagrams", headers=headers)
    assert resp.status_code == 200
    ids = {diagram["id"] for diagram in resp.json()}
    assert {
        "overview",
        "erd",
        "sequence",
        "class",
        "component",
        "deployment",
        "c4",
        "flowchart",
    } <= ids


def test_diagrams_require_blueprint(client, auth_headers):
    project_id = client.post("/api/v1/projects", json=PROJECT_PAYLOAD, headers=auth_headers).json()["id"]
    resp = client.get(f"/api/v1/projects/{project_id}/diagrams/erd", headers=auth_headers)
    assert resp.status_code == 400


def test_unknown_diagram(client, generated_project):
    project_id, headers = generated_project
    resp = client.get(f"/api/v1/projects/{project_id}/diagrams/nope", headers=headers)
    assert resp.status_code == 404


@pytest.mark.parametrize(
    "diagram_id,keyword",
    [
        ("overview", "flowchart"),
        ("erd", "erDiagram"),
        ("sequence", "sequenceDiagram"),
        ("class", "classDiagram"),
        ("component", "flowchart"),
        ("deployment", "flowchart"),
        ("c4", "C4Context"),
        ("flowchart", "flowchart"),
    ],
)
def test_diagram_source(client, generated_project, diagram_id, keyword):
    project_id, headers = generated_project
    resp = client.get(f"/api/v1/projects/{project_id}/diagrams/{diagram_id}", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == diagram_id
    assert body["format"] == "mermaid"
    assert body["source"].startswith(keyword) or f"\n{keyword}" in body["source"]
    assert body["generated_at"]
    assert body["blueprint_generated_at"]


def test_diagram_export_mmd(client, generated_project):
    project_id, headers = generated_project
    resp = client.get(f"/api/v1/projects/{project_id}/diagrams/erd/export", headers=headers)
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/vnd.mermaid")
    assert resp.content.startswith(b"%%")
    assert "filename=" in resp.headers["content-disposition"]


def test_diagram_export_md(client, generated_project):
    project_id, headers = generated_project
    resp = client.get(f"/api/v1/projects/{project_id}/diagrams/erd/export?format=md", headers=headers)
    assert resp.status_code == 200
    assert resp.content.startswith(b"```mermaid")


def test_diagram_export_unknown_format(client, generated_project):
    project_id, headers = generated_project
    resp = client.get(f"/api/v1/projects/{project_id}/diagrams/erd/export?format=pdf", headers=headers)
    assert resp.status_code == 400
