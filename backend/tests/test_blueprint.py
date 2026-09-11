import json

from tests.test_projects import PROJECT_PAYLOAD


def test_generate_flow(client, auth_headers, drain_jobs):
    project_id = client.post("/api/v1/projects", json=PROJECT_PAYLOAD, headers=auth_headers).json()["id"]
    resp = client.post(f"/api/v1/projects/{project_id}/generate", headers=auth_headers)
    assert resp.status_code == 202
    drain_jobs()

    project = client.get(f"/api/v1/projects/{project_id}", headers=auth_headers).json()
    assert project["status"] == "complete"
    assert project["ai_provider"] == "template"

    blueprint = project["blueprint"]
    assert blueprint["metadata"]["version"] == "3.0"
    assert "analysis" in blueprint
    assert "domain_understanding" in blueprint
    assert "business_processes" in blueprint
    assert "technology_selection" in blueprint
    assert "technology_evaluation" in blueprint
    assert "design_decisions" in blueprint
    assert "tradeoffs" in blueprint
    assert "architecture" in blueprint
    assert "database" in blueprint
    assert "api" in blueprint
    assert "ui_ux" in blueprint
    assert "security" in blueprint
    assert "performance" in blueprint
    assert "scalability" in blueprint
    assert "cost_estimation" in blueprint
    assert "business_risks" in blueprint
    assert "roadmap" in blueprint
    assert "product_evolution" in blueprint
    assert "adr" in blueprint
    assert "testing" in blueprint
    assert "documentation" in blueprint
    assert "deployment" in blueprint
    assert "validation" in blueprint

    assert blueprint["analysis"]["problem_statement"]
    assert blueprint["analysis"]["objectives"]
    assert blueprint["analysis"]["complexity_score"]["score"] > 0
    assert blueprint["analysis"]["complexity_score"]["estimated_team"]["total"] > 0
    assert blueprint["domain_understanding"]["identified_domain"]
    assert blueprint["domain_understanding"]["domain_reasoning"]
    assert blueprint["business_processes"]["workflows"]
    assert blueprint["business_processes"]["business_rules"]
    assert blueprint["technology_selection"]["selected_stack"]
    assert blueprint["technology_selection"]["decision_matrix"]
    assert blueprint["technology_evaluation"]["categories"]
    assert blueprint["design_decisions"]["decisions"]
    assert blueprint["tradeoffs"]["tradeoffs"]
    assert blueprint["architecture"]["high_level_architecture"].startswith("graph")
    assert blueprint["database"]["erd_diagram"].startswith("erDiagram")
    assert blueprint["database"]["sql_scripts"]["create_tables"]
    assert len(blueprint["api"]["endpoints"]) >= 3
    assert blueprint["api"]["business_workflow_mapping"]
    assert blueprint["ui_ux"]["user_journeys"]
    assert blueprint["security"]["security_score"] >= 0
    assert blueprint["performance"]["performance_score"] >= 0
    assert blueprint["scalability"]["scenarios"]
    assert blueprint["cost_estimation"]["summary_table"]["monthly_total"] > 0
    assert blueprint["business_risks"]["risks"]
    assert blueprint["roadmap"]["weekly_milestones"]
    assert blueprint["product_evolution"]["versions"]
    assert blueprint["adr"]["records"]
    assert blueprint["deployment"]["dockerfile"]
    assert blueprint["documentation"]["readme"]
    assert blueprint["validation"]["quality_report"]["overall_quality"] >= 0
    assert blueprint["metadata"]["provider"] == "template"


def test_export_markdown(client, auth_headers, drain_jobs):
    project_id = client.post("/api/v1/projects", json=PROJECT_PAYLOAD, headers=auth_headers).json()["id"]
    client.post(f"/api/v1/projects/{project_id}/generate", headers=auth_headers)
    drain_jobs()
    resp = client.get(f"/api/v1/projects/{project_id}/export?format=markdown", headers=auth_headers)
    assert resp.status_code == 200
    assert "text/markdown" in resp.headers["content-type"]
    content = resp.content.decode("utf-8")
    assert "# Hospital Management System" in content
    assert "## 1. Requirements Analysis" in content
    assert "## 4. Technology Evaluation" in content
    assert "## 5. Design Decisions" in content
    assert "## 6. Trade-off Analysis" in content
    assert "## 7. Security Review" in content
    assert "## 8. Performance Review" in content
    assert "## 9. Scalability Planning" in content
    assert "## 10. Cost Estimation" in content
    assert "## 11. Business Risk Analysis" in content
    assert "## 12. Product Evolution Roadmap" in content
    assert "## 13. Architecture Decision Records" in content
    assert "```mermaid" in content


