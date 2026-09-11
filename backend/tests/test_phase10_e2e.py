"""E2E validation for Phase 10 actions across domains."""

import pytest

from tests.test_projects import PROJECT_PAYLOAD

FOOD_DELIVERY_PAYLOAD = {
    "name": "Food Delivery Platform",
    "description": "Connect restaurants with customers for food ordering and delivery.",
    "category": "Food",
    "target_users": "Customers, restaurant owners, delivery drivers",
    "features": ["Restaurant listing", "Menu browsing", "Order placement", "Delivery tracking", "Reviews"],
    "preferred_frontend": "Next.js",
    "preferred_backend": "FastAPI",
    "database": "PostgreSQL",
    "auth_method": "JWT",
    "deployment_platform": "Docker",
    "language": "TypeScript",
}

PHASE10_ACTIONS = [
    "security-audit",
    "generate-test-strategy",
    "generate-ci-cd",
    "generate-sprint-plan",
    "generate-risk-register",
    "generate-compliance-map",
]


def _create_generated_project(client, headers, payload):
    project_id = client.post("/api/v1/projects", json=payload, headers=headers).json()["id"]
    resp = client.post(f"/api/v1/projects/{project_id}/generate", headers=headers)
    assert resp.status_code == 202
    return project_id


def _drain_jobs(drain_jobs):
    drain_jobs()


@pytest.mark.parametrize("action_id", PHASE10_ACTIONS)
def test_hospital_phase10_actions(client, auth_headers, drain_jobs, action_id):
    """All Phase 10 actions work for Hospital Management System."""
    project_id = _create_generated_project(client, auth_headers, PROJECT_PAYLOAD)
    _drain_jobs(drain_jobs)

    resp = client.post(
        f"/api/v1/projects/{project_id}/actions/{action_id}",
        json={"inputs": {}},
        headers=auth_headers,
    )
    assert resp.status_code == 200, f"Action {action_id} failed: {resp.text}"
    body = resp.json()
    assert body["action_id"] == action_id
    assert body["status"] in ("success", "fallback")
    assert body["result"] is not None


@pytest.mark.parametrize("action_id", PHASE10_ACTIONS)
def test_food_delivery_phase10_actions(client, auth_headers, drain_jobs, action_id):
    """All Phase 10 actions work for Food Delivery Platform."""
    project_id = _create_generated_project(client, auth_headers, FOOD_DELIVERY_PAYLOAD)
    _drain_jobs(drain_jobs)

    resp = client.post(
        f"/api/v1/projects/{project_id}/actions/{action_id}",
        json={"inputs": {}},
        headers=auth_headers,
    )
    assert resp.status_code == 200, f"Action {action_id} failed: {resp.text}"
    body = resp.json()
    assert body["action_id"] == action_id
    assert body["status"] in ("success", "fallback")
    assert body["result"] is not None


