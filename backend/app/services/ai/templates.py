"""Template-based blueprint generator.

Produces a complete, professional software blueprint deterministically from the
wizard inputs. Used when no LLM API key is configured, as a fallback when the
LLM fails, and as the deterministic baseline for tests.
"""
from __future__ import annotations

import re
from typing import Any

# ---------------------------------------------------------------------------
# Stack knowledge bases
# ---------------------------------------------------------------------------

FRONTENDS: dict[str, dict[str, Any]] = {
    "Next.js": {
        "type": "React meta-framework (SSR/SSG/ISR)",
        "state": "React Context + TanStack Query",
        "styling": "Tailwind CSS + shadcn/ui",
        "routing": "App Router (file-based)",
        "why": "Best for SEO-sensitive apps with server components and first-class deployment support.",
    },
    "React": {
        "type": "SPA (Vite or CRA)",
        "state": "Redux Toolkit / Zustand",
        "styling": "Tailwind CSS + shadcn/ui",
        "routing": "React Router v6",
        "why": "Mature ecosystem, huge component library availability, ideal for complex dashboards.",
    },
    "Angular": {
        "type": "SPA (opinionated framework)",
        "state": "NgRx / RxJS services",
        "styling": "SCSS + Angular Material",
        "routing": "Angular Router",
        "why": "Enterprise-grade dependency injection, strong typing and testability out of the box.",
    },
    "Vue": {
        "type": "SPA (progressive framework)",
        "state": "Pinia",
        "styling": "Tailwind CSS + Element Plus",
        "routing": "Vue Router",
        "why": "Gentle learning curve with excellent documentation and reactivity model.",
    },
}

BACKENDS: dict[str, dict[str, Any]] = {
    "FastAPI": {
        "type": "Python async web framework",
        "orm": "SQLAlchemy 2.0 + Alembic",
        "validation": "Pydantic v2",
        "api_docs": "Auto-generated OpenAPI/Swagger at /docs",
        "why": "High performance, automatic API documentation, clean type-driven validation.",
    },
    "Django": {
        "type": "Python batteries-included framework",
        "orm": "Django ORM",
        "validation": "Django Forms + DRF serializers",
        "api_docs": "DRF + drf-spectacular",
        "why": "Admin panel, ORM and auth included; fastest path to a production CRUD backend.",
    },
    "Node.js": {
        "type": "JavaScript runtime (Express/NestJS)",
        "orm": "Prisma / TypeORM",
        "validation": "Joi / Zod",
        "api_docs": "OpenAPI via swagger-ui-express",
        "why": "Shared language with the frontend, excellent for real-time and I/O-heavy services.",
    },
    "Spring Boot": {
        "type": "Java enterprise framework",
        "orm": "Spring Data JPA + Flyway",
        "validation": "Bean Validation (Jakarta)",
        "api_docs": "Springdoc OpenAPI",
        "why": "Battle-tested for large enterprise systems with first-class security (Spring Security).",
    },
}

DATABASES: dict[str, dict[str, Any]] = {
    "PostgreSQL": {
        "type": "Relational (SQL)",
        "features": "JSONB, full-text search, row-level security, strong ACID",
        "migration": "Alembic (Python) / Flyway (JVM) / Knex (Node)",
        "why": "Most feature-rich open-source RDBMS; the default choice for transactional systems.",
    },
    "MySQL": {
        "type": "Relational (SQL)",
        "features": "Simple replication, huge ecosystem, InnoDB",
        "migration": "Alembic (Python) / Flyway (JVM) / Knex (Node)",
        "why": "Widely hosted, mature, cost-effective for read-heavy workloads.",
    },
    "MongoDB": {
        "type": "Document (NoSQL)",
        "features": "Flexible schema, horizontal scaling via sharding",
        "migration": "MongoDB migrations / Mongoose scripts",
        "why": "Best when the data model is flexible, document-shaped and scale-out is expected.",
    },
}

AUTH_METHODS: dict[str, dict[str, Any]] = {
    "JWT": {
        "type": "Stateless JSON Web Tokens",
        "flow": "Client sends credentials -> server verifies -> issues access + refresh tokens",
        "why": "Stateless, scalable across services, ideal for SPA + API architectures.",
    },
    "OAuth": {
        "type": "OAuth 2.0 / OpenID Connect",
        "flow": "Third-party IdP (Google/GitHub/Auth0) issues tokens after user consent",
        "why": "Zero password storage, strong security, best for consumer-facing products.",
    },
    "Firebase": {
        "type": "Firebase Authentication (hosted)",
        "flow": "Client SDK authenticates against Firebase, server verifies ID tokens",
        "why": "Fastest to integrate with email/password, social and phone auth built in.",
    },
}

DEPLOYMENTS: dict[str, dict[str, Any]] = {
    "Docker": {
        "type": "Containerized, self-hosted / any cloud",
        "why": "Portable, reproducible environments; the base layer for every other platform.",
    },
    "Railway": {
        "type": "PaaS with git-based deploys",
        "why": "Zero-config deploys, generous free tier, automatic HTTPS and previews.",
    },
    "Render": {
        "type": "PaaS with managed Postgres",
        "why": "Simple blueprints, managed databases, auto deploys on push.",
    },
    "AWS": {
        "type": "EC2/EKS + RDS + S3",
        "why": "Full control and the widest service catalog for production scale.",
    },
    "Azure": {
        "type": "Azure App Service / AKS",
        "why": "Enterprise integration, strong identity tooling (Entra ID), hybrid cloud.",
    },
}

LANGUAGES: dict[str, dict[str, Any]] = {
    "TypeScript": {"why": "Type safety across frontend and backend; preferred for team projects."},
    "Python": {"why": "Rapid development and the strongest AI/data ecosystem."},
    "JavaScript": {"why": "Universal language, fastest onboarding for web developers."},
    "Java": {"why": "Enterprise performance, strong typing and tooling."},
}

# ---------------------------------------------------------------------------
# Domain table recipes (category keyword -> database design)
# ---------------------------------------------------------------------------

