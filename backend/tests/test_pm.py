import pytest

from tests.test_projects import PROJECT_PAYLOAD


@pytest.fixture()
def generated_project(client, auth_headers, drain_jobs):
    project_id = client.post("/api/v1/projects", json=PROJECT_PAYLOAD, headers=auth_headers).json()["id"]
    resp = client.post(f"/api/v1/projects/{project_id}/generate", headers=auth_headers)
    assert resp.status_code == 202
    drain_jobs()
    return project_id, auth_headers


def test_pm_requires_blueprint(client, auth_headers):
    project_id = client.post("/api/v1/projects", json=PROJECT_PAYLOAD, headers=auth_headers).json()["id"]
    resp = client.get(f"/api/v1/projects/{project_id}/pm", headers=auth_headers)
    assert resp.status_code == 400


def test_pm_model_shape(client, generated_project):
    project_id, headers = generated_project
    resp = client.get(f"/api/v1/projects/{project_id}/pm", headers=headers)
    assert resp.status_code == 200
    model = resp.json()

    assert model["project_name"]
    assert model["project_key"]
    assert model["epics"]
    assert model["sprint_backlog"]
    assert model["milestones"]
    assert model["dependencies"]
    assert model["critical_path"]["chain"]
    assert model["github_issues"]
    assert model["jira_tasks"]
    assert model["sprint_burndown"]
    assert model["summary"]["user_stories"] > 0
    assert model["blueprint_generated_at"]

    story = model["epics"][0]["user_stories"][0]
    assert story["id"].startswith("US-")
    assert story["title"]
    assert story["as_a"]
    assert story["i_want"]
    assert story["so_that"]
    assert len(story["acceptance_criteria"]) >= 3
    assert story["module"]
    assert story["source_sections"]
    assert story["epic_id"]
    assert story["points"] > 0
    assert story["hours"] > 0


def test_pm_tasks_reference_blueprint_modules(client, generated_project):
    project_id, headers = generated_project
    model = client.get(f"/api/v1/projects/{project_id}/pm", headers=headers).json()
    for epic in model["epics"]:
        assert epic["module"]
        assert epic["source_sections"]
        for story in epic["user_stories"]:
            assert story["module"]
            assert story["source_sections"], story["id"]
    for issue in model["github_issues"]:
        assert issue["labels"]
        assert "blueprint" in issue["body"].lower()


def test_pm_dependency_graph_is_acyclic(client, generated_project):
    project_id, headers = generated_project
    model = client.get(f"/api/v1/projects/{project_id}/pm", headers=headers).json()
    edges = {(edge["from"], edge["to"]) for edge in model["dependencies"]}
    nodes = {story["id"] for epic in model["epics"] for story in epic["user_stories"]}

    indegree = {node: 0 for node in nodes}
    adjacency = {node: [] for node in nodes}
    for source, target in edges:
        if source in nodes and target in nodes:
            adjacency[source].append(target)
            indegree[target] += 1
    queue = [node for node, degree in indegree.items() if degree == 0]
    visited = 0
    while queue:
        node = queue.pop(0)
        visited += 1
        for neighbor in adjacency[node]:
            indegree[neighbor] -= 1
            if indegree[neighbor] == 0:
                queue.append(neighbor)
    assert visited == len(nodes), "dependency graph contains a cycle"

    chain = model["critical_path"]["chain"]
    assert chain[0] in nodes
    assert set(chain) <= nodes


def test_pm_sprints_and_burndown(client, generated_project):
    project_id, headers = generated_project
    model = client.get(f"/api/v1/projects/{project_id}/pm", headers=headers).json()
    total_points = sum(sprint["total_points"] for sprint in model["sprint_backlog"])
    assert total_points == model["summary"]["total_points"]
    assert model["sprint_burndown"][-1]["ideal_remaining"] == 0
    assert model["sprint_burndown"][0]["points_remaining"] > 0


def test_pm_export_json(client, generated_project):
    project_id, headers = generated_project
    resp = client.get(f"/api/v1/projects/{project_id}/pm/export?format=json", headers=headers)
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/json")
    body = resp.json()
    assert body["epics"]
    assert "filename=" in resp.headers["content-disposition"]


def test_pm_export_markdown(client, generated_project):
    project_id, headers = generated_project
    resp = client.get(f"/api/v1/projects/{project_id}/pm/export?format=md", headers=headers)
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/markdown")
    text = resp.text
    assert text.startswith("# ")
    assert "## Epics & User Stories" in text
    assert "## Sprint Backlog" in text
    assert "## Critical Path" in text
    assert "## GitHub Issues" in text
    assert "## Jira Tasks" in text


def test_pm_export_csv(client, generated_project):
    project_id, headers = generated_project
    resp = client.get(f"/api/v1/projects/{project_id}/pm/export?format=csv", headers=headers)
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/csv")
    rows = resp.text.strip().splitlines()
    assert rows[0].startswith("id,title,type")
    assert any(row.startswith("US-") for row in rows[1:])


def test_pm_export_unknown_format(client, generated_project):
    project_id, headers = generated_project
    resp = client.get(f"/api/v1/projects/{project_id}/pm/export?format=xlsx", headers=headers)
    assert resp.status_code == 400