def test_export_json(client, auth_headers, drain_jobs):
    project_id = client.post("/api/v1/projects", json=PROJECT_PAYLOAD, headers=auth_headers).json()["id"]
    client.post(f"/api/v1/projects/{project_id}/generate", headers=auth_headers)
    drain_jobs()
    resp = client.get(f"/api/v1/projects/{project_id}/export?format=json", headers=auth_headers)
    assert resp.status_code == 200
    assert json.loads(resp.content)["project"]["name"] == "Hospital Management System"


def test_export_zip(client, auth_headers, drain_jobs):
    project_id = client.post("/api/v1/projects", json=PROJECT_PAYLOAD, headers=auth_headers).json()["id"]
    client.post(f"/api/v1/projects/{project_id}/generate", headers=auth_headers)
    drain_jobs()
    resp = client.get(f"/api/v1/projects/{project_id}/export?format=zip", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.content[:2] == b"PK"


def test_export_docx_and_pdf(client, auth_headers, drain_jobs):
    project_id = client.post("/api/v1/projects", json=PROJECT_PAYLOAD, headers=auth_headers).json()["id"]
    client.post(f"/api/v1/projects/{project_id}/generate", headers=auth_headers)
    drain_jobs()
    docx = client.get(f"/api/v1/projects/{project_id}/export?format=docx", headers=auth_headers)
    assert docx.status_code == 200
    assert docx.content[:2] == b"PK"
    pdf = client.get(f"/api/v1/projects/{project_id}/export?format=pdf", headers=auth_headers)
    assert pdf.status_code == 200
    assert pdf.content[:4] == b"%PDF"


def test_export_before_generation_fails(client, auth_headers):
    project_id = client.post("/api/v1/projects", json=PROJECT_PAYLOAD, headers=auth_headers).json()["id"]
    resp = client.get(f"/api/v1/projects/{project_id}/export?format=markdown", headers=auth_headers)
    assert resp.status_code == 400


def test_export_bad_format(client, auth_headers, drain_jobs):
    project_id = client.post("/api/v1/projects", json=PROJECT_PAYLOAD, headers=auth_headers).json()["id"]
    client.post(f"/api/v1/projects/{project_id}/generate", headers=auth_headers)
    drain_jobs()
    resp = client.get(f"/api/v1/projects/{project_id}/export?format=exe", headers=auth_headers)
    assert resp.status_code == 400


def test_template_engine_variety(client, auth_headers, drain_jobs):
    cases = [
        ("Food Delivery App", "Node.js", "MongoDB", "food", "Order food from local restaurants with delivery tracking.", ["Restaurant menus", "Order placement", "Courier tracking", "Reviews"]),
        ("College ERP", "Django", "PostgreSQL", "erp", "Enroll students, track attendance and manage fees.", ["Admissions", "Attendance", "Grading", "Fee payments"]),
        ("Chat App", "Spring Boot", "MongoDB", "chat", "Real-time direct and group messaging with reactions.", ["Conversations", "Messages", "Reactions", "Read receipts"]),
    ]
    for name, backend, database, expected_domain, description, features in cases:
        payload = {
            **PROJECT_PAYLOAD,
            "name": name,
            "description": description,
            "category": "General",
            "preferred_backend": backend,
            "database": database,
            "features": features,
        }
        pid = client.post("/api/v1/projects", json=payload, headers=auth_headers).json()["id"]
        client.post(f"/api/v1/projects/{pid}/generate", headers=auth_headers)
        drain_jobs()
        project = client.get(f"/api/v1/projects/{pid}", headers=auth_headers).json()
        assert project["status"] == "complete"
        assert project["blueprint"]["deployment"]["dockerfile"]
        assert project["blueprint"]["domain_understanding"]["identified_domain"] == expected_domain
        assert project["blueprint"]["validation"]["passed"] is True