TABLE_RECIPES: dict[str, list[dict[str, Any]]] = {
    "hospital": [
        {
            "name": "patients",
            "purpose": "Demographic and contact details of registered patients.",
            "columns": [
                {"name": "id", "type": "SERIAL PRIMARY KEY", "constraints": ["PK"], "description": "Unique patient identifier"},
                {"name": "full_name", "type": "VARCHAR(150) NOT NULL", "constraints": [], "description": "Patient full name"},
                {"name": "date_of_birth", "type": "DATE", "constraints": [], "description": "Date of birth"},
                {"name": "gender", "type": "VARCHAR(10)", "constraints": [], "description": "Patient gender"},
                {"name": "phone", "type": "VARCHAR(20)", "constraints": ["UNIQUE"], "description": "Contact phone"},
                {"name": "email", "type": "VARCHAR(150)", "constraints": ["UNIQUE"], "description": "Contact email"},
                {"name": "blood_group", "type": "VARCHAR(5)", "constraints": [], "description": "Blood group"},
                {"name": "address", "type": "TEXT", "constraints": [], "description": "Physical address"},
                {"name": "created_at", "type": "TIMESTAMPTZ DEFAULT now()", "constraints": [], "description": "Record creation time"},
            ],
            "indexes": [{"name": "idx_patients_email", "columns": ["email"], "unique": True}, {"name": "idx_patients_phone", "columns": ["phone"], "unique": True}],
            "relationships": [{"type": "one-to-many", "to_table": "appointments", "on": "patients.id = appointments.patient_id"}, {"type": "one-to-many", "to_table": "medical_records", "on": "patients.id = medical_records.patient_id"}],
        },
        {
            "name": "doctors",
            "purpose": "Doctor profiles and specialization data.",
            "columns": [
                {"name": "id", "type": "SERIAL PRIMARY KEY", "constraints": ["PK"], "description": "Unique doctor identifier"},
                {"name": "full_name", "type": "VARCHAR(150) NOT NULL", "constraints": [], "description": "Doctor full name"},
                {"name": "specialization", "type": "VARCHAR(100)", "constraints": [], "description": "Medical specialization"},
                {"name": "license_number", "type": "VARCHAR(50)", "constraints": ["UNIQUE"], "description": "Medical license"},
                {"name": "department_id", "type": "INTEGER REFERENCES departments(id)", "constraints": ["FK"], "description": "Owning department"},
                {"name": "phone", "type": "VARCHAR(20)", "constraints": [], "description": "Contact phone"},
                {"name": "available", "type": "BOOLEAN DEFAULT true", "constraints": [], "description": "Currently accepting patients"},
            ],
            "indexes": [{"name": "idx_doctors_dept", "columns": ["department_id"], "unique": False}],
            "relationships": [{"type": "one-to-many", "to_table": "appointments", "on": "doctors.id = appointments.doctor_id"}],
        },
        {
            "name": "departments",
            "purpose": "Hospital departments.",
            "columns": [
                {"name": "id", "type": "SERIAL PRIMARY KEY", "constraints": ["PK"], "description": "Unique department identifier"},
                {"name": "name", "type": "VARCHAR(120) NOT NULL UNIQUE", "constraints": ["UNIQUE"], "description": "Department name"},
                {"name": "floor", "type": "VARCHAR(20)", "constraints": [], "description": "Physical location"},
                {"name": "description", "type": "TEXT", "constraints": [], "description": "Department description"},
            ],
            "indexes": [],
            "relationships": [{"type": "one-to-many", "to_table": "doctors", "on": "departments.id = doctors.department_id"}],
        },
        {
            "name": "appointments",
            "purpose": "Scheduled doctor appointments.",
            "columns": [
                {"name": "id", "type": "SERIAL PRIMARY KEY", "constraints": ["PK"], "description": "Unique appointment identifier"},
                {"name": "patient_id", "type": "INTEGER NOT NULL REFERENCES patients(id)", "constraints": ["FK"], "description": "Booking patient"},
                {"name": "doctor_id", "type": "INTEGER NOT NULL REFERENCES doctors(id)", "constraints": ["FK"], "description": "Assigned doctor"},
                {"name": "scheduled_at", "type": "TIMESTAMPTZ NOT NULL", "constraints": [], "description": "Appointment time"},
                {"name": "status", "type": "VARCHAR(20) DEFAULT 'scheduled'", "constraints": ["CHECK (status IN ('scheduled','completed','cancelled','no-show'))"], "description": "Appointment state"},
                {"name": "reason", "type": "TEXT", "constraints": [], "description": "Reason for visit"},
                {"name": "created_at", "type": "TIMESTAMPTZ DEFAULT now()", "constraints": [], "description": "Booking time"},
            ],
            "indexes": [{"name": "idx_appointments_patient", "columns": ["patient_id"], "unique": False}, {"name": "idx_appointments_doctor_slot", "columns": ["doctor_id", "scheduled_at"], "unique": True}],
            "relationships": [{"type": "many-to-one", "to_table": "patients", "on": "appointments.patient_id = patients.id"}, {"type": "many-to-one", "to_table": "doctors", "on": "appointments.doctor_id = doctors.id"}],
        },
        {
            "name": "medical_records",
            "purpose": "Clinical records and visit history.",
            "columns": [
                {"name": "id", "type": "SERIAL PRIMARY KEY", "constraints": ["PK"], "description": "Unique record identifier"},
                {"name": "patient_id", "type": "INTEGER NOT NULL REFERENCES patients(id)", "constraints": ["FK"], "description": "Owning patient"},
                {"name": "doctor_id", "type": "INTEGER REFERENCES doctors(id)", "constraints": ["FK"], "description": "Attending doctor"},
                {"name": "diagnosis", "type": "TEXT", "constraints": [], "description": "Clinical diagnosis"},
                {"name": "prescription", "type": "TEXT", "constraints": [], "description": "Prescribed treatment"},
                {"name": "notes", "type": "TEXT", "constraints": [], "description": "Clinical notes"},
                {"name": "recorded_at", "type": "TIMESTAMPTZ DEFAULT now()", "constraints": [], "description": "Record time"},
            ],
            "indexes": [{"name": "idx_records_patient", "columns": ["patient_id"], "unique": False}],
            "relationships": [{"type": "many-to-one", "to_table": "patients", "on": "medical_records.patient_id = patients.id"}],
        },
        {
            "name": "billing",
            "purpose": "Patient invoices and payments.",
            "columns": [
                {"name": "id", "type": "SERIAL PRIMARY KEY", "constraints": ["PK"], "description": "Unique invoice identifier"},
                {"name": "patient_id", "type": "INTEGER NOT NULL REFERENCES patients(id)", "constraints": ["FK"], "description": "Billed patient"},
                {"name": "amount", "type": "NUMERIC(10,2) NOT NULL", "constraints": ["CHECK (amount >= 0)"], "description": "Invoice amount"},
                {"name": "status", "type": "VARCHAR(20) DEFAULT 'pending'", "constraints": ["CHECK (status IN ('pending','paid','cancelled'))"], "description": "Payment state"},
                {"name": "paid_at", "type": "TIMESTAMPTZ", "constraints": [], "description": "Payment timestamp"},
                {"name": "created_at", "type": "TIMESTAMPTZ DEFAULT now()", "constraints": [], "description": "Invoice creation time"},
            ],
            "indexes": [{"name": "idx_billing_patient", "columns": ["patient_id"], "unique": False}],
            "relationships": [{"type": "many-to-one", "to_table": "patients", "on": "billing.patient_id = patients.id"}],
        },
    ],
    "food": [
        {
            "name": "restaurants",
            "purpose": "Registered restaurants and metadata.",
            "columns": [
                {"name": "id", "type": "SERIAL PRIMARY KEY", "constraints": ["PK"], "description": "Unique restaurant identifier"},
                {"name": "name", "type": "VARCHAR(150) NOT NULL", "constraints": [], "description": "Restaurant name"},
                {"name": "owner_id", "type": "INTEGER REFERENCES users(id)", "constraints": ["FK"], "description": "Restaurant owner"},
                {"name": "cuisine", "type": "VARCHAR(80)", "constraints": [], "description": "Cuisine type"},
                {"name": "address", "type": "TEXT", "constraints": [], "description": "Physical address"},
                {"name": "latitude", "type": "DOUBLE PRECISION", "constraints": [], "description": "Geo latitude"},
                {"name": "longitude", "type": "DOUBLE PRECISION", "constraints": [], "description": "Geo longitude"},
                {"name": "is_active", "type": "BOOLEAN DEFAULT true", "constraints": [], "description": "Currently accepting orders"},
                {"name": "delivery_fee", "type": "NUMERIC(6,2) DEFAULT 0", "constraints": [], "description": "Flat delivery fee"},
            ],
            "indexes": [{"name": "idx_restaurants_geo", "columns": ["latitude", "longitude"], "unique": False}],
            "relationships": [{"type": "one-to-many", "to_table": "menu_items", "on": "restaurants.id = menu_items.restaurant_id"}, {"type": "one-to-many", "to_table": "orders", "on": "restaurants.id = orders.restaurant_id"}],
        },
        {
            "name": "menu_items",
            "purpose": "Dishes offered by restaurants.",
            "columns": [
                {"name": "id", "type": "SERIAL PRIMARY KEY", "constraints": ["PK"], "description": "Unique menu item identifier"},
                {"name": "restaurant_id", "type": "INTEGER NOT NULL REFERENCES restaurants(id)", "constraints": ["FK"], "description": "Owning restaurant"},
                {"name": "name", "type": "VARCHAR(150) NOT NULL", "constraints": [], "description": "Dish name"},
                {"name": "description", "type": "TEXT", "constraints": [], "description": "Dish description"},
                {"name": "price", "type": "NUMERIC(8,2) NOT NULL", "constraints": ["CHECK (price >= 0)"], "description": "Dish price"},
                {"name": "is_available", "type": "BOOLEAN DEFAULT true", "constraints": [], "description": "Currently orderable"},
                {"name": "category", "type": "VARCHAR(50)", "constraints": [], "description": "Menu category"},
            ],
            "indexes": [{"name": "idx_menu_restaurant", "columns": ["restaurant_id"], "unique": False}],
            "relationships": [{"type": "many-to-one", "to_table": "restaurants", "on": "menu_items.restaurant_id = restaurants.id"}],
        },
        {
            "name": "orders",
            "purpose": "Customer orders.",
            "columns": [
                {"name": "id", "type": "SERIAL PRIMARY KEY", "constraints": ["PK"], "description": "Unique order identifier"},
                {"name": "customer_id", "type": "INTEGER NOT NULL REFERENCES users(id)", "constraints": ["FK"], "description": "Ordering customer"},
                {"name": "restaurant_id", "type": "INTEGER NOT NULL REFERENCES restaurants(id)", "constraints": ["FK"], "description": "Fulfilling restaurant"},
                {"name": "status", "type": "VARCHAR(20) DEFAULT 'pending'", "constraints": ["CHECK (status IN ('pending','confirmed','preparing','out_for_delivery','delivered','cancelled'))"], "description": "Order state"},
                {"name": "total", "type": "NUMERIC(10,2) NOT NULL", "constraints": ["CHECK (total >= 0)"], "description": "Order total"},
                {"name": "delivery_address", "type": "TEXT NOT NULL", "constraints": [], "description": "Delivery destination"},
                {"name": "created_at", "type": "TIMESTAMPTZ DEFAULT now()", "constraints": [], "description": "Order placement time"},
                {"name": "delivered_at", "type": "TIMESTAMPTZ", "constraints": [], "description": "Delivery completion time"},
            ],
            "indexes": [{"name": "idx_orders_customer", "columns": ["customer_id"], "unique": False}, {"name": "idx_orders_restaurant_status", "columns": ["restaurant_id", "status"], "unique": False}],
            "relationships": [{"type": "one-to-many", "to_table": "order_items", "on": "orders.id = order_items.order_id"}],
        },
        {
            "name": "order_items",
            "purpose": "Line items within an order.",
            "columns": [
                {"name": "id", "type": "SERIAL PRIMARY KEY", "constraints": ["PK"], "description": "Unique line item identifier"},
                {"name": "order_id", "type": "INTEGER NOT NULL REFERENCES orders(id)", "constraints": ["FK"], "description": "Owning order"},
                {"name": "menu_item_id", "type": "INTEGER NOT NULL REFERENCES menu_items(id)", "constraints": ["FK"], "description": "Ordered dish"},
                {"name": "quantity", "type": "INTEGER NOT NULL", "constraints": ["CHECK (quantity > 0)"], "description": "Quantity ordered"},
                {"name": "unit_price", "type": "NUMERIC(8,2) NOT NULL", "constraints": [], "description": "Snapshot price at order time"},
            ],
            "indexes": [{"name": "idx_order_items_order", "columns": ["order_id"], "unique": False}],
            "relationships": [{"type": "many-to-one", "to_table": "orders", "on": "order_items.order_id = orders.id"}],
        },
        {
            "name": "couriers",
            "purpose": "Delivery riders and live status.",
            "columns": [
                {"name": "id", "type": "SERIAL PRIMARY KEY", "constraints": ["PK"], "description": "Unique courier identifier"},
                {"name": "user_id", "type": "INTEGER NOT NULL REFERENCES users(id)", "constraints": ["FK"], "description": "Linked user account"},
                {"name": "vehicle", "type": "VARCHAR(50)", "constraints": [], "description": "Vehicle type"},
                {"name": "is_available", "type": "BOOLEAN DEFAULT true", "constraints": [], "description": "Accepting deliveries"},
                {"name": "current_latitude", "type": "DOUBLE PRECISION", "constraints": [], "description": "Live latitude"},
                {"name": "current_longitude", "type": "DOUBLE PRECISION", "constraints": [], "description": "Live longitude"},
                {"name": "rating", "type": "NUMERIC(3,2) DEFAULT 5.0", "constraints": ["CHECK (rating BETWEEN 1 AND 5)"], "description": "Average rating"},
            ],
            "indexes": [],
            "relationships": [],
        },
        {
            "name": "reviews",
            "purpose": "Order feedback and ratings.",
            "columns": [
                {"name": "id", "type": "SERIAL PRIMARY KEY", "constraints": ["PK"], "description": "Unique review identifier"},
                {"name": "order_id", "type": "INTEGER UNIQUE REFERENCES orders(id)", "constraints": ["FK", "UNIQUE"], "description": "Reviewed order"},
                {"name": "rating", "type": "SMALLINT NOT NULL", "constraints": ["CHECK (rating BETWEEN 1 AND 5)"], "description": "Star rating"},
                {"name": "comment", "type": "TEXT", "constraints": [], "description": "Review text"},
                {"name": "created_at", "type": "TIMESTAMPTZ DEFAULT now()", "constraints": [], "description": "Review time"},
            ],
            "indexes": [],
            "relationships": [{"type": "one-to-one", "to_table": "orders", "on": "reviews.order_id = orders.id"}],
        },
    ],
    "ecommerce": [
        {
            "name": "products",
            "purpose": "Catalog products and inventory metadata.",
            "columns": [
                {"name": "id", "type": "SERIAL PRIMARY KEY", "constraints": ["PK"], "description": "Unique product identifier"},
                {"name": "name", "type": "VARCHAR(200) NOT NULL", "constraints": [], "description": "Product name"},
                {"name": "slug", "type": "VARCHAR(220) NOT NULL UNIQUE", "constraints": ["UNIQUE"], "description": "URL-friendly identifier"},
                {"name": "description", "type": "TEXT", "constraints": [], "description": "Product description"},
                {"name": "price", "type": "NUMERIC(10,2) NOT NULL", "constraints": ["CHECK (price >= 0)"], "description": "List price"},
                {"name": "category_id", "type": "INTEGER REFERENCES categories(id)", "constraints": ["FK"], "description": "Owning category"},
                {"name": "stock", "type": "INTEGER DEFAULT 0", "constraints": ["CHECK (stock >= 0)"], "description": "Available quantity"},
                {"name": "is_active", "type": "BOOLEAN DEFAULT true", "constraints": [], "description": "Visible in catalog"},
                {"name": "image_url", "type": "TEXT", "constraints": [], "description": "Primary image"},
                {"name": "created_at", "type": "TIMESTAMPTZ DEFAULT now()", "constraints": [], "description": "Creation time"},
            ],
            "indexes": [{"name": "idx_products_slug", "columns": ["slug"], "unique": True}, {"name": "idx_products_category", "columns": ["category_id"], "unique": False}],
            "relationships": [{"type": "one-to-many", "to_table": "order_items", "on": "products.id = order_items.product_id"}],
        },
        {
            "name": "categories",
            "purpose": "Product taxonomy.",
            "columns": [
                {"name": "id", "type": "SERIAL PRIMARY KEY", "constraints": ["PK"], "description": "Unique category identifier"},
                {"name": "name", "type": "VARCHAR(120) NOT NULL UNIQUE", "constraints": ["UNIQUE"], "description": "Category name"},
                {"name": "parent_id", "type": "INTEGER REFERENCES categories(id)", "constraints": ["FK"], "description": "Parent category (self-referencing)"},
            ],
            "indexes": [],
            "relationships": [{"type": "one-to-many", "to_table": "products", "on": "categories.id = products.category_id"}],
        },
        {
            "name": "orders",
            "purpose": "Customer purchases.",
            "columns": [
                {"name": "id", "type": "SERIAL PRIMARY KEY", "constraints": ["PK"], "description": "Unique order identifier"},
                {"name": "customer_id", "type": "INTEGER NOT NULL REFERENCES users(id)", "constraints": ["FK"], "description": "Purchasing customer"},
                {"name": "status", "type": "VARCHAR(20) DEFAULT 'pending'", "constraints": ["CHECK (status IN ('pending','paid','shipped','delivered','cancelled','refunded'))"], "description": "Order state"},
                {"name": "total", "type": "NUMERIC(12,2) NOT NULL", "constraints": ["CHECK (total >= 0)"], "description": "Order total"},
                {"name": "shipping_address", "type": "TEXT NOT NULL", "constraints": [], "description": "Delivery address"},
                {"name": "created_at", "type": "TIMESTAMPTZ DEFAULT now()", "constraints": [], "description": "Order placement time"},
            ],
            "indexes": [{"name": "idx_orders_customer", "columns": ["customer_id"], "unique": False}],
            "relationships": [{"type": "one-to-many", "to_table": "order_items", "on": "orders.id = order_items.order_id"}],
        },
        {
            "name": "order_items",
            "purpose": "Line items within an order.",
            "columns": [
                {"name": "id", "type": "SERIAL PRIMARY KEY", "constraints": ["PK"], "description": "Unique line item identifier"},
                {"name": "order_id", "type": "INTEGER NOT NULL REFERENCES orders(id)", "constraints": ["FK"], "description": "Owning order"},
                {"name": "product_id", "type": "INTEGER NOT NULL REFERENCES products(id)", "constraints": ["FK"], "description": "Purchased product"},
                {"name": "quantity", "type": "INTEGER NOT NULL", "constraints": ["CHECK (quantity > 0)"], "description": "Quantity"},
                {"name": "unit_price", "type": "NUMERIC(10,2) NOT NULL", "constraints": [], "description": "Price snapshot"},
            ],
            "indexes": [{"name": "idx_order_items_order", "columns": ["order_id"], "unique": False}],
            "relationships": [{"type": "many-to-one", "to_table": "orders", "on": "order_items.order_id = orders.id"}],
        },
        {
            "name": "inventory_movements",
            "purpose": "Stock change audit trail.",
            "columns": [
                {"name": "id", "type": "SERIAL PRIMARY KEY", "constraints": ["PK"], "description": "Unique movement identifier"},
                {"name": "product_id", "type": "INTEGER NOT NULL REFERENCES products(id)", "constraints": ["FK"], "description": "Affected product"},
                {"name": "delta", "type": "INTEGER NOT NULL", "constraints": [], "description": "Positive or negative change"},
                {"name": "reason", "type": "VARCHAR(50)", "constraints": [], "description": "Purchase, restock, adjustment"},
                {"name": "created_at", "type": "TIMESTAMPTZ DEFAULT now()", "constraints": [], "description": "Movement time"},
            ],
            "indexes": [{"name": "idx_inventory_product", "columns": ["product_id"], "unique": False}],
            "relationships": [{"type": "many-to-one", "to_table": "products", "on": "inventory_movements.product_id = products.id"}],
        },
        {
            "name": "payments",
            "purpose": "Payment transactions and gateway reference.",
            "columns": [
                {"name": "id", "type": "SERIAL PRIMARY KEY", "constraints": ["PK"], "description": "Unique payment identifier"},
                {"name": "order_id", "type": "INTEGER UNIQUE REFERENCES orders(id)", "constraints": ["FK"], "description": "Paid order"},
                {"name": "amount", "type": "NUMERIC(12,2) NOT NULL", "constraints": [], "description": "Charged amount"},
                {"name": "method", "type": "VARCHAR(30)", "constraints": [], "description": "Card, wallet, UPI, bank"},
                {"name": "gateway_ref", "type": "VARCHAR(100)", "constraints": ["UNIQUE"], "description": "Gateway transaction id"},
                {"name": "status", "type": "VARCHAR(20) DEFAULT 'pending'", "constraints": ["CHECK (status IN ('pending','succeeded','failed','refunded'))"], "description": "Payment state"},
                {"name": "paid_at", "type": "TIMESTAMPTZ", "constraints": [], "description": "Completion time"},
            ],
            "indexes": [{"name": "idx_payments_gateway", "columns": ["gateway_ref"], "unique": True}],
            "relationships": [{"type": "one-to-one", "to_table": "orders", "on": "payments.order_id = orders.id"}],
        },
    ],
    "inventory": [
        {
            "name": "products",
            "purpose": "Stock keeping units.",
            "columns": [
                {"name": "id", "type": "SERIAL PRIMARY KEY", "constraints": ["PK"], "description": "Unique product identifier"},
                {"name": "sku", "type": "VARCHAR(50) NOT NULL UNIQUE", "constraints": ["UNIQUE"], "description": "Stock keeping unit code"},
                {"name": "name", "type": "VARCHAR(200) NOT NULL", "constraints": [], "description": "Product name"},
                {"name": "unit", "type": "VARCHAR(20) DEFAULT 'pcs'", "constraints": [], "description": "Units, kg, pcs"},
                {"name": "category_id", "type": "INTEGER REFERENCES categories(id)", "constraints": ["FK"], "description": "Owning category"},
            ],
            "indexes": [{"name": "idx_products_sku", "columns": ["sku"], "unique": True}],
            "relationships": [{"type": "one-to-many", "to_table": "stock_movements", "on": "products.id = stock_movements.product_id"}],
        },
        {
            "name": "categories",
            "purpose": "Product grouping.",
            "columns": [
                {"name": "id", "type": "SERIAL PRIMARY KEY", "constraints": ["PK"], "description": "Unique category identifier"},
                {"name": "name", "type": "VARCHAR(120) NOT NULL UNIQUE", "constraints": ["UNIQUE"], "description": "Category name"},
            ],
            "indexes": [],
            "relationships": [],
        },
        {
            "name": "suppliers",
            "purpose": "Vendor information.",
            "columns": [
                {"name": "id", "type": "SERIAL PRIMARY KEY", "constraints": ["PK"], "description": "Unique supplier identifier"},
                {"name": "name", "type": "VARCHAR(150) NOT NULL", "constraints": [], "description": "Supplier name"},
                {"name": "contact_person", "type": "VARCHAR(120)", "constraints": [], "description": "Primary contact"},
                {"name": "phone", "type": "VARCHAR(20)", "constraints": [], "description": "Contact phone"},
                {"name": "email", "type": "VARCHAR(150)", "constraints": [], "description": "Contact email"},
                {"name": "lead_time_days", "type": "INTEGER DEFAULT 1", "constraints": ["CHECK (lead_time_days >= 0)"], "description": "Replenishment lead time"},
            ],
            "indexes": [],
            "relationships": [{"type": "one-to-many", "to_table": "purchase_orders", "on": "suppliers.id = purchase_orders.supplier_id"}],
        },
        {
            "name": "warehouses",
            "purpose": "Storage locations.",
            "columns": [
                {"name": "id", "type": "SERIAL PRIMARY KEY", "constraints": ["PK"], "description": "Unique warehouse identifier"},
                {"name": "name", "type": "VARCHAR(150) NOT NULL", "constraints": [], "description": "Warehouse name"},
                {"name": "location", "type": "TEXT", "constraints": [], "description": "Address"},
            ],
            "indexes": [],
            "relationships": [{"type": "one-to-many", "to_table": "stock_movements", "on": "warehouses.id = stock_movements.warehouse_id"}],
        },
        {
            "name": "stock_movements",
            "purpose": "Immutable stock ledger.",
            "columns": [
                {"name": "id", "type": "SERIAL PRIMARY KEY", "constraints": ["PK"], "description": "Unique movement identifier"},
                {"name": "product_id", "type": "INTEGER NOT NULL REFERENCES products(id)", "constraints": ["FK"], "description": "Affected product"},
                {"name": "warehouse_id", "type": "INTEGER REFERENCES warehouses(id)", "constraints": ["FK"], "description": "Affected warehouse"},
                {"name": "quantity", "type": "INTEGER NOT NULL", "constraints": ["CHECK (quantity <> 0)"], "description": "Signed quantity change"},
                {"name": "movement_type", "type": "VARCHAR(30) NOT NULL", "constraints": ["CHECK (movement_type IN ('inbound','outbound','adjustment','transfer_in','transfer_out'))"], "description": "Movement kind"},
                {"name": "reference_id", "type": "INTEGER", "constraints": [], "description": "Purchase order / sale reference"},
                {"name": "created_at", "type": "TIMESTAMPTZ DEFAULT now()", "constraints": [], "description": "Movement time"},
            ],
            "indexes": [{"name": "idx_stock_product", "columns": ["product_id"], "unique": False}, {"name": "idx_stock_warehouse", "columns": ["warehouse_id"], "unique": False}],
            "relationships": [],
        },
        {
            "name": "purchase_orders",
            "purpose": "Replenishment orders to suppliers.",
            "columns": [
                {"name": "id", "type": "SERIAL PRIMARY KEY", "constraints": ["PK"], "description": "Unique purchase order identifier"},
                {"name": "supplier_id", "type": "INTEGER NOT NULL REFERENCES suppliers(id)", "constraints": ["FK"], "description": "Vendor"},
                {"name": "status", "type": "VARCHAR(20) DEFAULT 'created'", "constraints": ["CHECK (status IN ('created','ordered','received','cancelled'))"], "description": "PO state"},
                {"name": "expected_at", "type": "DATE", "constraints": [], "description": "Expected delivery"},
                {"name": "received_at", "type": "TIMESTAMPTZ", "constraints": [], "description": "Actual receipt"},
                {"name": "created_at", "type": "TIMESTAMPTZ DEFAULT now()", "constraints": [], "description": "Creation time"},
            ],
            "indexes": [{"name": "idx_po_supplier", "columns": ["supplier_id"], "unique": False}],
            "relationships": [],
        },
    ],
    "erp": [
        {
            "name": "students",
            "purpose": "Enrolled student records.",
            "columns": [
                {"name": "id", "type": "SERIAL PRIMARY KEY", "constraints": ["PK"], "description": "Unique student identifier"},
                {"name": "user_id", "type": "INTEGER UNIQUE REFERENCES users(id)", "constraints": ["FK"], "description": "Linked account"},
                {"name": "roll_number", "type": "VARCHAR(30) NOT NULL UNIQUE", "constraints": ["UNIQUE"], "description": "Institutional roll number"},
                {"name": "department_id", "type": "INTEGER REFERENCES departments(id)", "constraints": ["FK"], "description": "Owning department"},
                {"name": "batch_year", "type": "INTEGER", "constraints": [], "description": "Admission year"},
                {"name": "enrollment_status", "type": "VARCHAR(20) DEFAULT 'active'", "constraints": ["CHECK (enrollment_status IN ('active','suspended','graduated','withdrawn'))"], "description": "Enrollment state"},
            ],
            "indexes": [{"name": "idx_students_roll", "columns": ["roll_number"], "unique": True}, {"name": "idx_students_dept", "columns": ["department_id"], "unique": False}],
            "relationships": [{"type": "one-to-many", "to_table": "enrollments", "on": "students.id = enrollments.student_id"}, {"type": "one-to-many", "to_table": "fees", "on": "students.id = fees.student_id"}],
        },
        {
            "name": "departments",
            "purpose": "Academic departments.",
            "columns": [
                {"name": "id", "type": "SERIAL PRIMARY KEY", "constraints": ["PK"], "description": "Unique department identifier"},
                {"name": "name", "type": "VARCHAR(150) NOT NULL UNIQUE", "constraints": ["UNIQUE"], "description": "Department name"},
                {"name": "head_id", "type": "INTEGER REFERENCES faculty(id)", "constraints": ["FK"], "description": "Department head"},
            ],
            "indexes": [],
            "relationships": [],
        },
        {
            "name": "faculty",
            "purpose": "Teaching staff profiles.",
            "columns": [
                {"name": "id", "type": "SERIAL PRIMARY KEY", "constraints": ["PK"], "description": "Unique faculty identifier"},
                {"name": "user_id", "type": "INTEGER UNIQUE REFERENCES users(id)", "constraints": ["FK"], "description": "Linked account"},
                {"name": "department_id", "type": "INTEGER REFERENCES departments(id)", "constraints": ["FK"], "description": "Owning department"},
                {"name": "designation", "type": "VARCHAR(80)", "constraints": [], "description": "Professor / Lecturer"},
                {"name": "specialization", "type": "VARCHAR(120)", "constraints": [], "description": "Research area"},
            ],
            "indexes": [],
            "relationships": [{"type": "one-to-many", "to_table": "courses", "on": "faculty.id = courses.instructor_id"}],
        },
        {
            "name": "courses",
            "purpose": "Course catalog.",
            "columns": [
                {"name": "id", "type": "SERIAL PRIMARY KEY", "constraints": ["PK"], "description": "Unique course identifier"},
                {"name": "code", "type": "VARCHAR(20) NOT NULL UNIQUE", "constraints": ["UNIQUE"], "description": "Course code"},
                {"name": "name", "type": "VARCHAR(200) NOT NULL", "constraints": [], "description": "Course name"},
                {"name": "credits", "type": "INTEGER", "constraints": ["CHECK (credits > 0)"], "description": "Credit hours"},
                {"name": "instructor_id", "type": "INTEGER REFERENCES faculty(id)", "constraints": ["FK"], "description": "Primary instructor"},
                {"name": "department_id", "type": "INTEGER REFERENCES departments(id)", "constraints": ["FK"], "description": "Owning department"},
            ],
            "indexes": [{"name": "idx_courses_code", "columns": ["code"], "unique": True}],
            "relationships": [{"type": "one-to-many", "to_table": "enrollments", "on": "courses.id = enrollments.course_id"}],
        },
        {
            "name": "enrollments",
            "purpose": "Student-course registrations.",
            "columns": [
                {"name": "id", "type": "SERIAL PRIMARY KEY", "constraints": ["PK"], "description": "Unique enrollment identifier"},
                {"name": "student_id", "type": "INTEGER NOT NULL REFERENCES students(id)", "constraints": ["FK"], "description": "Enrolled student"},
                {"name": "course_id", "type": "INTEGER NOT NULL REFERENCES courses(id)", "constraints": ["FK"], "description": "Registered course"},
                {"name": "semester", "type": "VARCHAR(20) NOT NULL", "constraints": [], "description": "Semester term"},
                {"name": "grade", "type": "VARCHAR(5)", "constraints": [], "description": "Final grade"},
                {"name": "enrolled_at", "type": "TIMESTAMPTZ DEFAULT now()", "constraints": [], "description": "Registration time"},
            ],
            "indexes": [{"name": "uq_enrollment", "columns": ["student_id", "course_id", "semester"], "unique": True}],
            "relationships": [],
        },
        {
            "name": "attendance",
            "purpose": "Daily attendance records.",
            "columns": [
                {"name": "id", "type": "SERIAL PRIMARY KEY", "constraints": ["PK"], "description": "Unique attendance identifier"},
                {"name": "enrollment_id", "type": "INTEGER NOT NULL REFERENCES enrollments(id)", "constraints": ["FK"], "description": "Related enrollment"},
                {"name": "date", "type": "DATE NOT NULL", "constraints": [], "description": "Attendance date"},
                {"name": "status", "type": "VARCHAR(15) NOT NULL", "constraints": ["CHECK (status IN ('present','absent','late','excused'))"], "description": "Attendance state"},
            ],
            "indexes": [{"name": "uq_attendance", "columns": ["enrollment_id", "date"], "unique": True}],
            "relationships": [],
        },
        {
            "name": "fees",
            "purpose": "Tuition and payment ledger.",
            "columns": [
                {"name": "id", "type": "SERIAL PRIMARY KEY", "constraints": ["PK"], "description": "Unique fee record identifier"},
                {"name": "student_id", "type": "INTEGER NOT NULL REFERENCES students(id)", "constraints": ["FK"], "description": "Billed student"},
                {"name": "amount", "type": "NUMERIC(10,2) NOT NULL", "constraints": ["CHECK (amount >= 0)"], "description": "Due amount"},
                {"name": "semester", "type": "VARCHAR(20)", "constraints": [], "description": "Billing term"},
                {"name": "status", "type": "VARCHAR(20) DEFAULT 'pending'", "constraints": ["CHECK (status IN ('pending','partial','paid','waived'))"], "description": "Payment state"},
                {"name": "due_date", "type": "DATE", "constraints": [], "description": "Deadline"},
            ],
            "indexes": [{"name": "idx_fees_student", "columns": ["student_id"], "unique": False}],
            "relationships": [],
        },
    ],
    "chat": [
        {
            "name": "conversations",
            "purpose": "Chat threads between members.",
            "columns": [
                {"name": "id", "type": "SERIAL PRIMARY KEY", "constraints": ["PK"], "description": "Unique conversation identifier"},
                {"name": "type", "type": "VARCHAR(15) DEFAULT 'direct'", "constraints": ["CHECK (type IN ('direct','group'))"], "description": "Conversation kind"},
                {"name": "name", "type": "VARCHAR(120)", "constraints": [], "description": "Group name (nullable for direct)"},
                {"name": "created_by", "type": "INTEGER REFERENCES users(id)", "constraints": ["FK"], "description": "Creator"},
                {"name": "created_at", "type": "TIMESTAMPTZ DEFAULT now()", "constraints": [], "description": "Creation time"},
            ],
            "indexes": [],
            "relationships": [{"type": "one-to-many", "to_table": "messages", "on": "conversations.id = messages.conversation_id"}],
        },
        {
            "name": "conversation_members",
            "purpose": "Membership of conversations.",
            "columns": [
                {"name": "id", "type": "SERIAL PRIMARY KEY", "constraints": ["PK"], "description": "Unique membership identifier"},
                {"name": "conversation_id", "type": "INTEGER NOT NULL REFERENCES conversations(id)", "constraints": ["FK"], "description": "Joined conversation"},
                {"name": "user_id", "type": "INTEGER NOT NULL REFERENCES users(id)", "constraints": ["FK"], "description": "Member"},
                {"name": "role", "type": "VARCHAR(15) DEFAULT 'member'", "constraints": ["CHECK (role IN ('admin','member'))"], "description": "Membership role"},
                {"name": "joined_at", "type": "TIMESTAMPTZ DEFAULT now()", "constraints": [], "description": "Join time"},
                {"name": "last_read_message_id", "type": "INTEGER REFERENCES messages(id)", "constraints": ["FK"], "description": "Read cursor"},
            ],
            "indexes": [{"name": "uq_membership", "columns": ["conversation_id", "user_id"], "unique": True}],
            "relationships": [],
        },
        {
            "name": "messages",
            "purpose": "Chat message content.",
            "columns": [
                {"name": "id", "type": "SERIAL PRIMARY KEY", "constraints": ["PK"], "description": "Unique message identifier"},
                {"name": "conversation_id", "type": "INTEGER NOT NULL REFERENCES conversations(id)", "constraints": ["FK"], "description": "Owning conversation"},
                {"name": "sender_id", "type": "INTEGER NOT NULL REFERENCES users(id)", "constraints": ["FK"], "description": "Message author"},
                {"name": "body", "type": "TEXT NOT NULL", "constraints": [], "description": "Message content"},
                {"name": "message_type", "type": "VARCHAR(20) DEFAULT 'text'", "constraints": ["CHECK (message_type IN ('text','image','file','system'))"], "description": "Payload kind"},
                {"name": "attachment_url", "type": "TEXT", "constraints": [], "description": "Optional attachment"},
                {"name": "created_at", "type": "TIMESTAMPTZ DEFAULT now()", "constraints": [], "description": "Send time"},
            ],
            "indexes": [{"name": "idx_messages_conversation_created", "columns": ["conversation_id", "created_at"], "unique": False}],
            "relationships": [],
        },
        {
            "name": "message_reactions",
            "purpose": "Reactions on messages.",
            "columns": [
                {"name": "id", "type": "SERIAL PRIMARY KEY", "constraints": ["PK"], "description": "Unique reaction identifier"},
                {"name": "message_id", "type": "INTEGER NOT NULL REFERENCES messages(id)", "constraints": ["FK"], "description": "Reacted message"},
                {"name": "user_id", "type": "INTEGER NOT NULL REFERENCES users(id)", "constraints": ["FK"], "description": "Reacting user"},
                {"name": "emoji", "type": "VARCHAR(10) NOT NULL", "constraints": [], "description": "Reaction emoji"},
            ],
            "indexes": [{"name": "uq_reaction", "columns": ["message_id", "user_id", "emoji"], "unique": True}],
            "relationships": [],
        },
    ],
    "ai": [
        {
            "name": "documents",
            "purpose": "Uploaded source documents (resumes, contracts, images).",
            "columns": [
                {"name": "id", "type": "SERIAL PRIMARY KEY", "constraints": ["PK"], "description": "Unique document identifier"},
                {"name": "owner_id", "type": "INTEGER NOT NULL REFERENCES users(id)", "constraints": ["FK"], "description": "Uploading user"},
                {"name": "filename", "type": "VARCHAR(255) NOT NULL", "constraints": [], "description": "Original filename"},
                {"name": "storage_key", "type": "VARCHAR(500) NOT NULL UNIQUE", "constraints": ["UNIQUE"], "description": "Object storage key"},
                {"name": "content_type", "type": "VARCHAR(100)", "constraints": [], "description": "MIME type"},
                {"name": "size_bytes", "type": "BIGINT", "constraints": [], "description": "File size"},
                {"name": "status", "type": "VARCHAR(20) DEFAULT 'pending'", "constraints": ["CHECK (status IN ('pending','processing','ready','failed'))"], "description": "Processing state"},
                {"name": "created_at", "type": "TIMESTAMPTZ DEFAULT now()", "constraints": [], "description": "Upload time"},
            ],
            "indexes": [{"name": "idx_documents_owner", "columns": ["owner_id"], "unique": False}],
            "relationships": [{"type": "one-to-many", "to_table": "analyses", "on": "documents.id = analyses.document_id"}],
        },
        {
            "name": "analyses",
            "purpose": "AI analysis outputs for documents.",
            "columns": [
                {"name": "id", "type": "SERIAL PRIMARY KEY", "constraints": ["PK"], "description": "Unique analysis identifier"},
                {"name": "document_id", "type": "INTEGER NOT NULL REFERENCES documents(id)", "constraints": ["FK"], "description": "Analyzed document"},
                {"name": "model", "type": "VARCHAR(80)", "constraints": [], "description": "Model used"},
                {"name": "result_json", "type": "JSONB", "constraints": [], "description": "Structured findings"},
                {"name": "score", "type": "NUMERIC(5,2)", "constraints": ["CHECK (score BETWEEN 0 AND 100)"], "description": "Overall score"},
                {"name": "created_at", "type": "TIMESTAMPTZ DEFAULT now()", "constraints": [], "description": "Analysis time"},
            ],
            "indexes": [{"name": "idx_analyses_document", "columns": ["document_id"], "unique": False}],
            "relationships": [],
        },
        {
            "name": "prompts",
            "purpose": "Prompt history for audit and iteration.",
            "columns": [
                {"name": "id", "type": "SERIAL PRIMARY KEY", "constraints": ["PK"], "description": "Unique prompt identifier"},
                {"name": "user_id", "type": "INTEGER NOT NULL REFERENCES users(id)", "constraints": ["FK"], "description": "Prompting user"},
                {"name": "input_text", "type": "TEXT NOT NULL", "constraints": [], "description": "Raw prompt"},
                {"name": "output_text", "type": "TEXT", "constraints": [], "description": "Model output"},
                {"name": "latency_ms", "type": "INTEGER", "constraints": [], "description": "Response latency"},
                {"name": "created_at", "type": "TIMESTAMPTZ DEFAULT now()", "constraints": [], "description": "Prompt time"},
            ],
            "indexes": [{"name": "idx_prompts_user", "columns": ["user_id"], "unique": False}],
            "relationships": [],
        },
    ],
    "saas": [
        {
            "name": "workspaces",
            "purpose": "Organization/tenant container.",
            "columns": [
                {"name": "id", "type": "SERIAL PRIMARY KEY", "constraints": ["PK"], "description": "Unique workspace identifier"},
                {"name": "name", "type": "VARCHAR(150) NOT NULL", "constraints": [], "description": "Workspace name"},
                {"name": "slug", "type": "VARCHAR(160) NOT NULL UNIQUE", "constraints": ["UNIQUE"], "description": "URL slug"},
                {"name": "plan", "type": "VARCHAR(20) DEFAULT 'free'", "constraints": ["CHECK (plan IN ('free','pro','enterprise'))"], "description": "Subscription tier"},
                {"name": "created_at", "type": "TIMESTAMPTZ DEFAULT now()", "constraints": [], "description": "Creation time"},
            ],
            "indexes": [{"name": "idx_workspaces_slug", "columns": ["slug"], "unique": True}],
            "relationships": [{"type": "one-to-many", "to_table": "projects", "on": "workspaces.id = projects.workspace_id"}],
        },
        {
            "name": "projects",
            "purpose": "Top-level units of work.",
            "columns": [
                {"name": "id", "type": "SERIAL PRIMARY KEY", "constraints": ["PK"], "description": "Unique project identifier"},
                {"name": "workspace_id", "type": "INTEGER NOT NULL REFERENCES workspaces(id)", "constraints": ["FK"], "description": "Owning workspace"},
                {"name": "name", "type": "VARCHAR(200) NOT NULL", "constraints": [], "description": "Project name"},
                {"name": "description", "type": "TEXT", "constraints": [], "description": "Project description"},
                {"name": "status", "type": "VARCHAR(20) DEFAULT 'active'", "constraints": ["CHECK (status IN ('active','archived','completed'))"], "description": "Project state"},
                {"name": "created_at", "type": "TIMESTAMPTZ DEFAULT now()", "constraints": [], "description": "Creation time"},
            ],
            "indexes": [{"name": "idx_projects_workspace", "columns": ["workspace_id"], "unique": False}],
            "relationships": [{"type": "one-to-many", "to_table": "tasks", "on": "projects.id = tasks.project_id"}],
        },
        {
            "name": "tasks",
            "purpose": "Work items within projects.",
            "columns": [
                {"name": "id", "type": "SERIAL PRIMARY KEY", "constraints": ["PK"], "description": "Unique task identifier"},
                {"name": "project_id", "type": "INTEGER NOT NULL REFERENCES projects(id)", "constraints": ["FK"], "description": "Owning project"},
                {"name": "title", "type": "VARCHAR(200) NOT NULL", "constraints": [], "description": "Task title"},
                {"name": "assignee_id", "type": "INTEGER REFERENCES users(id)", "constraints": ["FK"], "description": "Assigned user"},
                {"name": "status", "type": "VARCHAR(20) DEFAULT 'todo'", "constraints": ["CHECK (status IN ('todo','in_progress','done','blocked'))"], "description": "Task state"},
                {"name": "priority", "type": "VARCHAR(10) DEFAULT 'medium'", "constraints": ["CHECK (priority IN ('low','medium','high','urgent'))"], "description": "Priority"},
                {"name": "due_date", "type": "DATE", "constraints": [], "description": "Deadline"},
                {"name": "created_at", "type": "TIMESTAMPTZ DEFAULT now()", "constraints": [], "description": "Creation time"},
            ],
            "indexes": [{"name": "idx_tasks_project", "columns": ["project_id"], "unique": False}, {"name": "idx_tasks_assignee", "columns": ["assignee_id"], "unique": False}],
            "relationships": [],
        },
    ],
}