def test_hospital_security_audit_domain_awareness(client, auth_headers, drain_jobs):
    """Hospital security audit uses healthcare terminology, not food terminology."""
    project_id = _create_generated_project(client, auth_headers, PROJECT_PAYLOAD)
    _drain_jobs(drain_jobs)

    resp = client.post(
        f"/api/v1/projects/{project_id}/actions/security-audit",
        json={"inputs": {}},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    result = resp.json()["result"]
    if resp.json()["status"] == "success":
        full_text = str(result).lower()
        # Should NOT have food-delivery terminology
        forbidden = ["restaurant", "courier", "dish", "chef", "kitchen", "takeaway", "meal", "recipe", "food delivery"]
        for term in forbidden:
            assert term not in full_text, f"Found food term '{term}' in hospital security audit"
        # Should have healthcare terminology
        healthcare_terms = ["patient", "medical", "healthcare", "hospital", "doctor", "appointment", "prescription"]
        found = any(term in full_text for term in healthcare_terms)
        assert found, "Hospital security audit should mention healthcare terms"


def test_food_delivery_security_audit_domain_awareness(client, auth_headers, drain_jobs):
    """Food delivery security audit uses food terminology, not healthcare terminology."""
    project_id = _create_generated_project(client, auth_headers, FOOD_DELIVERY_PAYLOAD)
    _drain_jobs(drain_jobs)

    resp = client.post(
        f"/api/v1/projects/{project_id}/actions/security-audit",
        json={"inputs": {}},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    result = resp.json()["result"]
    if resp.json()["status"] == "success":
        full_text = str(result).lower()
        # Should NOT have healthcare terminology
        forbidden = ["patient", "medical record", "prescription", "hospital", "doctor", "surgery", "pharmacy"]
        for term in forbidden:
            assert term not in full_text, f"Found healthcare term '{term}' in food delivery security audit"
        # Should have food terminology
        food_terms = ["restaurant", "courier", "dish", "kitchen", "delivery", "order", "menu", "cuisine"]
        found = any(term in full_text for term in food_terms)
        assert found, "Food delivery security audit should mention food terms"


def test_hospital_compliance_map_domain_awareness(client, auth_headers, drain_jobs):
    """Hospital compliance map mentions HIPAA/healthcare frameworks."""
    project_id = _create_generated_project(client, auth_headers, PROJECT_PAYLOAD)
    _drain_jobs(drain_jobs)

    resp = client.post(
        f"/api/v1/projects/{project_id}/actions/generate-compliance-map",
        json={"inputs": {}},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    result = resp.json()["result"]
    if resp.json()["status"] == "success":
        full_text = str(result).lower()
        healthcare_frameworks = ["hipaa", "gdpr", "phi", "patient", "medical", "healthcare"]
        found = any(f in full_text for f in healthcare_frameworks)
        assert found, "Hospital compliance map should mention healthcare frameworks"


def test_food_delivery_compliance_map_domain_awareness(client, auth_headers, drain_jobs):
    """Food delivery compliance map mentions food/PCI frameworks, not HIPAA."""
    project_id = _create_generated_project(client, auth_headers, FOOD_DELIVERY_PAYLOAD)
    _drain_jobs(drain_jobs)

    resp = client.post(
        f"/api/v1/projects/{project_id}/actions/generate-compliance-map",
        json={"inputs": {}},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    result = resp.json()["result"]
    if resp.json()["status"] == "success":
        full_text = str(result).lower()
        # Should NOT claim HIPAA is required (not healthcare)
        assert "hipaa" not in full_text or "not_applicable" in full_text
        # Should have food/payment relevant frameworks
        relevant = ["pci", "gdpr", "ccpa", "payment", "consumer", "food", "restaurant"]
        found = any(f in full_text for f in relevant)
        assert found, "Food delivery compliance map should mention relevant frameworks"


def test_hospital_risk_register_domain_awareness(client, auth_headers, drain_jobs):
    """Hospital risk register uses healthcare-specific risks."""
    project_id = _create_generated_project(client, auth_headers, PROJECT_PAYLOAD)
    _drain_jobs(drain_jobs)

    resp = client.post(
        f"/api/v1/projects/{project_id}/actions/generate-risk-register",
        json={"inputs": {}},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    result = resp.json()["result"]
    if resp.json()["status"] == "success":
        full_text = str(result).lower()
        # Should NOT have food-delivery terminology
        forbidden = ["restaurant", "courier", "dish", "chef", "kitchen", "takeaway", "food delivery"]
        for term in forbidden:
            assert term not in full_text, f"Found food term '{term}' in hospital risk register"
        # Should have healthcare terminology
        healthcare_terms = ["patient", "medical", "healthcare", "hospital", "hipaa", "phi", "clinical"]
        found = any(term in full_text for term in healthcare_terms)
        assert found, "Hospital risk register should mention healthcare terms"


def test_food_delivery_risk_register_domain_awareness(client, auth_headers, drain_jobs):
    """Food delivery risk register uses food-specific risks."""
    project_id = _create_generated_project(client, auth_headers, FOOD_DELIVERY_PAYLOAD)
    _drain_jobs(drain_jobs)

    resp = client.post(
        f"/api/v1/projects/{project_id}/actions/generate-risk-register",
        json={"inputs": {}},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    result = resp.json()["result"]
    if resp.json()["status"] == "success":
        full_text = str(result).lower()
        # Should NOT have healthcare terminology
        forbidden = ["patient", "medical record", "prescription", "hospital", "doctor", "surgery", "pharmacy", "hipaa"]
        for term in forbidden:
            assert term not in full_text, f"Found healthcare term '{term}' in food delivery risk register"
        # Should have food terminology
        food_terms = ["restaurant", "courier", "delivery", "order", "menu", "cuisine", "kitchen", "pci", "payment"]
        found = any(term in full_text for term in food_terms)
        assert found, "Food delivery risk register should mention food terms"
