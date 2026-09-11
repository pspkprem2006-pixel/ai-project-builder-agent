"""Phase 1 regression tests — recipe-domain entities must be resolved into the
Domain Context and flow through to the generated blueprint.

RECIPE_DOMAINS deliberately define ``"entities": None`` because their entity
model is sourced from ``templates.TABLE_RECIPES``. The Domain Context builder
must resolve those recipes (via ``domain_data.domain_tables``) so blueprints
contain the domain's real entities instead of only the base auth tables.
"""

import pytest

from app.services.ai.domain_context import build_domain_context
from app.services.ai.domain_data import RECIPE_DOMAINS
from app.services.ai.reasoning import generate_blueprint

# Known domain-specific table names, sourced verbatim from
# templates.TABLE_RECIPES (the recipe entity model for each domain).
RECIPE_SIGNATURE_TABLES: dict[str, set[str]] = {
    "hospital": {"patients", "appointments", "medical_records", "billing"},
    "food": {"restaurants", "orders", "order_items", "couriers", "reviews"},
    "ecommerce": {"products", "categories", "orders", "payments"},
    "inventory": {"products", "warehouses", "stock_movements", "purchase_orders", "suppliers"},
    "erp": {"students", "faculty", "courses", "enrollments", "attendance", "fees"},
    "chat": {"conversations", "conversation_members", "messages", "message_reactions"},
    "ai": {"documents", "analyses", "prompts"},
    "saas": {"workspaces", "projects", "tasks"},
}

BASE_TABLES = {"users", "roles", "user_roles", "audit_logs"}

RECIPE_PAYLOADS: dict[str, dict] = {
    "hospital": {
        "name": "Hospital Management System",
        "description": "Complete hospital operations platform.",
        "category": "Healthcare",
        "target_users": "Hospital admins, doctors, reception staff, patients",
        "features": ["Patient registration", "Appointments", "Medical records", "Billing"],
        "preferred_frontend": "Next.js",
        "preferred_backend": "FastAPI",
        "database": "PostgreSQL",
        "auth_method": "JWT",
        "deployment_platform": "Docker",
        "language": "TypeScript",
    },
    "food": {
        "name": "Food Delivery App",
        "description": "Restaurant discovery and food delivery platform.",
        "category": "Food & Delivery",
        "target_users": "Customers, restaurant owners, couriers",
        "features": ["Restaurant menus", "Orders", "Courier delivery", "Reviews"],
        "preferred_frontend": "Next.js",
        "preferred_backend": "FastAPI",
        "database": "PostgreSQL",
        "auth_method": "JWT",
        "deployment_platform": "Docker",
        "language": "TypeScript",
    },
    "ecommerce": {
        "name": "Online Shop",
        "description": "Online store with catalog, cart and checkout.",
        "category": "E-Commerce",
        "target_users": "Shoppers, store managers",
        "features": ["Products", "Categories", "Cart", "Checkout", "Payments"],
        "preferred_frontend": "Next.js",
        "preferred_backend": "FastAPI",
        "database": "PostgreSQL",
        "auth_method": "JWT",
        "deployment_platform": "Docker",
        "language": "TypeScript",
    },
    "inventory": {
        "name": "Warehouse Stock Manager",
        "description": "Inventory and warehouse management with purchase orders.",
        "category": "Inventory",
        "target_users": "Warehouse staff, procurement",
        "features": ["SKUs", "Warehouses", "Stock movements", "Purchase orders", "Suppliers"],
        "preferred_frontend": "Next.js",
        "preferred_backend": "FastAPI",
        "database": "PostgreSQL",
        "auth_method": "JWT",
        "deployment_platform": "Docker",
        "language": "TypeScript",
    },
    "erp": {
        "name": "Campus ERP",
        "description": "University administration with enrollment and grades.",
        "category": "ERP",
        "target_users": "Students, faculty, administrators",
        "features": ["Students", "Enrollment", "Attendance", "Courses", "Fees"],
        "preferred_frontend": "Next.js",
        "preferred_backend": "FastAPI",
        "database": "PostgreSQL",
        "auth_method": "JWT",
        "deployment_platform": "Docker",
        "language": "TypeScript",
    },
    "chat": {
        "name": "Team Chat App",
        "description": "Real-time team messaging platform.",
        "category": "Chat",
        "target_users": "Team members, administrators",
        "features": ["Group chat", "Direct messages", "Read receipts"],
        "preferred_frontend": "Next.js",
        "preferred_backend": "FastAPI",
        "database": "PostgreSQL",
        "auth_method": "JWT",
        "deployment_platform": "Docker",
        "language": "TypeScript",
    },
    "ai": {
        "name": "Resume Analyzer",
        "description": "AI resume parsing and candidate insights.",
        "category": "AI",
        "target_users": "Recruiters, job seekers",
        "features": ["Resume parsing", "NLP", "Machine learning", "Analysis"],
        "preferred_frontend": "Next.js",
        "preferred_backend": "FastAPI",
        "database": "PostgreSQL",
        "auth_method": "JWT",
        "deployment_platform": "Docker",
        "language": "TypeScript",
    },
    "saas": {
        "name": "Task Tracker SaaS",
        "description": "Multi-tenant project management workspace.",
        "category": "SaaS",
        "target_users": "Teams, workspace admins",
        "features": ["Projects", "Tasks", "Workspaces", "Subscription billing"],
        "preferred_frontend": "Next.js",
        "preferred_backend": "FastAPI",
        "database": "PostgreSQL",
        "auth_method": "JWT",
        "deployment_platform": "Docker",
        "language": "TypeScript",
    },
}


def test_recipe_domains_have_signature_tables():
    """The test data itself must stay anchored to the recipe entity model."""
    assert set(RECIPE_PAYLOADS) == set(RECIPE_DOMAINS)
    for domain in RECIPE_DOMAINS:
        assert RECIPE_SIGNATURE_TABLES[domain], f"no signature tables for {domain}"


@pytest.mark.parametrize("domain", sorted(RECIPE_DOMAINS))
def test_recipe_domain_tables_present_in_domain_context(domain):
    payload = RECIPE_PAYLOADS[domain]
    ctx = build_domain_context(payload)
    assert ctx["primary_domain"] == domain
    names = {t["name"] for t in ctx["tables"]}
    missing = RECIPE_SIGNATURE_TABLES[domain] - names
    assert not missing, f"{domain} context missing recipe tables: {sorted(missing)}"
    # Domain context carries domain tables only; base auth tables are added
    # downstream by the database builder.
    assert not (names & BASE_TABLES), f"{domain} context leaked base tables: {sorted(names & BASE_TABLES)}"


@pytest.mark.parametrize("domain", sorted(RECIPE_DOMAINS))
def test_recipe_domain_tables_present_in_blueprint(domain):
    payload = RECIPE_PAYLOADS[domain]
    blueprint = generate_blueprint(payload)
    names = {t["name"] for t in blueprint["database"]["tables"]}
    missing = RECIPE_SIGNATURE_TABLES[domain] - names
    assert not missing, f"{domain} blueprint missing recipe tables: {sorted(missing)}"
    assert names >= BASE_TABLES, f"{domain} blueprint lost base auth tables: {sorted(BASE_TABLES - names)}"
    endpoints = {ep["path"] for ep in blueprint["api"]["endpoints"]}
    first = sorted(RECIPE_SIGNATURE_TABLES[domain])[0]
    slug = "/" + first.replace("_", "-")
    assert slug in endpoints, f"{domain} blueprint has no REST endpoint for '{first}'"