BASE_TABLES = [
    {
        "name": "users",
        "purpose": "Registered application users (auth principal).",
        "columns": [
            {"name": "id", "type": "SERIAL PRIMARY KEY", "constraints": ["PK"], "description": "Unique user identifier"},
            {"name": "email", "type": "VARCHAR(255) NOT NULL UNIQUE", "constraints": ["UNIQUE"], "description": "Login email"},
            {"name": "full_name", "type": "VARCHAR(120)", "constraints": [], "description": "Display name"},
            {"name": "password_hash", "type": "VARCHAR(255) NOT NULL", "constraints": [], "description": "bcrypt hash"},
            {"name": "is_active", "type": "BOOLEAN DEFAULT true", "constraints": [], "description": "Account state"},
            {"name": "created_at", "type": "TIMESTAMPTZ DEFAULT now()", "constraints": [], "description": "Registration time"},
        ],
        "indexes": [{"name": "idx_users_email", "columns": ["email"], "unique": True}],
        "relationships": [],
    },
    {
        "name": "roles",
        "purpose": "Authorization roles (RBAC).",
        "columns": [
            {"name": "id", "type": "SERIAL PRIMARY KEY", "constraints": ["PK"], "description": "Unique role identifier"},
            {"name": "name", "type": "VARCHAR(50) NOT NULL UNIQUE", "constraints": ["UNIQUE"], "description": "Role name"},
            {"name": "description", "type": "TEXT", "constraints": [], "description": "Role description"},
        ],
        "indexes": [],
        "relationships": [],
    },
    {
        "name": "user_roles",
        "purpose": "Many-to-many user-role assignment.",
        "columns": [
            {"name": "id", "type": "SERIAL PRIMARY KEY", "constraints": ["PK"], "description": "Unique assignment identifier"},
            {"name": "user_id", "type": "INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE", "constraints": ["FK"], "description": "Assigned user"},
            {"name": "role_id", "type": "INTEGER NOT NULL REFERENCES roles(id) ON DELETE CASCADE", "constraints": ["FK"], "description": "Assigned role"},
            {"name": "assigned_at", "type": "TIMESTAMPTZ DEFAULT now()", "constraints": [], "description": "Assignment time"},
        ],
        "indexes": [{"name": "uq_user_roles", "columns": ["user_id", "role_id"], "unique": True}],
        "relationships": [],
    },
    {
        "name": "audit_logs",
        "purpose": "Immutable audit trail for sensitive operations.",
        "columns": [
            {"name": "id", "type": "BIGSERIAL PRIMARY KEY", "constraints": ["PK"], "description": "Unique audit identifier"},
            {"name": "user_id", "type": "INTEGER REFERENCES users(id)", "constraints": ["FK"], "description": "Acting user"},
            {"name": "action", "type": "VARCHAR(100) NOT NULL", "constraints": [], "description": "Performed action"},
            {"name": "entity_type", "type": "VARCHAR(50)", "constraints": [], "description": "Affected entity"},
            {"name": "entity_id", "type": "BIGINT", "constraints": [], "description": "Affected entity id"},
            {"name": "metadata", "type": "JSONB", "constraints": [], "description": "Contextual payload"},
            {"name": "created_at", "type": "TIMESTAMPTZ DEFAULT now()", "constraints": [], "description": "Audit time"},
        ],
        "indexes": [{"name": "idx_audit_user_time", "columns": ["user_id", "created_at"], "unique": False}],
        "relationships": [],
    },
]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def _detect_domain(category: str, name: str, description: str, features: list[str]) -> str:
    blob = f"{category} {name} {description} {' '.join(features)}".lower()
    mapping = [
        ("chat", ["chat", "messaging", "conversation", "message"]),
        ("hospital", ["hospital", "clinic", "patient", "doctor", "health", "medical"]),
        ("food", ["food", "restaurant", "delivery", "meal", "recipe", "cuisine"]),
        ("ecommerce", ["ecommerce", "e-commerce", "shop", "store", "product", "cart", "marketplace"]),
        ("inventory", ["inventory", "stock", "warehouse", "supply", "supplier"]),
        ("erp", ["erp", "college", "university", "campus", "student", "school", "education", "academic"]),
        ("ai", ["ai", "analyzer", "resume", "ml", "nlp", "insight", "recommendation engine", "cv"]),
        ("saas", ["saas", "task", "todo", "project management", "workspace", "crm", "erp", "billing", "subscription"]),
    ]
    for domain, keywords in mapping:
        if any(k in blob for k in keywords):
            return domain
    return "saas"


