"""Phase 6 — Engineering Workspace: download center, API collections, asset ZIP."""

import io
import json
import zipfile

import pytest

from tests.test_projects import PROJECT_PAYLOAD


@pytest.fixture()
def generated_project(client, auth_headers, drain_jobs):
    project_id = client.post("/api/v1/projects", json=PROJECT_PAYLOAD, headers=auth_headers).json()["id"]
    resp = client.post(f"/api/v1/projects/{project_id}/generate", headers=auth_headers)
    assert resp.status_code == 202
    drain_jobs()
    return project_id, auth_headers


def test_openapi_collection(client, generated_project):
    project_id, headers = generated_project
    resp = client.get(f"/api/v1/projects/{project_id}/api-collection?format=openapi", headers=headers)
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/json")

    doc = resp.json()
    assert doc["openapi"] == "3.0.3"
    assert "Hospital Management System API" in doc["info"]["title"]
    assert doc["components"]["securitySchemes"]["bearerAuth"]["type"] == "http"
    assert doc["servers"][0]["url"] == "/api/v1"

    blueprint = client.get(f"/api/v1/projects/{project_id}", headers=headers).json()["blueprint"]
    expected = {e["path"]: e["method"].lower() for e in blueprint["api"]["endpoints"]}
    for path, method in expected.items():
        assert path in doc["paths"]
        assert method in doc["paths"][path]


def test_openapi_collection_auth_secured_endpoints(client, generated_project):
    project_id, headers = generated_project
    doc = client.get(f"/api/v1/projects/{project_id}/api-collection?format=openapi", headers=headers).json()
    auth_paths = [p for p, ops in doc["paths"].items() for m, op in ops.items() if "security" in op]
    assert auth_paths, "expected at least one secured endpoint"


def test_postman_collection(client, generated_project):
    project_id, headers = generated_project
    resp = client.get(f"/api/v1/projects/{project_id}/api-collection?format=postman", headers=headers)
    assert resp.status_code == 200

    collection = resp.json()
    assert collection["info"]["schema"].endswith("collection/v2.1.0/collection.json")
    assert collection["variable"][0]["key"] == "baseUrl"
    assert collection["item"]

    blueprint = client.get(f"/api/v1/projects/{project_id}", headers=headers).json()["blueprint"]
    assert len(collection["item"]) == len(blueprint["api"]["endpoints"])
    first = collection["item"][0]
    assert first["request"]["url"]["host"] == ["{{baseUrl}}"]
    assert first["request"]["header"]


def test_api_collection_unknown_format(client, generated_project):
    project_id, headers = generated_project
    resp = client.get(f"/api/v1/projects/{project_id}/api-collection?format=xml", headers=headers)
    assert resp.status_code == 400


def test_artifacts_catalog(client, generated_project):
    project_id, headers = generated_project
    resp = client.get(f"/api/v1/projects/{project_id}/workspace/artifacts", headers=headers)
    assert resp.status_code == 200
    catalog = resp.json()

    assert catalog["project_name"] == PROJECT_PAYLOAD["name"]
    assert catalog["zip_href"].endswith(f"/projects/{project_id}/workspace/export")

    groups = {g["id"]: g for g in catalog["groups"]}
    assert {
        "blueprint",
        "code",
        "diagrams",
        "sprint-board",
        "database",
        "api-collection",
        "starter-repo",
    } <= set(groups)

    blueprint_formats = {item["id"] for item in groups["blueprint"]["items"]}
    assert {"markdown", "pdf", "docx", "json"} <= blueprint_formats

    assert len(groups["code"]["items"]) == 8
    assert len(groups["diagrams"]["items"]) == 8

    collection_items = {item["id"] for item in groups["api-collection"]["items"]}
    assert collection_items == {"openapi", "postman"}

    board_formats = {item["id"] for item in groups["sprint-board"]["items"]}
    assert board_formats == {"json", "markdown", "csv"}

    db_generators = {item["id"] for item in groups["database"]["items"]}
    assert db_generators == {"sql", "prisma", "sqlalchemy"}

    for group in catalog["groups"]:
        for item in group["items"]:
            assert item["href"].startswith("/api/v1/projects/")


def test_workspace_zip_bundles_everything(client, generated_project):
    project_id, headers = generated_project
    resp = client.get(f"/api/v1/projects/{project_id}/workspace/export", headers=headers)
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/zip"

    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        names = zf.namelist()
        root = names[0].split("/")[0]
        with zf.open(f"{root}/api/openapi.json") as handle:
            doc = json.load(handle)
        with zf.open(f"{root}/blueprint.json") as handle:
            blueprint = json.load(handle)

    assert f"{root}/blueprint.md" in names
    assert f"{root}/blueprint.json" in names
    assert f"{root}/README.md" in names
    assert f"{root}/api/openapi.json" in names
    assert f"{root}/api/postman.json" in names
    assert f"{root}/project-management/project-management.md" in names
    assert f"{root}/database/schema.sql" in names

    for diagram_id in ["overview", "erd", "sequence", "class", "component", "deployment", "c4", "flowchart"]:
        assert f"{root}/diagrams/{diagram_id}.mmd" in names

    for generator_id in ["sql", "prisma", "sqlalchemy", "fastapi", "express", "nextjs", "react", "spring"]:
        assert f"{root}/code/{generator_id}.zip" in names

    assert doc["openapi"] == "3.0.3"
    assert doc["paths"]
    assert blueprint["project"]["name"] == PROJECT_PAYLOAD["name"]


def test_workspace_requires_blueprint(client, auth_headers):
    project_id = client.post("/api/v1/projects", json=PROJECT_PAYLOAD, headers=auth_headers).json()["id"]
    for path in (
        f"/api/v1/projects/{project_id}/workspace/artifacts",
        f"/api/v1/projects/{project_id}/workspace/export",
        f"/api/v1/projects/{project_id}/api-collection",
    ):
        resp = client.get(path, headers=auth_headers)
        assert resp.status_code == 400