def _build_erd(domain_tables: list[dict[str, Any]]) -> str:
    lines = ["erDiagram"]
    for table in domain_tables:
        name = table["name"]
        lines.append(f"    {name} {{")
        lines.append("        integer id PK")
        for col in table["columns"]:
            if col["name"] == "id":
                continue
            cname = col["name"]
            ctype = col["type"].split()[0].replace("(", "").replace(")", "")
            tag = "FK" if "FK" in " ".join(col["constraints"]) else "UNIQUE" if "UNIQUE" in " ".join(col["constraints"]) else ""
            lines.append(f"        {ctype} {cname} {tag}".rstrip())
        lines.append("    }")
    for table in domain_tables:
        for rel in table.get("relationships", []):
            a, b = sorted([table["name"], rel["to_table"]])
            lines.append(f"    {a} ||--o{{ {b} : \"{rel['type']}\"")
    return "\n".join(lines)


def _build_high_level(frontend: str, backend: str, database: str, deployment: str) -> str:
    return (
        f"graph TD\n"
        f'    A["Client - {frontend}"] -->|"HTTPS/REST"| B["API Gateway / Load Balancer"]\n'
        f'    B --> C["Backend API - {backend}"]\n'
        f'    C --> D["{database}"]\n'
        f'    C -->|"cached reads"| E["Redis Cache (optional)"]\n'
        f'    C -->|"async jobs"| F["Task Queue / Workers"]\n'
        f'    B --> G["Object Storage (S3)"]\n'
        f'    H["Monitoring & Logging"] --> C\n'
        f'    H --> A\n'
        f'    subgraph Runtime["{deployment} Runtime"]\n'
        f"      A\n"
        f"      B\n"
        f"      C\n"
        f"      F\n"
        f"    end"
    )


def _build_component_diagram(backend: str) -> str:
    return (
        f"graph LR\n"
        f'    subgraph Frontend["Frontend - {backend.split()[0] if backend else "Web"}"]\n'
        f'      UI["UI Components"]\n'
        f'      SM["State Management"]\n'
        f'      API["API Client Layer"]\n'
        f'    end\n'
        f'    subgraph Backend["Backend"]\n'
        f'      CTL["Controllers"]\n'
        f'      SVC["Services (business logic)"]\n'
        f'      REP["Repositories (data access)"]\n'
        f'      MW["Middleware (auth, validation)"]\n'
        f'    end\n'
        f'    API --> CTL\n'
        f'    CTL --> SVC\n'
        f'    SVC --> REP\n'
        f'    MW --> CTL\n'
        f'    REP --> DB["Database"]'
    )


def _build_sequence(input_data: dict[str, Any], auth: str) -> str:
    return (
        f"sequenceDiagram\n"
        f'    participant U as User\n'
        f'    participant F as Frontend\n'
        f'    participant B as Backend API\n'
        f'    participant D as Database\n'
        f'    U->>F: Perform action\n'
        f'    F->>B: HTTP Request ({auth} auth)\n'
        f'    B->>B: Validate request / authorize\n'
        f'    B->>D: Query / mutate data\n'
        f'    D-->>B: Result set\n'
        f'    B-->>F: JSON response (200/4xx/5xx)\n'
        f'    F-->>U: Render updated UI'
    )


def _build_deployment_diagram(deployment: str, backend: str) -> str:
    return (
        f"graph TB\n"
        f'    subgraph Platform["{deployment}"]\n'
        f'      LB["Load Balancer"]\n'
        f'      subgraph App["App Cluster"]\n'
        f'        API["{backend} Service"]\n'
        f'        W1["Worker Service"]\n'
        f'      end\n'
        f'      PG["Managed PostgreSQL"]\n'
        f'      REDIS["Redis"]\n'
        f'      S3["Object Storage"]\n'
        f'    end\n'
        f'    LB --> API\n'
        f'    API --> PG\n'
        f'    API --> REDIS\n'
        f'    API --> S3\n'
        f'    W1 --> PG'
    )


def _build_nav_flow() -> str:
    return (
        "flowchart TD\n"
        '    A["Landing / Login"] --> B["Dashboard"]\n'
        '    B --> C["New Project Wizard"]\n'
        '    B --> D["My Projects"]\n'
        '    D --> E["Blueprint Detail"]\n'
        '    E --> F["Export / Edit / Duplicate"]\n'
        '    B --> G["Settings / Profile"]'
    )


def _frontend(frontend: str) -> dict[str, Any]:
    return FRONTENDS.get(frontend, FRONTENDS["React"])


def _backend(backend: str) -> dict[str, Any]:
    return BACKENDS.get(backend, BACKENDS["FastAPI"])


def _db(database: str) -> dict[str, Any]:
    return DATABASES.get(database, DATABASES["PostgreSQL"])


def _auth(auth_method: str) -> dict[str, Any]:
    return AUTH_METHODS.get(auth_method, AUTH_METHODS["JWT"])


def _deploy(deployment: str) -> dict[str, Any]:
    return DEPLOYMENTS.get(deployment, DEPLOYMENTS["Docker"])


def _lang(language: str) -> dict[str, Any]:
    return LANGUAGES.get(language, LANGUAGES["TypeScript"])


# ---------------------------------------------------------------------------
# Blueprint generation
# ---------------------------------------------------------------------------

def _analysis(input_data: dict[str, Any]) -> dict[str, Any]:
    name = input_data["name"]
    desc = input_data["description"] or f"A {input_data['category'].lower()} application designed to solve a focused business problem."
    features = input_data["features"] or ["User management", "Core domain workflows", "Reporting"]

    complexity_factors = [
        f"{len(features)} core feature areas identified",
        f"Stack: {input_data['preferred_frontend']} + {input_data['preferred_backend']}",
        f"Database: {input_data['database']}",
        f"Authentication via {input_data['auth_method']}",
    ]
    if len(features) > 6:
        complexity_factors.append("High feature count increases integration surface")
        overall = "High"
    elif len(features) > 3:
        overall = "Medium"
    else:
        overall = "Low"

    frs = [
        {
            "id": "FR-1",
            "title": "User authentication",
            "description": f"Register, login, logout and profile management using {input_data['auth_method']}.",
            "priority": "Must Have",
        },
        {
            "id": "FR-2",
            "title": "Role-based access control",
            "description": "Admin and end-user roles with permission scoping for all resources.",
            "priority": "Must Have",
        },
    ]
    for i, feature in enumerate(features[:8]):
        frs.append(
            {
                "id": f"FR-{i + 3}",
                "title": feature,
                "description": f"Complete {feature.lower()} workflow: create, read, update, delete, search and audit.",
                "priority": "Must Have" if i < 3 else "Should Have",
            }
        )
    frs.append({"id": "FR-X", "title": "Audit logging", "description": "Immutable audit trail for sensitive operations.", "priority": "Should Have"})

    return {
        "problem_statement": (
            f"Organizations and users currently lack a unified, purpose-built solution for {name.lower()}. "
            f"Existing generic tools force manual workarounds, scattered data and inconsistent workflows. "
            f"{desc.strip('.')}. This project delivers a dedicated platform that automates these workflows, "
            f"enforces data integrity, and provides actionable reporting."
        ),
        "objectives": [
            f"Deliver a production-ready {name} with the chosen {input_data['preferred_backend']} + {input_data['preferred_frontend']} stack",
            "Automate the core domain workflows end-to-end",
            "Enforce data integrity, security and auditability",
            "Provide role-aware dashboards and reporting",
            "Ship with CI/CD, tests and documentation from day one",
        ],
        "target_audience": (
            [u.strip() for u in input_data["target_users"].split(",") if u.strip()]
            or ["Administrators", "End users", "Operations staff"]
        ),
        "functional_requirements": frs,
        "non_functional_requirements": [
            {"id": "NFR-1", "title": "Performance", "description": "API p95 latency under 500ms for read paths; pages interactive under 2s on broadband."},
            {"id": "NFR-2", "title": "Security", "description": f"OWASP Top 10 hardened; {input_data['auth_method']} with short-lived tokens; encrypted secrets."},
            {"id": "NFR-3", "title": "Reliability", "description": "99.9% availability target; graceful degradation; automated health checks."},
            {"id": "NFR-4", "title": "Scalability", "description": "Stateless API services to allow horizontal scaling; database read replicas at scale."},
            {"id": "NFR-5", "title": "Maintainability", "description": "Modular layered architecture, typed contracts, and CI-enforced code quality."},
            {"id": "NFR-6", "title": "Accessibility", "description": "WCAG 2.1 AA compliance for all public-facing flows."},
        ],
        "technology_recommendations": [
            {"name": input_data["preferred_frontend"], "reason": _frontend(input_data["preferred_frontend"])["why"]},
            {"name": input_data["preferred_backend"], "reason": _backend(input_data["preferred_backend"])["why"]},
            {"name": input_data["database"], "reason": _db(input_data["database"])["why"]},
            {"name": f"{input_data['auth_method']} authentication", "reason": _auth(input_data["auth_method"])["why"]},
            {"name": input_data["language"], "reason": _lang(input_data["language"])["why"]},
        ],
        "complexity_analysis": {
            "overall": overall,
            "factors": complexity_factors,
            "recommendation": (
                "Build in vertical slices: ship the first end-to-end feature before generalizing."
                if overall != "Low"
                else "A small team can deliver this rapidly; keep scope frozen after the first release."
            ),
        },
        "estimated_development_time": "6 - 10 weeks for MVP (single team)",
        "estimated_team_size": {"roles": [{"role": "Full-stack developer", "count": 2}, {"role": "Product/QA", "count": 1}], "total": 3},
        "suggested_improvements": [
            "Start with a vertical-slice MVP to validate the core workflow early",
            "Add structured audit logging before the first release",
            "Instrument analytics from day one to drive product decisions",
            "Use feature flags to ship continuously without downtime",
        ],
        "risks": [
            {"risk": "Scope creep during feature definition", "likelihood": "High", "impact": "Medium", "mitigation": "Freeze scope at week 2; prioritize by impact."},
            {"risk": f"{input_data['database']} schema changes late in the cycle", "likelihood": "Medium", "impact": "High", "mitigation": "Mandatory migrations + integration tests."},
            {"risk": "Third-party API availability (auth/payments)", "likelihood": "Medium", "impact": "Medium", "mitigation": "Abstract integrations behind interfaces with mock fallbacks."},
            {"risk": "Security review gaps", "likelihood": "Medium", "impact": "High", "mitigation": "Automated SAST in CI + scheduled dependency updates."},
        ],
    }


def _architecture(input_data: dict[str, Any], analysis: dict[str, Any]) -> dict[str, Any]:
    frontend, backend, database, deployment = (
        input_data["preferred_frontend"],
        input_data["preferred_backend"],
        input_data["database"],
        input_data["deployment_platform"],
    )
    complexity = analysis["complexity_analysis"]["overall"]
    patterns = [
        {"pattern": "Layered (Controller-Service-Repository)", "explanation": "Separates HTTP handling, business logic and data access for testability."},
        {"pattern": "Repository pattern", "explanation": "Abstracts the database so the domain layer never depends on SQL specifics."},
        {"pattern": "DTO + validation boundary", "explanation": "Explicit request/response contracts validated at the edge."},
    ]
    if complexity == "High":
        patterns.append({"pattern": "Service layer with dependency injection", "explanation": "Enables unit testing with mocks and clean interchangeability."})
    return {
        "summary": (
            f"A clean, layered web architecture: a {frontend} SPA talks to a stateless {backend} REST API "
            f"backed by {database}, deployed via {deployment}. The system favors synchronous REST for CRUD and "
            f"asynchronous jobs for anything slow or external."
        ),
        "patterns": patterns,
        "high_level_architecture": _build_high_level(frontend, backend, database, deployment),
        "component_diagram": _build_component_diagram(backend),
        "data_flow": _build_sequence(input_data, input_data["auth_method"]),
        "service_communication": (
            "graph TB\n"
            '    subgraph Services["Backend Services"]\n'
            '      AUTH["Auth Service"]\n'
            '      CORE["Core Domain Service"]\n'
            '      NOTIF["Notification Service"]\n'
            '      REPORT["Reporting Service"]\n'
            '    end\n'
            '    subgraph Infra["Shared Infrastructure"]\n'
            '      DB["PostgreSQL"]\n'
            '      CACHE["Redis"]\n'
            '      BUS["Message Bus (Redis Streams / RabbitMQ)"]\n'
            '    end\n'
            '    CORE --> DB\n'
            '    AUTH --> DB\n'
            '    REPORT --> DB\n'
            '    CORE --> BUS\n'
            '    NOTIF --> BUS\n'
            '    REPORT --> CACHE\n'
            '    CORE --> CACHE'
        ),
        "deployment_architecture": _build_deployment_diagram(deployment, backend),
        "components": [
            {"name": "Web client", "responsibility": "Rendering, state management, user interaction", "technology": frontend},
            {"name": "API service", "responsibility": "REST endpoints, validation, orchestration", "technology": backend},
            {"name": "Data store", "responsibility": "Persistent storage and queries", "technology": database},
            {"name": "Worker (optional)", "responsibility": "Email, exports, background jobs", "technology": "Celery / BullMQ / Quartz"},
            {"name": "Observability", "responsibility": "Logs, metrics, tracing, uptime", "technology": "Prometheus + Grafana / Sentry"},
        ],
    }


def _folder_structure(input_data: dict[str, Any]) -> dict[str, Any]:
    fe = input_data["preferred_frontend"].lower()
    be = input_data["preferred_backend"].lower()
    src_ext = "ts" if "type" in input_data["language"].lower() or "javascript" in input_data["language"].lower() else "py"
    tree = f"""{_slugify(input_data['name'])}/
├── backend/                      # API service
│   ├── app/
│   │   ├── main.{'py' if src_ext == 'py' else 'ts'}            # entry point
│   │   ├── config/              # configuration
│   │   ├── controllers/         # request handlers
│   │   ├── services/            # business logic
│   │   ├── repositories/        # data access
│   │   ├── middleware/          # auth, logging, error handling
│   │   ├── models/              # database models
│   │   ├── schemas/             # DTOs / validation
│   │   ├── routes/              # route registration
│   │   └── utils/
│   ├── migrations/              # schema migrations
│   ├── seed/                    # seed data scripts
│   ├── tests/
│   │   ├── unit/
│   │   ├── integration/
│   │   └── api/
│   ├── Dockerfile
│   ├── requirements.txt
│   └── .env.example
├── frontend/                    # {fe} web client
│   ├── src/
│   │   ├── app/                # routes / pages
│   │   ├── components/         # reusable UI
│   │   ├── pages/              # route-level views
│   │   ├── hooks/              # custom hooks
│   │   ├── services/           # API client layer
│   │   ├── stores/             # state management
│   │   ├── assets/             # static assets
│   │   └── styles/
│   ├── public/
│   ├── Dockerfile
│   └── .env.example
├── database/
│   ├── migrations/
│   └── seed/
├── docker/
│   ├── Dockerfile.{be}
│   ├── Dockerfile.{fe}
│   └── compose.yaml
├── docs/
│   ├── architecture.md
│   ├── api.md
│   ├── database.md
│   └── deployment.md
├── .github/workflows/ci.yml
├── .env.example
├── docker-compose.yml
└── README.md"""
    return {
        "tree": tree,
        "key_directories": [
            {"path": "backend/", "purpose": "API service with layered architecture (controllers -> services -> repositories)."},
            {"path": "frontend/", "purpose": "Web client with colocated routes, components, hooks and API services."},
            {"path": "database/", "purpose": "Migration scripts and deterministic seed data."},
            {"path": "docs/", "purpose": "Living documentation for architecture, API, database and deployment."},
            {"path": "docker/", "purpose": "Container definitions and compose overrides."},
            {"path": ".github/workflows/", "purpose": "CI/CD pipelines."},
        ],
    }


def _database(input_data: dict[str, Any], analysis: dict[str, Any]) -> dict[str, Any]:
    database = input_data["database"]
    db_info = _db(database)
    domain = _detect_domain(input_data["category"], input_data["name"], input_data["description"], input_data["features"])
    domain_tables = TABLE_RECIPES.get(domain, TABLE_RECIPES["saas"])
    tables = BASE_TABLES + domain_tables

    erd = _build_erd(tables)

    create_lines = ["-- PostgreSQL-compatible DDL generated by AI Project Builder Agent", ""]
    for table in tables:
        create_lines.append(f"CREATE TABLE IF NOT EXISTS {table['name']} (")
        col_lines = []
        for col in table["columns"]:
            col_lines.append(f"    {col['name']} {col['type']},")
        for index in table["indexes"]:
            suffix = " UNIQUE" if index["unique"] else ""
            create_lines.append(");")
            create_lines.append(f"CREATE{suffix} INDEX IF NOT EXISTS {index['name']} ON {table['name']} ({', '.join(index['columns'])});")
            create_lines.append("")
            continue
        create_lines.append(");")
        create_lines.append("")

    sql_scripts = {
        "create_tables": "\n".join(create_lines),
        "indexes": "".join(
            f"CREATE{' UNIQUE' if i['unique'] else ''} INDEX IF NOT EXISTS {i['name']} ON {t['name']} ({', '.join(i['columns'])});\n"
            for t in tables
            for i in t["indexes"]
        ).strip(),
        "constraints": (
            "ALTER TABLE user_roles ADD CONSTRAINT fk_user_roles_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;\n"
            "ALTER TABLE user_roles ADD CONSTRAINT fk_user_roles_role FOREIGN KEY (role_id) REFERENCES roles(id) ON DELETE CASCADE;\n"
            + "\n".join(
                f"ALTER TABLE {t['name']} ADD CONSTRAINT fk_{t['name']}_{r['to_table']} FOREIGN KEY ({r['to_table'].rstrip('s')}_id) REFERENCES {r['to_table']}(id) ON DELETE CASCADE;"
                for t in tables
                for r in t.get("relationships", [])
            )
        ),
    }

    return {
        "erd_diagram": erd,
        "summary": (
            f"A normalized relational schema on {database} ({db_info['type']}) with strict foreign keys, "
            f"check constraints and indexes tuned for the dominant query paths. "
            f"All timestamps use TIMESTAMPTZ; amounts use NUMERIC to avoid float drift."
        ),
        "tables": tables,
        "sql_scripts": sql_scripts,
        "migration_scripts": [
            {"file": "0001_initial.py", "description": "Creates all base and domain tables with indexes.", "sql": sql_scripts["create_tables"]},
            {"file": "0002_constraints.py", "description": "Adds FK and check constraints not expressed inline.", "sql": sql_scripts["constraints"]},
        ],
        "seed_data": {
            "file": "seed/dev_seed.py",
            "description": "Deterministic development seed: admin user, roles, and sample domain records.",
            "sql": (
                "-- Seed: 1 admin user + 2 roles + sample records\n"
                "INSERT INTO roles (name, description) VALUES ('admin', 'Full access'), ('member', 'Standard access');\n"
                "INSERT INTO users (email, full_name, password_hash, is_active)\n"
                "VALUES ('admin@example.com', 'Admin', '$2b$12$placeholder_hash', true);"
            ),
        },
    }


def _api(input_data: dict[str, Any], db_section: dict[str, Any]) -> dict[str, Any]:
    backend_info = _backend(input_data["preferred_backend"])
    auth_info = _auth(input_data["auth_method"])
    tables = [t["name"] for t in db_section["tables"]]
    endpoints = [
        {
            "path": "/auth/register",
            "method": "POST",
            "description": "Create a new user account.",
            "authentication": "None",
            "request": {"headers": {"Content-Type": "application/json"}, "body": {"email": "string", "password": "string (min 8)", "full_name": "string"}},
            "response": {"success": {"id": 1, "email": "string"}, "errors": {"409": "Email already registered"}},
            "validation_rules": ["email format", "password min 8 chars", "unique email"],
            "status_codes": [{"code": 201, "meaning": "Created"}, {"code": 409, "meaning": "Email exists"}, {"code": 422, "meaning": "Validation failed"}],
        },
        {
            "path": "/auth/login",
            "method": "POST",
            "description": f"Authenticate and receive an access token ({input_data['auth_method']}).",
            "authentication": "None",
            "request": {"headers": {"Content-Type": "application/json"}, "body": {"email": "string", "password": "string"}},
            "response": {"success": {"access_token": "string", "token_type": "bearer"}, "errors": {"401": "Invalid credentials"}},
            "validation_rules": ["credentials must match"],
            "status_codes": [{"code": 200, "meaning": "Token issued"}, {"code": 401, "meaning": "Bad credentials"}],
        },
        {
            "path": "/auth/me",
            "method": "GET",
            "description": "Return the authenticated user profile.",
            "authentication": f"Bearer token ({input_data['auth_method']})",
            "request": {"headers": {"Authorization": "Bearer <token>"}, "body": {}},
            "response": {"success": {"id": 1, "email": "string", "full_name": "string"}, "errors": {"401": "Missing/invalid token"}},
            "validation_rules": ["valid access token required"],
            "status_codes": [{"code": 200, "meaning": "Profile"}, {"code": 401, "meaning": "Unauthorized"}],
        },
    ]
    for table in tables:
        path = f"/{table.replace('_', '-')}"
        endpoints.append(
            {
                "path": path,
                "method": "GET",
                "description": f"List {table.replace('_', ' ')} with pagination, filtering and search.",
                "authentication": f"Bearer token ({input_data['auth_method']})",
                "request": {"headers": {"Authorization": "Bearer <token>"}, "body": {}, "query": {"page": 1, "page_size": 50, "q": "optional search"}},
                "response": {"success": {"items": [], "total": 0, "page": 1}, "errors": {"401": "Unauthorized", "403": "Forbidden"}},
                "validation_rules": ["page >= 1", "page_size <= 100"],
                "status_codes": [{"code": 200, "meaning": "List"}, {"code": 401, "meaning": "Unauthorized"}],
            }
        )
        endpoints.append(
            {
                "path": path,
                "method": "POST",
                "description": f"Create a new {table.replace('_', ' ').rstrip('s')} record.",
                "authentication": f"Bearer token ({input_data['auth_method']})",
                "request": {"headers": {"Authorization": "Bearer <token>"}, "body": {"...": "resource fields"}},
                "response": {"success": {"id": 1}, "errors": {"400": "Business rule violation", "422": "Validation failed"}},
                "validation_rules": ["required fields", "foreign keys must exist"],
                "status_codes": [{"code": 201, "meaning": "Created"}, {"code": 422, "meaning": "Validation failed"}],
            }
        )
    return {
        "summary": (
            f"A REST API built with {input_data['preferred_backend']} ({backend_info['type']}). "
            f"Resources follow the tables in the database design; all write endpoints validate input and "
            f"audit changes. Authentication uses {auth_info['type']}."
        ),
        "base_url": "/api/v1",
        "auth": {"method": input_data["auth_method"], "description": auth_info["type"], "flow": auth_info["flow"]},
        "endpoints": endpoints,
        "pagination": "Cursor or offset pagination: ?page=N&page_size=N (max 100). Responses include items, total, page.",
        "error_format": '{"detail": "human readable message", "code": "MACHINE_CODE", "field": "optional"}',
    }


def _ui_ux(input_data: dict[str, Any]) -> dict[str, Any]:
    screens = [
        {"name": "Login", "route": "/login", "purpose": "Authenticate users", "key_components": ["AuthForm", "BrandMark", "PasswordField"]},
        {"name": "Dashboard", "route": "/", "purpose": "Overview with KPIs and quick actions", "key_components": ["StatCard", "RecentList", "QuickActions"]},
        {"name": "List view", "route": "/{resource}", "purpose": "Paginated, filterable table of records", "key_components": ["DataTable", "FilterBar", "Pagination"]},
        {"name": "Detail view", "route": "/{resource}/:id", "purpose": "Full record with edit/delete", "key_components": ["DetailPanel", "ActionMenu"]},
        {"name": "Create/Edit form", "route": "/{resource}/new", "purpose": "Capture validated input", "key_components": ["FormShell", "Field", "SubmitButton"]},
        {"name": "Settings", "route": "/settings", "purpose": "Profile and preferences", "key_components": ["Tabs", "ProfileForm", "DangerZone"]},
    ]
    return {
        "design_principles": [
            "Progressive disclosure: show essentials first, detail on demand",
            "Consistent spacing scale and one accent color",
            "Optimistic UI with clear loading and empty states",
            "Accessible by default: keyboard navigation and ARIA labels",
        ],
        "screens": screens,
        "navigation_flow": _build_nav_flow(),
        "components": [
            {"name": "AppShell", "purpose": "Sidebar + topbar + content frame", "props": ["navItems", "user"]},
            {"name": "StatCard", "purpose": "KPI metric display", "props": ["label", "value", "trend", "icon"]},
            {"name": "DataTable", "purpose": "Sortable/filterable table", "props": ["columns", "rows", "loading"]},
            {"name": "Modal", "purpose": "Focused dialogs", "props": ["open", "title", "children"]},
            {"name": "Toast", "purpose": "Transient feedback", "props": ["variant", "message"]},
            {"name": "FormField", "purpose": "Labeled input with validation", "props": ["label", "error", "hint"]},
            {"name": "EmptyState", "purpose": "Empty list guidance", "props": ["title", "action"]},
            {"name": "ConfirmDialog", "purpose": "Destructive action confirmation", "props": ["title", "onConfirm"]},
        ],
        "forms": [
            {
                "name": "Auth forms",
                "fields": [
                    {"name": "email", "type": "email", "validation": "required, valid email"},
                    {"name": "password", "type": "password", "validation": "required, min 8 chars"},
                ],
            },
            {
                "name": "Entity form",
                "fields": [
                    {"name": "name", "type": "text", "validation": "required, max 200"},
                    {"name": "description", "type": "textarea", "validation": "optional, max 2000"},
                    {"name": "status", "type": "select", "validation": "one of allowed enum"},
                ],
            },
        ],
        "tables": [
            {
                "name": "Resource table",
                "columns": ["Name", "Status", "Owner", "Updated at", "Actions"],
                "features": ["Server-side pagination", "Search + column filters", "Row selection for bulk actions"],
            }
        ],
        "dashboard_layout": (
            "Top KPI row (4 stat cards) -> primary content grid (main table 2/3, activity feed 1/3) -> "
            "secondary row (chart + quick actions). Stacks vertically below 1024px."
        ),
        "responsive_strategy": "Mobile-first; sidebar collapses to a drawer, tables scroll horizontally, forms go single-column.",
        "colors": {
            "primary": "#4F46E5 (Indigo 600)",
            "secondary": "#0F172A (Slate 900)",
            "accent": "#10B981 (Emerald 500)",
            "background": "#F8FAFC (Slate 50)",
            "text": "#1E293B (Slate 800)",
        },
        "typography": {"font_family": "Inter", "headings": "600/700 weight, tight tracking", "body": "400 weight, 1.5 line height"},
        "reusable_components": ["Button", "Input", "Select", "Badge", "Table", "Card", "Tabs", "Avatar", "Spinner", "EmptyState", "ConfirmDialog"],
    }


def _roadmap(input_data: dict[str, Any], analysis: dict[str, Any]) -> dict[str, Any]:
    complexity = analysis["complexity_analysis"]["overall"]
    weeks = 4 if complexity == "Low" else 6 if complexity == "Medium" else 8
    base_hours = 90 if complexity == "Low" else 150 if complexity == "Medium" else 230
    milestones = []
    themes = [
        ("Planning, architecture & database", ["Write PRD and acceptance criteria", "Define architecture and data model", "Set up repo, CI and environments", "Create database schema + migrations", "Bootstrap backend and frontend projects"]),
        ("Authentication & core backend", [f"Implement {input_data['auth_method']} auth flow", "Role-based access control", "Core domain CRUD APIs", "Validation, error handling and audit logs", "Unit tests for services"]),
        ("Frontend & integration", ["App shell, navigation and routing", "Auth screens and guards", "Core domain screens (list/detail/form)", "Connect API client layer", "End-to-end integration tests"]),
        ("Testing, hardening & deployment", ["API and security tests", "Performance pass and edge cases", "Seed data and documentation", "Docker + CI/CD pipeline", f"Deploy to {input_data['deployment_platform']}", "Stakeholder demo and release notes"]),
    ]
    if weeks > 4:
        themes = themes[:2] + [
            ("Advanced features & reporting", ["Reporting and analytics endpoints", "Search, filters and export", "Notification flows", "Admin screens", "QA regression pass"]),
        ] + themes[2:]
    if weeks > 6:
        themes = themes[:2] + [
            ("Advanced features & reporting", ["Reporting and analytics endpoints", "Search, filters and export", "Notification flows", "Admin screens", "QA regression pass"]),
        ] + themes[2:4] + [
            ("Hardening & performance", ["Load testing and tuning", "Caching and query optimization", "Security review and fixes", "Disaster recovery drills"]),
        ] + themes[4:]

    hours_per_week = int(base_hours / len(themes)) + 5
    for idx, (theme, tasks) in enumerate(themes, start=1):
        tasks_payload = [{"task": t, "hours": max(3, hours_per_week // len(tasks) - idx), "deliverable": t} for t in tasks]
        week_hours = sum(t["hours"] for t in tasks_payload)
        milestones.append(
            {
                "week": idx,
                "theme": theme,
                "tasks": tasks_payload,
                "week_hours": week_hours,
                "goal": f"Complete: {theme.lower()}",
            }
        )

    return {
        "summary": f"A {len(themes)}-week roadmap (~{sum(m['week_hours'] for m in milestones)} hours) built on vertical slices with continuous testing.",
        "total_estimated_hours": sum(m["week_hours"] for m in milestones),
        "weekly_milestones": milestones,
        "critical_path": ["Requirements freeze", "Database schema", "Authentication", "Core CRUD APIs", "Frontend integration", "Release hardening"],
        "team_plan": [
            {"role": "Full-stack engineer", "focus": "Vertical slices end-to-end"},
            {"role": "QA engineer", "focus": "Test strategy, automation, release sign-off"},
            {"role": "Product owner", "focus": "Requirements, acceptance criteria, stakeholder demos"},
        ],
    }


def _git_commits(input_data: dict[str, Any]) -> dict[str, Any]:
    name = input_data["name"]
    messages = [
        ("chore", "Initialize repository", f"Project scaffolding for {name}"),
        ("chore", "Setup backend", "FastAPI app, config, database wiring, CI badge"),
        ("feat", "Add authentication", "JWT register/login/logout with password hashing"),
        ("feat", "Add user module", "Profile endpoints and RBAC roles"),
        ("feat", "Implement core CRUD APIs", "Domain resources with validation and pagination"),
        ("feat", "Build dashboard", "KPI cards, charts and recent activity feed"),
        ("feat", "Add search and filters", "Server-side search across core resources"),
        ("feat", "Add export functionality", "CSV/Excel export for list views"),
        ("fix", "Fix race condition on concurrent writes", "Row-level locking and retry logic"),
        ("test", "Add API test suite", "Coverage for auth and core endpoints"),
        ("docs", "Write architecture documentation", "ADRs, diagrams and runbooks"),
        ("refactor", "Extract service layer", "Controllers thin, business logic in services"),
        ("deploy", "Deploy application", "Docker image, env config, production release v1.0.0"),
    ]
    history = []
    for i, (scope, msg, desc) in enumerate(messages):
        history.append({"hash": f"a1b2c3d{i:04d}", "message": f"{scope}: {msg}", "description": desc, "scope": scope})
    return {"history": history}


def _testing(input_data: dict[str, Any]) -> dict[str, Any]:
    return {
        "summary": (
            "A pragmatic pyramid: many fast unit tests, fewer integration tests, and a thin set of "
            "end-to-end tests. Everything runs in CI on every push."
        ),
        "unit_tests": [
            {"name": "test_auth_register", "target": "AuthService.register", "scenario": "Valid input creates user; duplicate email raises conflict."},
            {"name": "test_auth_login", "target": "AuthService.login", "scenario": "Correct password returns token; wrong password rejected."},
            {"name": "test_service_validation", "target": "DomainService.create", "scenario": "Invalid payload rejected with field-level errors."},
            {"name": "test_money_math", "target": "Pricing module", "scenario": "Totals computed without floating point drift."},
            {"name": "test_repository_filters", "target": "Repository.list", "scenario": "Pagination + filters return expected slices."},
        ],
        "integration_tests": [
            {"name": "test_registration_flow", "flow": "register -> login -> me", "scenario": "Full auth journey against the real database."},
            {"name": "test_crud_lifecycle", "flow": "create -> read -> update -> delete", "scenario": "Resource lifecycle persists correctly."},
            {"name": "test_rbac_matrix", "flow": "admin vs member", "scenario": "Permission matrix enforced on every route."},
            {"name": "test_migration_smoke", "flow": "migrate -> seed -> query", "scenario": "Migrations and seed data apply cleanly on a fresh database."},
        ],
        "api_tests": [
            {"name": "api_auth_flow", "endpoint": "/auth/*", "method": "POST", "scenario": "Register/login/me return documented status codes."},
            {"name": "api_crud", "endpoint": "/{resource}", "method": "GET/POST/PUT/DELETE", "scenario": "Happy path + 401 without token + 422 on bad payload."},
            {"name": "api_pagination", "endpoint": "/{resource}", "method": "GET", "scenario": "Page bounds respected; page_size capped."},
        ],
        "security_tests": [
            {"name": "jwt_expiry", "threat": "Replay of expired tokens", "scenario": "Expired token returns 401; refresh rotates tokens."},
            {"name": "injection_probe", "threat": "SQL / NoSQL injection", "scenario": "Malicious strings in filters are neutralized by parameterization."},
            {"name": "privacy_leak", "threat": "Horizontal privilege escalation", "scenario": "User A cannot read/update User B resources."},
            {"name": "rate_limit", "threat": "Credential stuffing", "scenario": "Login endpoint throttled after N failures."},
        ],
        "performance_tests": [
            {"name": "api_p95", "metric": "p95 latency", "threshold": "< 500ms on 50 RPS", "scenario": "k6 load test on read endpoints."},
            {"name": "list_scalability", "metric": "query time", "threshold": "< 300ms with 1M rows", "scenario": "Index verification on the largest tables."},
            {"name": "frontend_lcp", "metric": "Largest Contentful Paint", "threshold": "< 2.5s", "scenario": "Lighthouse budget on dashboard route."},
        ],
        "edge_cases": [
            {"name": "empty_collections", "scenario": "Every list view renders a helpful empty state."},
            {"name": "duplicate_submit", "scenario": "Double-click submit creates exactly one record."},
            {"name": "unicode_names", "scenario": "Non-ASCII names and text survive round-trips."},
            {"name": "concurrent_edits", "scenario": "Last-write-wins with optimistic locking warning."},
            {"name": "large_payloads", "scenario": "Payloads near the limit handled without 500s."},
        ],
        "test_data": (
            "Deterministic seed: 1 admin + 3 members, 10 core records, unique emails. "
            "Faker-based factories for load and scale tests."
        ),
        "qa_checklist": [
            "All listed screens render with empty, loading, error and populated states",
            "No unhandled 5xx on any documented endpoint",
            "RBAC matrix verified for every role",
            "Accessibility: keyboard navigation on all primary flows",
            "Responsive: 375px, 768px, 1440px breakpoints pass",
            "Dark-mode and contrast issues resolved",
            "Documentation matches shipped behavior",
        ],
    }


def _deployment(input_data: dict[str, Any]) -> dict[str, Any]:
    dockerfile = (
        "# Backend Dockerfile (production)\n"
        "FROM python:3.13-slim AS base\n"
        "WORKDIR /app\n"
        "ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1\n"
        "RUN apt-get update && apt-get install -y --no-install-recommends build-essential && rm -rf /var/lib/apt/lists/*\n"
        "COPY requirements.txt .\n"
        "RUN pip install --no-cache-dir -r requirements.txt\n"
        "COPY . .\n"
        "EXPOSE 8010\n"
        'CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8010"]'
    )
    compose = (
        "services:\n"
        "  api:\n"
        "    build: .\n"
        "    env_file: .env\n"
        "    ports: ['8010:8010']\n"
        "    depends_on:\n"
        "      - db\n"
        "  db:\n"
        "    image: postgres:16-alpine\n"
        "    environment:\n"
        "      POSTGRES_USER: postgres\n"
        "      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}\n"
        "      POSTGRES_DB: app\n"
        "    volumes: ['pgdata:/var/lib/postgresql/data']\n"
        "  web:\n"
        "    build: ../frontend\n"
        "    ports: ['3010:3010']\n"
        "volumes:\n"
        "  pgdata:"
    )
    return {
        "dockerfile": dockerfile,
        "docker_compose": compose,
        "environment_variables": [
            {"name": "DATABASE_URL", "purpose": "Connection string", "secret": True},
            {"name": "SECRET_KEY", "purpose": "Token signing key", "secret": True},
            {"name": "OPENAI_API_KEY", "purpose": "LLM provider key", "secret": True},
            {"name": "SMTP_PASSWORD", "purpose": "Email sending", "secret": True},
            {"name": "CORS_ORIGINS", "purpose": "Allowed browser origins", "secret": False},
        ],
        "github_actions": (
            "name: CI\non: [push, pull_request]\njobs:\n"
            "  test:\n"
            "    runs-on: ubuntu-latest\n"
            "    steps:\n"
            "      - uses: actions/checkout@v4\n"
            "      - uses: actions/setup-python@v5\n"
            "        with: {python-version: '3.13'}\n"
            "      - run: pip install -r requirements.txt -r requirements-dev.txt\n"
            "      - run: pytest -q\n"
            "  build:\n"
            "    runs-on: ubuntu-latest\n"
            "    steps:\n"
            "      - uses: actions/checkout@v4\n"
            "      - uses: actions/setup-node@v4\n"
            "        with: {node-version: 22}\n"
            "      - run: npm ci\n"
            "      - run: npm run build"
        ),
        "production_guide": (
            f"1) Provision a managed {input_data['database']} instance and set DATABASE_URL.\n"
            f"2) Build and push the Docker image (backend + frontend) to a registry.\n"
            f"3) Deploy to {input_data['deployment_platform']} with the env block from the blueprint.\n"
            f"4) Run migrations on release, then switch traffic behind the load balancer.\n"
            f"5) Verify health endpoint, logs and metrics; enable automatic rollback on failed health checks."
        ),
        "monitoring": [
            {"tool": "Sentry", "what": "Errors and exceptions", "why": "Context-rich crash reporting with release tracking."},
            {"tool": "Prometheus + Grafana", "what": "API latency, throughput, error rate", "why": "Standard open-source metrics stack with dashboards."},
            {"tool": "Health checks", "what": "Liveness/readiness on /healthz", "why": "Orchestrator-level automatic restarts."},
            {"tool": "Uptime monitoring", "what": "External availability", "why": "Detects outages from the user's perspective."},
        ],
        "logging_strategy": (
            "Structured JSON logs (level, service, request_id, duration_ms). Correlation ID propagated "
            "from gateway to services; 30-day retention; error logs alerted in real time."
        ),
        "ci_cd_pipeline": [
            {"stage": "Lint", "actions": ["Ruff / ESLint on every push"]},
            {"stage": "Test", "actions": ["Unit + integration + API tests; coverage gate >= 80%"]},
            {"stage": "Build", "actions": ["Docker images built and scanned (Trivy)"]},
            {"stage": "Deploy", "actions": ["Tagged releases auto-deploy; DB migrations run before rollout"]},
        ],
    }


def _documentation(input_data: dict[str, Any], blueprint: dict[str, Any]) -> dict[str, Any]:
    name = input_data["name"]
    fe, be, db = input_data["preferred_frontend"], input_data["preferred_backend"], input_data["database"]
    readme = f"""# {name}

A professional-grade software blueprint for **{name}** — generated by the AI Project Builder Agent.

## Stack

| Layer | Choice |
|-------|--------|
| Frontend | {fe} |
| Backend | {be} |
| Database | {db} |
| Auth | {input_data['auth_method']} |
| Deployment | {input_data['deployment_platform']} |

## Quick start

```bash
cp .env.example .env
docker compose up -d
# backend: http://localhost:8010/docs   frontend: http://localhost:3010
```

## Repository layout

```
backend/    API service (controllers -> services -> repositories)
frontend/   Web client
database/   Migrations and seed data
docs/       Architecture, API, database and deployment docs
```

## Documentation

- [Architecture](docs/architecture.md)
- [API reference](docs/api.md)
- [Database design](docs/database.md)
- [Deployment guide](docs/deployment.md)
"""
    installation = (
        "## Installation\n\n### Prerequisites\n- Python 3.13+, Node 22+, Docker (optional)\n\n"
        "### 1. Backend\n```bash\ncd backend\npython -m venv .venv\nsource .venv/bin/activate  # Windows: .venv\\Scripts\\activate\npip install -r requirements.txt\nuvicorn app.main:app --reload\n```\n"
        "### 2. Frontend\n```bash\ncd frontend\nnpm install\ncp .env.local.example .env.local\nnpm run dev\n```\n"
        "### 3. Verify\nOpen http://localhost:8010/docs (Swagger) and http://localhost:3010."
    )
    return {
        "readme": readme,
        "installation_guide": installation,
        "api_documentation": f"See the API section of the blueprint: {len(blueprint['api']['endpoints'])} endpoints documented with request/response examples, validation rules and status codes. Interactive docs available via the framework's OpenAPI UI.",
        "architecture_documentation": "Layered architecture (controller -> service -> repository) with a stateless API, documented component/data-flow diagrams and deployment topology.",
        "database_documentation": f"Normalized {db} schema with ERD, FK/CHECK constraints, indexes and migration strategy (Alembic/Flyway/Knex).",
        "deployment_guide": f"Containerized via Docker, deployed to {input_data['deployment_platform']}, monitored with Sentry + Prometheus/Grafana, logging via structured JSON.",
        "contribution_guide": "1) Fork and branch from main. 2) Run lint + tests locally. 3) Open a PR with a clear description. 4) CI must pass; changes to API schemas require updated docs.",
        "future_improvements": [
            "Real-time features via WebSockets (notifications, presence)",
            "Multi-tenancy and workspace isolation",
            "Advanced analytics and export pipelines",
            "Mobile app (React Native / PWA)",
            "Automated accessibility audits in CI",
        ],
    }


def _recommendations(input_data: dict[str, Any]) -> dict[str, Any]:
    return {
        "libraries": [
            {"name": "Pydantic / Zod", "why": "Contract-first validation at the API boundary prevents invalid state."},
            {"name": "Alembic (or framework equivalent)", "why": "Versioned migrations make schema changes reviewable and reversible."},
            {"name": "TanStack Query", "why": "Caching, retries and background refetch for server state with minimal code."},
            {"name": "pytest + Playwright", "why": "Fast unit tests plus browser-level E2E for the critical flows."},
        ],
        "design_patterns": [
            {"name": "Repository", "why": "Isolates the database so services stay testable with fakes."},
            {"name": "Service layer", "why": "Keeps controllers thin and business rules centralized."},
            {"name": "DTO mapping", "why": "Internal models never leak to the API contract."},
            {"name": "Factory for test data", "why": "Deterministic seeds across environments."},
        ],
        "security_best_practices": [
            {"name": "OWASP dependency scanning in CI", "why": "Catches known CVEs before they ship."},
            {"name": "Short-lived access tokens + refresh rotation", "why": "Limits the blast radius of a leaked token."},
            {"name": "Parameterized queries everywhere", "why": "Eliminates the entire SQL injection class."},
            {"name": "Secrets manager (never .env in git)", "why": "Prevents accidental key exposure."},
            {"name": "Security headers + CORS allowlist", "why": "Reduces clickjacking/XSS and cross-origin abuse."},
        ],
        "performance_improvements": [
            {"name": "Pagination on every list endpoint", "why": "Bounded payloads keep p95 stable as data grows."},
            {"name": "Composite indexes for filters", "why": "Common filter combinations stay index-accelerated."},
            {"name": "HTTP caching for static assets", "why": "Drops repeat-load latency without code changes."},
            {"name": "Connection pooling", "why": "Avoids per-request database handshake overhead."},
        ],
        "scalability_suggestions": [
            {"name": "Stateless API replicas behind a load balancer", "why": "Horizontal scale without sticky-session complexity."},
            {"name": "Read replicas for report-heavy queries", "why": "Keeps transactional writes isolated from analytics load."},
            {"name": "Background workers for email/exports", "why": "Long tasks never block the request path."},
            {"name": "Cache hot read paths in Redis", "why": "Drops database QPS for popular queries."},
        ],
        "future_features": [
            {"name": "Real-time notifications", "value": "Higher engagement; trivial with WebSockets + Redis pub/sub."},
            {"name": "CSV/Excel bulk export", "value": "Ops users rely on it weekly; low implementation cost."},
            {"name": "Webhooks for third-party integration", "value": "Makes the product embeddable in other tools."},
            {"name": "Dark mode + i18n", "value": "Broadens appeal and accessibility."},
        ],
        "risk_analysis": [
            {"name": "Data loss on schema changes", "level": "Medium", "mitigation": "Zero-downtime migration pattern + nightly backups."},
            {"name": "Vendor lock-in (auth provider)", "level": "Medium", "mitigation": "Abstract provider behind an interface; keep local accounts."},
            {"name": "Performance degradation at scale", "level": "Low", "mitigation": "Load test before major releases; indexes reviewed monthly."},
        ],
        "cost_optimization": [
            {"name": "Right-size cloud instances", "savings": "Up to 40%", "how": "Start small; scale horizontally instead of vertically."},
            {"name": "Redis + CDN cache hits", "savings": "20-30% compute", "how": "Serve reads from cache, not the database."},
            {"name": "Reserved capacity for stable workloads", "savings": "Up to 60%", "how": "Commit to steady-state instances on AWS/Azure."},
        ],
    }


def generate_blueprint(input_data: dict[str, Any]) -> dict[str, Any]:
    """Deterministically generate a complete blueprint from wizard input."""
    analysis = _analysis(input_data)
    architecture = _architecture(input_data, analysis)
    folder_structure = _folder_structure(input_data)
    database = _database(input_data, analysis)
    api = _api(input_data, database)
    ui_ux = _ui_ux(input_data)
    roadmap = _roadmap(input_data, analysis)
    git_commits = _git_commits(input_data)
    testing = _testing(input_data)
    deployment = _deployment(input_data)

    return {
        "analysis": analysis,
        "architecture": architecture,
        "folder_structure": folder_structure,
        "database": database,
        "api": api,
        "ui_ux": ui_ux,
        "roadmap": roadmap,
        "git_commits": git_commits,
        "testing": testing,
        "deployment": deployment,
        "recommendations": _recommendations(input_data),
        "documentation": _documentation(
            input_data, blueprint={"api": api, "database": database, "architecture": architecture}
        ),
    }
