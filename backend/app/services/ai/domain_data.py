"""Business domain knowledge base.

Each domain captures what a Senior Architect identifies before designing any
technical artifact: business domain, core workflow, primary users, roles,
processes, modules, entities, relationships, business rules and future
expansion. Used by the Domain Understanding, Business Process Modeling,
Database and API agents so output is domain-aware rather than generic.

Entity specs use a compact tuple format expanded by ``expand_entity_spec``:
    (name, purpose, columns, indexes, relationships, normalization_notes)
columns       :: (name, type, description)
indexes       :: (name, columns, unique)
relationships :: (relationship_type, to_table, on_clause)

Domains whose entity set already existed in the v1 recipe tables reuse them
via ``recipe_domains``; new domains define their entities inline.
"""
from __future__ import annotations

from typing import Any

EntitySpec = tuple[
    str, str,
    list[tuple[str, str, str]],
    list[tuple[str, list[str], bool]],
    list[tuple[str, str, str]],
    str,
]

# Common reference column helpers
_REF = "INTEGER NOT NULL REFERENCES {t}(id)"
_REF_OPT = "INTEGER REFERENCES {t}(id)"


def expand_entity_spec(spec: EntitySpec) -> dict[str, Any]:
    name, purpose, columns, indexes, relationships, normalization = spec
    full_columns = [
        {"name": "id", "type": "SERIAL PRIMARY KEY", "constraints": ["PK"], "description": f"Unique {name.rstrip('s')} identifier"}
    ]
    for col_name, col_type, col_desc in columns:
        constraints: list[str] = []
        upper = col_type.upper()
        if "REFERENCES" in upper:
            constraints.append("FK")
        if "UNIQUE" in upper:
            constraints.append("UNIQUE")
        if "NOT NULL" in upper:
            constraints.append("NOT NULL")
        if "CHECK" in upper:
            constraints.append("CHECK")
        if "PRIMARY KEY" in upper:
            constraints.append("PK")
        full_columns.append({"name": col_name, "type": col_type, "constraints": constraints, "description": col_desc})
    return {
        "name": name,
        "purpose": purpose,
        "columns": full_columns,
        "indexes": [{"name": idx_name, "columns": idx_cols, "unique": unique} for idx_name, idx_cols, unique in indexes],
        "relationships": [
            {"type": rel_type, "to_table": to_table, "on": on_clause} for rel_type, to_table, on_clause in relationships
        ],
        "normalization_notes": normalization,
    }


def _idx(name: str, columns: str | list[str], unique: bool = False) -> tuple[str, list[str], bool]:
    return (name, columns if isinstance(columns, list) else [columns], unique)


# ---------------------------------------------------------------------------
# New domains (inline compact entity specs)
# ---------------------------------------------------------------------------

NEW_DOMAINS: dict[str, dict[str, Any]] = {
    "smart_city": {
        "label": "Smart City Management",
        "core_workflow": "Citizens register and submit service requests; departments manage public infrastructure — traffic signals, public transport, utilities and waste collection — while sensors stream telemetry, incidents are triaged by emergency teams, and dashboards drive city operations.",
        "primary_users": ["Citizens", "City departments", "Transport authority", "Emergency services", "City administrators"],
        "roles": ["Citizen", "Department Officer", "Dispatcher", "City Administrator"],
        "processes": ["Traffic management", "Public transport operations", "Utility monitoring", "Waste collection", "Emergency dispatch", "Citizen service requests", "Environmental monitoring", "IoT sensor telemetry"],
        "entities": [
            ("citizens", "City residents registered for citizen services.", [
                ("full_name", "VARCHAR(150) NOT NULL", "Full name"),
                ("email", "VARCHAR(150) NOT NULL UNIQUE", "Contact email"),
                ("phone", "VARCHAR(20)", "Contact phone"),
                ("address", "TEXT", "Residential address"),
                ("created_at", "TIMESTAMPTZ DEFAULT now()", "Registration time"),
            ], [_idx("idx_citizens_email", "email", True)], [("one-to-many", "service_requests", "citizens.id = service_requests.citizen_id")], "3NF; citizen identity is independent of any single request."),
            ("departments", "City departments owning service areas.", [
                ("name", "VARCHAR(150) NOT NULL", "Department name"),
                ("head_name", "VARCHAR(150)", "Department head"),
                ("service_area", "VARCHAR(200)", "Covered responsibility"),
                ("contact", "VARCHAR(20)", "Contact phone"),
            ], [_idx("idx_departments_name", "name", True)], [("one-to-many", "emergency_teams", "departments.id = emergency_teams.department_id")], ""),
            ("traffic_signals", "Traffic light infrastructure and state.", [
                ("location", "VARCHAR(200) NOT NULL", "Intersection location"),
                ("controller_ip", "VARCHAR(50)", "Controller address"),
                ("status", "VARCHAR(20) DEFAULT 'operational'", "Operational / fault / maintenance"),
                ("last_maintenance", "DATE", "Last service date"),
            ], [_idx("idx_signals_location", "location")], [], ""),
            ("routes", "Public transport routes.", [
                ("name", "VARCHAR(150) NOT NULL", "Route name"),
                ("origin", "VARCHAR(120)", "Origin stop"),
                ("destination", "VARCHAR(120)", "Destination stop"),
                ("distance_km", "NUMERIC(8,2)", "Route length"),
                ("frequency_minutes", "INTEGER", "Headway in minutes"),
            ], [_idx("idx_routes_name", "name", True)], [("one-to-many", "buses", "routes.id = buses.route_id")], ""),
            ("buses", "Fleet vehicles assigned to routes.", [
                ("plate_number", "VARCHAR(20) NOT NULL UNIQUE", "Vehicle plate"),
                ("route_id", _REF.format(t="routes"), "Assigned route"),
                ("capacity", "INTEGER", "Passenger capacity"),
                ("status", "VARCHAR(20) DEFAULT 'on_route'", "On route / depot / maintenance"),
                ("current_location", "VARCHAR(120)", "Live position label"),
            ], [_idx("idx_buses_plate", "plate_number", True), _idx("idx_buses_route", "route_id")], [("many-to-one", "routes", "buses.route_id = routes.id")], ""),
            ("utilities", "Water, power and gas assets under management.", [
                ("utility_type", "VARCHAR(30) NOT NULL", "Water / power / gas"),
                ("name", "VARCHAR(150) NOT NULL", "Asset name"),
                ("service_area", "VARCHAR(200)", "Served district"),
                ("provider", "VARCHAR(120)", "Operating provider"),
                ("status", "VARCHAR(20) DEFAULT 'active'", "Active / degraded / offline"),
            ], [_idx("idx_utilities_type", "utility_type")], [("one-to-many", "incidents", "utilities.id = incidents.utility_id")], ""),
            ("sensors", "IoT sensors streaming city telemetry.", [
                ("device_id", "VARCHAR(60) NOT NULL UNIQUE", "Device identifier"),
                ("sensor_type", "VARCHAR(40)", "Air / water / traffic / energy"),
                ("location", "VARCHAR(200)", "Installation point"),
                ("status", "VARCHAR(20) DEFAULT 'online'", "Online / offline / battery"),
                ("last_reading", "NUMERIC(14,2)", "Latest telemetry value"),
                ("battery_level", "SMALLINT", "Battery percentage"),
                ("installed_at", "DATE", "Installation date"),
            ], [_idx("idx_sensors_device", "device_id", True), _idx("idx_sensors_type", "sensor_type")], [], "Readings are append-only telemetry; the last_reading column is a denormalized snapshot."),
            ("incidents", "City incidents triaged by emergency teams.", [
                ("incident_type", "VARCHAR(60) NOT NULL", "Fire / flood / accident / outage"),
                ("severity", "VARCHAR(15) DEFAULT 'medium'", "Low / medium / high / critical"),
                ("location", "VARCHAR(200)", "Incident location"),
                ("description", "TEXT", "Incident details"),
                ("status", "VARCHAR(20) DEFAULT 'reported'", "Reported / dispatched / stabilized / closed"),
                ("reported_by", _REF_OPT.format(t="citizens"), "Reporting citizen"),
                ("assigned_team", _REF_OPT.format(t="emergency_teams"), "Dispatched team"),
                ("utility_id", _REF_OPT.format(t="utilities"), "Affected utility"),
                ("created_at", "TIMESTAMPTZ DEFAULT now()", "Report time"),
            ], [_idx("idx_incidents_status", "status"), _idx("idx_incidents_team", "assigned_team")], [], "Status transitions are state-machine constrained by business rules."),
            ("emergency_teams", "Dispatchable response units.", [
                ("name", "VARCHAR(150) NOT NULL", "Team name"),
                ("team_type", "VARCHAR(40)", "Fire / medical / utility / police"),
                ("department_id", _REF.format(t="departments"), "Owning department"),
                ("status", "VARCHAR(20) DEFAULT 'available'", "Available / dispatched"),
                ("location", "VARCHAR(120)", "Current position"),
                ("contact", "VARCHAR(20)", "Dispatch contact"),
            ], [_idx("idx_teams_department", "department_id")], [("many-to-one", "departments", "emergency_teams.department_id = departments.id")], ""),
            ("waste_collections", "Planned and completed collection runs.", [
                ("schedule_date", "DATE NOT NULL", "Collection date"),
                ("zone", "VARCHAR(80)", "Collection zone"),
                ("status", "VARCHAR(20) DEFAULT 'scheduled'", "Scheduled / in_progress / completed"),
                ("collected_weight_kg", "NUMERIC(10,2)", "Logged weight"),
                ("notes", "TEXT", "Route notes"),
            ], [_idx("idx_collections_zone_date", "zone", False)], [], ""),
            ("service_requests", "Citizen-submitted service requests.", [
                ("citizen_id", _REF.format(t="citizens"), "Requesting citizen"),
                ("category", "VARCHAR(80) NOT NULL", "Pothole / lighting / waste / noise"),
                ("title", "VARCHAR(200) NOT NULL", "Request title"),
                ("description", "TEXT", "Request details"),
                ("priority", "VARCHAR(15) DEFAULT 'normal'", "Low / normal / high"),
                ("status", "VARCHAR(20) DEFAULT 'submitted'", "Submitted / assigned / resolved"),
                ("assigned_department", _REF_OPT.format(t="departments"), "Owning department"),
                ("created_at", "TIMESTAMPTZ DEFAULT now()", "Submission time"),
                ("resolved_at", "TIMESTAMPTZ", "Resolution time"),
            ], [_idx("idx_requests_citizen", "citizen_id"), _idx("idx_requests_status", "status")], [("many-to-one", "citizens", "service_requests.citizen_id = citizens.id")], "Requests are the citizen-facing SLA ledger."),
        ],
        "modules": [
            {"name": "Traffic & Transport", "purpose": "Signals, routes and fleet operations", "entities": ["traffic_signals", "routes", "buses"]},
            {"name": "Utilities & Environment", "purpose": "Utility assets and IoT sensor telemetry", "entities": ["utilities", "sensors"]},
            {"name": "Emergency & Safety", "purpose": "Incident triage and team dispatch", "entities": ["incidents", "emergency_teams"]},
            {"name": "Citizen Services", "purpose": "Service requests and feedback", "entities": ["citizens", "service_requests"]},
            {"name": "Waste Operations", "purpose": "Collection runs and route validation", "entities": ["waste_collections"]},
            {"name": "City Administration", "purpose": "Department registry and governance", "entities": ["departments"]},
        ],
        "business_rules": [
            "An incident can only be closed by the assigned emergency team after a stabilization report.",
            "A service request must be resolved within the SLA window of its priority.",
            "Sensor readings are append-only; corrections are recorded as new readings.",
            "A bus can only be assigned to a route in 'on_route' status.",
        ],
        "future_expansion": ["Autonomous transit", "Predictive maintenance on sensors", "Smart parking", "Energy grid optimization", "Citizen mobile app"],
        "workflows": [
            {"name": "Emergency incident response", "description": "From report to stabilization.", "steps": [
                "Incident reported", "Incident triaged by dispatcher", "Emergency team dispatched",
                "Situation stabilized", "Report filed",
            ]},
            {"name": "Citizen service request", "description": "From submission to resolution.", "steps": [
                "Request submitted", "Request assigned to department", "Work scheduled",
                "Request resolved", "Citizen notified",
            ]},
            {"name": "Waste collection run", "description": "From planning to validated collection.", "steps": [
                "Route planned", "Crew dispatched", "Collection completed",
                "Weight logged", "Route validated",
            ]},
        ],
    },
    "startup": {
        "label": "Startup Incubator",
        "core_workflow": "Founder submits an idea, the platform validates it, market research and competitor analysis follow, a business model is built, an investor pitch is generated, funding is raised, and the startup is tracked through milestones.",
        "primary_users": ["Founders", "Investors", "Incubation program managers", "Mentors"],
        "roles": ["Founder", "Investor", "Mentor", "Program Manager", "Administrator"],
        "processes": ["Idea submission & AI validation", "Market research", "Competitor analysis", "Business model building", "Pitch generation", "Investor matching", "Funding rounds", "Milestone tracking"],
        "entities": [
            ("startups", "Incubated companies with validation status.", [
                ("name", "VARCHAR(150) NOT NULL", "Startup name"),
                ("founder_id", _REF.format(t="founders"), "Lead founder"),
                ("stage", "VARCHAR(30) DEFAULT 'ideation'", "Ideation / validation / funding / scaled"),
                ("sector", "VARCHAR(80)", "Target industry"),
                ("pitch_deck_url", "TEXT", "Deck storage reference"),
                ("created_at", "TIMESTAMPTZ DEFAULT now()", "Registration time"),
            ], [_idx("idx_startups_founder", "founder_id"), _idx("idx_startups_stage", "stage")], [
                ("one-to-many", "pitches", "startups.id = pitches.startup_id"),
                ("one-to-many", "funding_rounds", "startups.id = funding_rounds.startup_id"),
            ], "3NF; each startup has one lead founder and is tracked by stage."),
            ("founders", "Founder profiles and contact details.", [
                ("name", "VARCHAR(150) NOT NULL", "Founder full name"),
                ("email", "VARCHAR(150) NOT NULL UNIQUE", "Contact email"),
                ("linkedin_url", "TEXT", "Professional profile"),
                ("expertise", "VARCHAR(120)", "Domain expertise"),
            ], [_idx("idx_founders_email", "email", True)], [], "3NF; founder identity is independent of any single startup."),
            ("investors", "Investors and their focus areas for matching.", [
                ("name", "VARCHAR(150) NOT NULL", "Investor / firm name"),
                ("investor_type", "VARCHAR(40)", "Angel / VC / Corporate"),
                ("focus_sectors", "JSONB", "Preferred sectors"),
                ("ticket_min", "NUMERIC(12,2)", "Minimum ticket size"),
                ("ticket_max", "NUMERIC(12,2)", "Maximum ticket size"),
                ("is_active", "BOOLEAN DEFAULT true", "Actively deploying capital"),
            ], [], [], "Denormalized focus sectors speed up the matching query."),
            ("pitches", "Pitch submissions and their AI validation results.", [
                ("startup_id", _REF.format(t="startups"), "Pitching startup"),
                ("deck_text", "TEXT", "Submitted idea / deck text"),
                ("validation_score", "NUMERIC(5,2)", "AI validation 0-100"),
                ("ai_feedback", "TEXT", "AI improvement suggestions"),
                ("status", "VARCHAR(20) DEFAULT 'submitted'", "Submitted / validated / rejected"),
                ("submitted_at", "TIMESTAMPTZ DEFAULT now()", "Submission time"),
            ], [_idx("idx_pitches_startup", "startup_id")], [
                ("many-to-one", "startups", "pitches.startup_id = startups.id"),
            ], "Pitches are append-only; every submission is a new row so history is preserved."),
            ("mentors", "Experts assigned to startups.", [
                ("name", "VARCHAR(150) NOT NULL", "Mentor name"),
                ("expertise", "VARCHAR(120)", "Domain expertise"),
                ("availability", "VARCHAR(20) DEFAULT 'available'", "Availability state"),
            ], [], [], ""),
            ("milestones", "Verifiable milestones in the incubation roadmap.", [
                ("startup_id", _REF.format(t="startups"), "Owning startup"),
                ("title", "VARCHAR(200) NOT NULL", "Milestone title"),
                ("status", "VARCHAR(20) DEFAULT 'pending'", "Pending / in_progress / achieved"),
                ("due_date", "DATE", "Planned completion"),
            ], [], [], "Milestones are the progress ledger that gates funding."),
            ("funding_rounds", "Capital raised per round.", [
                ("startup_id", _REF.format(t="startups"), "Raising startup"),
                ("round_type", "VARCHAR(30)", "Pre-seed / seed / Series A"),
                ("amount", "NUMERIC(14,2) NOT NULL", "Total raised"),
                ("closed_date", "DATE", "Closing date"),
            ], [_idx("idx_rounds_startup", "startup_id")], [
                ("many-to-one", "startups", "funding_rounds.startup_id = startups.id"),
            ], "Money data uses NUMERIC, never float."),
            ("market_researches", "Market sizing studies per startup.", [
                ("startup_id", _REF.format(t="startups"), "Commissioning startup"),
                ("market_size", "NUMERIC(14,2)", "TAM estimate"),
                ("growth_rate", "NUMERIC(6,2)", "CAGR estimate"),
                ("source", "VARCHAR(120)", "Research source"),
                ("conducted_at", "DATE", "Study date"),
            ], [], [], "3NF; one study row per research run."),
            ("competitors", "Competitive landscape entries.", [
                ("startup_id", _REF.format(t="startups"), "Compared startup"),
                ("competitor_name", "VARCHAR(150) NOT NULL", "Competitor"),
                ("strengths", "TEXT", "Competitor strengths"),
                ("weaknesses", "TEXT", "Competitor weaknesses"),
                ("threat_level", "VARCHAR(10) DEFAULT 'medium'", "Low / medium / high"),
            ], [_idx("idx_competitors_startup", "startup_id")], [], ""),
            ("business_models", "Revenue model definitions.", [
                ("startup_id", _REF.format(t="startups"), "Owning startup"),
                ("model_type", "VARCHAR(60)", "Subscription / commission / freemium"),
                ("unit_economics", "JSONB", "CAC, LTV, margins"),
                ("reviewed_at", "DATE", "Last review"),
            ], [], [], ""),
            ("revenue_projections", "Forecast scenarios per startup.", [
                ("startup_id", _REF.format(t="startups"), "Owning startup"),
                ("scenario", "VARCHAR(20) DEFAULT 'base'", "Conservative / base / optimistic"),
                ("year", "INTEGER NOT NULL", "Forecast year"),
                ("projected_revenue", "NUMERIC(14,2)", "Revenue forecast"),
            ], [], [], "One row per startup per scenario per year."),
            ("tasks", "Assigned action items in the program.", [
                ("startup_id", _REF.format(t="startups"), "Owning startup"),
                ("assigned_to", _REF.format(t="mentors"), "Assignee"),
                ("title", "VARCHAR(200) NOT NULL", "Task title"),
                ("status", "VARCHAR(20) DEFAULT 'todo'", "Task state"),
                ("due_date", "DATE", "Deadline"),
            ], [], [], ""),
        ],
        "modules": [
            {"name": "Idea Validation", "purpose": "Submit, validate and score startup ideas", "entities": ["pitches", "startups"]},
            {"name": "Market & Competitors", "purpose": "Market research and competitive tracking", "entities": ["market_researches", "competitors"]},
            {"name": "Funding", "purpose": "Business models, investor matching and funding rounds", "entities": ["business_models", "revenue_projections", "investors", "funding_rounds"]},
            {"name": "Mentorship & Progress", "purpose": "Mentor assignment, tasks and milestone tracking", "entities": ["mentors", "tasks", "milestones"]},
        ],
        "business_rules": [
            "An investor can only be matched to a startup whose validation_score exceeds 60.",
            "A funding round requires a completed market research and competitor analysis.",
            "Funding cannot be recorded before the required milestones are achieved.",
            "Financial mutations are always written to the audit log.",
        ],
        "future_expansion": ["ESOP management", "Due diligence workflows", "Investor syndication", "Founder discovery"],
        "workflows": [
            {"name": "Incubation pipeline", "description": "An idea moves from submission to growth.", "steps": [
                "Founder submits startup idea", "AI validates idea", "Market research conducted",
                "Competitor analysis", "Business model built", "Investor pitch", "Funding raised", "Progress tracking",
            ]},
            {"name": "Investor matching", "description": "Investors are matched to validated startups.", "steps": [
                "Startup passes validation", "Investor preferences loaded", "Matching engine scores fit",
                "Intro meeting scheduled", "Due diligence", "Term sheet issued",
            ]},
        ],
    },
    "agriculture": {
        "label": "Agriculture",
        "core_workflow": "Farmers register farms and fields, plant crops, track harvests, record equipment and supplies, and sell produce while sensor data informs decisions.",
        "primary_users": ["Farmers", "Agronomists", "Cooperative managers", "Suppliers"],
        "roles": ["Farmer", "Agronomist", "Warehouse manager", "Administrator"],
        "processes": ["Farm & field registration", "Crop planning", "Planting & harvest tracking", "Equipment management", "Supply procurement", "Produce sales"],
        "entities": [
            ("farms", "Registered farms and their owners.", [
                ("name", "VARCHAR(150) NOT NULL", "Farm name"),
                ("owner_id", _REF.format(t="users"), "Owning user"),
                ("location", "TEXT", "Physical location"),
                ("total_area_hectares", "NUMERIC(8,2)", "Total area"),
            ], [_idx("idx_farms_owner", "owner_id")], [("one-to-many", "fields", "farms.id = fields.farm_id")], "3NF."),
            ("fields", "Sub-divided agricultural plots.", [
                ("farm_id", _REF.format(t="farms"), "Owning farm"),
                ("name", "VARCHAR(120) NOT NULL", "Field name"),
                ("area_hectares", "NUMERIC(8,2)", "Field area"),
                ("soil_type", "VARCHAR(60)", "Soil classification"),
                ("irrigation_type", "VARCHAR(60)", "Irrigation method"),
            ], [_idx("idx_fields_farm", "farm_id")], [("one-to-many", "crops", "fields.id = crops.field_id")], "Fields belong to exactly one farm."),
            ("crops", "Crop cycles planted in fields.", [
                ("field_id", _REF.format(t="fields"), "Planted field"),
                ("crop_name", "VARCHAR(120) NOT NULL", "Crop variety"),
                ("planted_on", "DATE NOT NULL", "Planting date"),
                ("expected_harvest", "DATE", "Expected harvest"),
                ("status", "VARCHAR(20) DEFAULT 'growing'", "Growing / harvested / failed"),
            ], [_idx("idx_crops_field_status", "field_id")], [("one-to-many", "harvests", "crops.id = harvests.crop_id")], ""),
            ("harvests", "Recorded harvest yields.", [
                ("crop_id", _REF.format(t="crops"), "Harvested crop cycle"),
                ("yield_tonnes", "NUMERIC(10,2) NOT NULL", "Yield"),
                ("harvested_on", "DATE NOT NULL", "Harvest date"),
                ("quality_grade", "VARCHAR(10)", "A / B / C grade"),
            ], [], [], ""),
            ("equipment", "Farm machinery and its state.", [
                ("farm_id", _REF.format(t="farms"), "Owning farm"),
                ("name", "VARCHAR(120) NOT NULL", "Equipment name"),
                ("status", "VARCHAR(20) DEFAULT 'operational'", "Operational / maintenance / broken"),
                ("last_maintenance", "DATE", "Last service date"),
            ], [], [], ""),
            ("suppliers", "Input suppliers (seeds, fertilizer).", [
                ("name", "VARCHAR(150) NOT NULL", "Supplier name"),
                ("category", "VARCHAR(60)", "Supply category"),
                ("contact", "VARCHAR(20)", "Contact phone"),
            ], [], [("one-to-many", "sales_orders", "suppliers.id = sales_orders.supplier_id")], ""),
            ("sales_orders", "Produce sales and supply purchases.", [
                ("farm_id", _REF.format(t="farms"), "Selling farm"),
                ("supplier_id", _REF_OPT.format(t="suppliers"), "Purchased from"),
                ("type", "VARCHAR(10) NOT NULL", "Sale / purchase"),
                ("amount", "NUMERIC(12,2) NOT NULL", "Transaction amount"),
                ("created_at", "TIMESTAMPTZ DEFAULT now()", "Order time"),
            ], [_idx("idx_orders_farm", "farm_id")], [], "Amounts are NUMERIC to avoid float drift."),
        ],
        "modules": [
            {"name": "Farm Management", "purpose": "Farms, fields and equipment", "entities": ["farms", "fields", "equipment"]},
            {"name": "Crop Operations", "purpose": "Planting, growing and harvest tracking", "entities": ["crops", "harvests"]},
            {"name": "Supply & Sales", "purpose": "Suppliers and produce transactions", "entities": ["suppliers", "sales_orders"]},
        ],
        "business_rules": [
            "A field cannot host two active crop cycles at once.",
            "Harvest yield must be recorded before a crop cycle is marked harvested.",
            "Equipment flagged for maintenance cannot be assigned to a new cycle.",
        ],
        "future_expansion": ["IoT sensor telemetry", "Yield forecasting with ML", "Crop insurance", "Marketplace for produce"],
        "workflows": [
            {"name": "Crop season", "description": "From field preparation to sale.", "steps": [
                "Register farm and fields", "Plan crop and suppliers", "Plant crop",
                "Monitor growth", "Harvest and grade", "Sell produce",
            ]},
        ],
    },
    "finance": {
        "label": "Finance",
        "core_workflow": "Customers and accounts are onboarded, transactions are posted, budgets are planned, invoices are issued and payments are reconciled.",
        "primary_users": ["Customers", "Accountants", "Finance managers", "Admins"],
        "roles": ["Customer", "Accountant", "Finance Manager", "Compliance Officer"],
        "processes": ["Customer onboarding", "Account management", "Transaction posting", "Budgeting", "Invoicing", "Payment reconciliation"],
        "entities": [
            ("customers", "Bank / finance customers.", [
                ("name", "VARCHAR(150) NOT NULL", "Customer name"),
                ("email", "VARCHAR(150) NOT NULL UNIQUE", "Contact email"),
                ("kyc_status", "VARCHAR(20) DEFAULT 'pending'", "KYC verification state"),
                ("risk_rating", "VARCHAR(10) DEFAULT 'low'", "Compliance risk rating"),
            ], [_idx("idx_customers_email", "email", True)], [("one-to-many", "accounts", "customers.id = accounts.customer_id")], "3NF."),
            ("accounts", "Customer financial accounts.", [
                ("customer_id", _REF.format(t="customers"), "Account owner"),
                ("account_number", "VARCHAR(30) NOT NULL UNIQUE", "Account number"),
                ("account_type", "VARCHAR(30)", "Savings / current / loan"),
                ("balance", "NUMERIC(14,2) NOT NULL DEFAULT 0", "Current balance"),
                ("currency", "VARCHAR(3) DEFAULT 'USD'", "Currency code"),
                ("status", "VARCHAR(20) DEFAULT 'active'", "Account state"),
            ], [_idx("idx_accounts_number", "account_number", True), _idx("idx_accounts_customer", "customer_id")], [("one-to-many", "transactions", "accounts.id = transactions.account_id")], "Balance is denormalized and reconciled via the ledger."),
            ("transactions", "Immutable financial ledger entries.", [
                ("account_id", _REF.format(t="accounts"), "Affected account"),
                ("transaction_type", "VARCHAR(20) NOT NULL", "Credit / debit / transfer"),
                ("amount", "NUMERIC(14,2) NOT NULL", "Transaction amount"),
                ("counterparty", "VARCHAR(150)", "Other party"),
                ("reference", "VARCHAR(100) UNIQUE", "External reference"),
                ("posted_at", "TIMESTAMPTZ DEFAULT now()", "Posting time"),
            ], [_idx("idx_transactions_account_time", "account_id"), _idx("idx_transactions_reference", "reference", True)], [], "Append-only ledger; amounts use NUMERIC."),
            ("budgets", "Planned financial targets.", [
                ("category", "VARCHAR(80) NOT NULL", "Budget category"),
                ("period", "VARCHAR(20) NOT NULL", "FY / quarter / month"),
                ("planned_amount", "NUMERIC(14,2) NOT NULL", "Planned value"),
                ("actual_amount", "NUMERIC(14,2) DEFAULT 0", "Tracked actual"),
            ], [], [], ""),
            ("invoices", "Issued invoices with line totals.", [
                ("customer_id", _REF.format(t="customers"), "Billed customer"),
                ("invoice_number", "VARCHAR(30) NOT NULL UNIQUE", "Invoice number"),
                ("total", "NUMERIC(14,2) NOT NULL", "Invoice total"),
                ("status", "VARCHAR(20) DEFAULT 'issued'", "Issued / paid / overdue"),
                ("due_date", "DATE", "Payment deadline"),
            ], [_idx("idx_invoices_customer", "customer_id")], [], "Totals are NUMERIC and computed from line items."),
            ("payments", "Received payments against invoices.", [
                ("invoice_id", _REF.format(t="invoices"), "Settled invoice"),
                ("amount", "NUMERIC(14,2) NOT NULL", "Paid amount"),
                ("method", "VARCHAR(30)", "Card / wire / cash"),
                ("received_at", "TIMESTAMPTZ DEFAULT now()", "Payment time"),
            ], [], [], ""),
        ],
        "modules": [
            {"name": "Customer Onboarding", "purpose": "KYC, risk ratings and customer records", "entities": ["customers"]},
            {"name": "Accounts & Ledger", "purpose": "Accounts, transactions and reconciliation", "entities": ["accounts", "transactions"]},
            {"name": "Billing & Budgets", "purpose": "Budgets, invoices and payment reconciliation", "entities": ["budgets", "invoices", "payments"]},
        ],
        "business_rules": [
            "A transaction cannot post if it would overdraw a restricted account.",
            "Invoice status transitions: issued -> paid, or issued -> overdue after due_date.",
            "All financial mutations must be recorded in the immutable ledger first.",
        ],
        "future_expansion": ["Loan origination", "FX and multi-currency", "AML monitoring", "Open banking APIs"],
        "workflows": [
            {"name": "Payment lifecycle", "description": "From invoice to reconciliation.", "steps": [
                "Invoice issued", "Customer notified", "Payment received",
                "Ledger posted", "Invoice reconciled", "Statement updated",
            ]},
        ],
    },
    "travel": {
        "label": "Travel",
        "core_workflow": "Travelers search destinations and packages, compare hotels and flights, book itineraries, pay, travel, and leave reviews.",
        "primary_users": ["Travelers", "Travel agents", "Hotel partners", "Admins"],
        "roles": ["Traveler", "Agent", "Partner", "Administrator"],
        "processes": ["Destination discovery", "Package booking", "Hotel & flight reservation", "Payment", "Trip management", "Reviews"],
        "entities": [
            ("destinations", "Travel destinations with profiles.", [
                ("name", "VARCHAR(150) NOT NULL", "Destination name"),
                ("country", "VARCHAR(80)", "Country"),
                ("description", "TEXT", "Destination overview"),
                ("best_season", "VARCHAR(40)", "Recommended travel window"),
            ], [], [("one-to-many", "packages", "destinations.id = packages.destination_id")], "3NF."),
            ("packages", "Curated travel packages.", [
                ("destination_id", _REF.format(t="destinations"), "Target destination"),
                ("name", "VARCHAR(200) NOT NULL", "Package name"),
                ("duration_days", "INTEGER NOT NULL", "Trip duration"),
                ("price", "NUMERIC(10,2) NOT NULL", "Package price"),
                ("includes", "JSONB", "Included items"),
                ("is_active", "BOOLEAN DEFAULT true", "Bookable"),
            ], [_idx("idx_packages_destination", "destination_id")], [("one-to-many", "bookings", "packages.id = bookings.package_id")], ""),
            ("hotels", "Partner hotels.", [
                ("name", "VARCHAR(150) NOT NULL", "Hotel name"),
                ("destination_id", _REF.format(t="destinations"), "Located destination"),
                ("star_rating", "SMALLINT", "1-5 stars"),
                ("price_per_night", "NUMERIC(10,2)", "Nightly rate"),
                ("amenities", "JSONB", "Amenity list"),
            ], [], [], ""),
            ("flights", "Available flight legs.", [
                ("origin", "VARCHAR(80) NOT NULL", "Departure city"),
                ("destination", "VARCHAR(80) NOT NULL", "Arrival city"),
                ("airline", "VARCHAR(80)", "Carrier"),
                ("departs_at", "TIMESTAMPTZ", "Departure time"),
                ("price", "NUMERIC(10,2)", "Ticket price"),
            ], [], [], ""),
            ("bookings", "Traveler bookings.", [
                ("traveler_id", _REF.format(t="users"), "Booking customer"),
                ("package_id", _REF.format(t="packages"), "Booked package"),
                ("status", "VARCHAR(20) DEFAULT 'pending'", "Pending / confirmed / cancelled / completed"),
                ("total", "NUMERIC(10,2) NOT NULL", "Booking total"),
                ("booked_at", "TIMESTAMPTZ DEFAULT now()", "Booking time"),
            ], [_idx("idx_bookings_traveler", "traveler_id")], [("one-to-many", "payments", "bookings.id = payments.booking_id")], ""),
            ("payments", "Booking payments.", [
                ("booking_id", _REF.format(t="bookings"), "Paid booking"),
                ("amount", "NUMERIC(10,2) NOT NULL", "Paid amount"),
                ("method", "VARCHAR(30)", "Payment method"),
                ("gateway_ref", "VARCHAR(100) UNIQUE", "Gateway reference"),
                ("status", "VARCHAR(20) DEFAULT 'pending'", "Payment state"),
            ], [], [], ""),
            ("reviews", "Post-trip traveler reviews.", [
                ("booking_id", _REF.format(t="bookings"), "Reviewed booking"),
                ("rating", "SMALLINT NOT NULL", "1-5 rating"),
                ("comment", "TEXT", "Review text"),
            ], [], [], "One review per booking enforced by a unique index."),
        ],
        "modules": [
            {"name": "Discovery", "purpose": "Destinations, hotels and flights", "entities": ["destinations", "hotels", "flights"]},
            {"name": "Bookings", "purpose": "Packages, reservations and payments", "entities": ["packages", "bookings", "payments"]},
            {"name": "Community", "purpose": "Traveler reviews and ratings", "entities": ["reviews"]},
        ],
        "business_rules": [
            "A booking can only be confirmed after payment succeeds.",
            "Cancelation rules depend on the days remaining until departure.",
            "A traveler can review a package only after completing the booking.",
        ],
        "future_expansion": ["Dynamic pricing", "Loyalty program", "Group bookings", "Itinerary builder"],
        "workflows": [
            {"name": "Booking journey", "description": "From discovery to review.", "steps": [
                "Search destinations", "Compare packages", "Select package",
                "Book and pay", "Receive confirmation", "Travel", "Leave review",
            ]},
        ],
    },
    "retail": {
        "label": "Retail",
        "core_workflow": "Products are listed with promotions, customers shop via POS or online, sales are recorded, stock adjusts, returns are processed and suppliers replenish inventory.",
        "primary_users": ["Customers", "Store staff", "Store managers", "Suppliers"],
        "roles": ["Customer", "Cashier", "Manager", "Supplier"],
        "processes": ["Product cataloging", "Promotion management", "Sales (POS/web)", "Inventory adjustment", "Returns", "Supplier replenishment"],
        "entities": [
            ("stores", "Retail locations.", [
                ("name", "VARCHAR(150) NOT NULL", "Store name"),
                ("location", "TEXT", "Store address"),
                ("opening_hours", "VARCHAR(100)", "Operating hours"),
            ], [], [("one-to-many", "sales_transactions", "stores.id = sales_transactions.store_id")], "3NF."),
            ("products", "Retail catalog items.", [
                ("sku", "VARCHAR(50) NOT NULL UNIQUE", "Stock keeping unit"),
                ("name", "VARCHAR(200) NOT NULL", "Product name"),
                ("category", "VARCHAR(80)", "Product category"),
                ("price", "NUMERIC(10,2) NOT NULL", "Selling price"),
                ("cost", "NUMERIC(10,2)", "Cost price"),
                ("stock_qty", "INTEGER DEFAULT 0", "On-hand quantity"),
                ("reorder_level", "INTEGER DEFAULT 0", "Restock threshold"),
            ], [_idx("idx_products_sku", "sku", True), _idx("idx_products_category", "category")], [("one-to-many", "sales_transactions", "products.id = sales_transactions.product_id")], "Price and cost are denormalized for fast reporting."),
            ("promotions", "Discount campaigns.", [
                ("name", "VARCHAR(150) NOT NULL", "Promotion name"),
                ("discount_type", "VARCHAR(20)", "Percent / fixed"),
                ("discount_value", "NUMERIC(8,2)", "Discount amount"),
                ("starts_at", "TIMESTAMPTZ", "Start time"),
                ("ends_at", "TIMESTAMPTZ", "End time"),
                ("product_id", _REF_OPT.format(t="products"), "Scoped product (null = all)"),
            ], [], [], ""),
            ("sales_transactions", "POS and online sales.", [
                ("store_id", _REF.format(t="stores"), "Selling store"),
                ("cashier_id", _REF_OPT.format(t="users"), "Serving cashier"),
                ("product_id", _REF.format(t="products"), "Sold product"),
                ("quantity", "INTEGER NOT NULL", "Sold quantity"),
                ("unit_price", "NUMERIC(10,2) NOT NULL", "Price snapshot"),
                ("total", "NUMERIC(12,2) NOT NULL", "Line total"),
                ("sold_at", "TIMESTAMPTZ DEFAULT now()", "Sale time"),
            ], [_idx("idx_sales_store_time", "store_id"), _idx("idx_sales_product", "product_id")], [], "Line items snapshot prices at sale time."),
            ("returns", "Product returns and refunds.", [
                ("sale_id", _REF.format(t="sales_transactions"), "Original sale"),
                ("quantity", "INTEGER NOT NULL", "Returned quantity"),
                ("refund_amount", "NUMERIC(10,2)", "Refund value"),
                ("reason", "VARCHAR(120)", "Return reason"),
                ("processed_at", "TIMESTAMPTZ DEFAULT now()", "Processing time"),
            ], [], [], ""),
            ("suppliers", "Product suppliers.", [
                ("name", "VARCHAR(150) NOT NULL", "Supplier name"),
                ("contact", "VARCHAR(20)", "Contact phone"),
                ("lead_time_days", "INTEGER DEFAULT 1", "Replenishment lead time"),
            ], [], [], ""),
        ],
        "modules": [
            {"name": "Catalog", "purpose": "Products and promotions", "entities": ["products", "promotions"]},
            {"name": "Sales", "purpose": "POS transactions and returns", "entities": ["sales_transactions", "returns"]},
            {"name": "Operations", "purpose": "Stores and supplier replenishment", "entities": ["stores", "suppliers"]},
        ],
        "business_rules": [
            "Stock cannot go below zero at sale time.",
            "A promotion requires a valid start and end window.",
            "Returns must reference an existing sale line.",
        ],
        "future_expansion": ["Loyalty points", "Omnichannel cart sync", "Demand forecasting", "Self-checkout"],
        "workflows": [
            {"name": "Sale at store", "description": "A product reaches the customer.", "steps": [
                "Customer selects products", "Cashier scans items", "Promotions applied",
                "Payment collected", "Stock adjusted", "Receipt issued",
            ]},
        ],
    },
    "manufacturing": {
        "label": "Manufacturing",
        "core_workflow": "Products are defined with bills of materials, raw materials are procured, work orders are scheduled on machines, quality checks gate output, and finished goods are shipped.",
        "primary_users": ["Production planners", "Shop floor operators", "Procurement", "Quality inspectors"],
        "roles": ["Planner", "Operator", "Procurement Manager", "Quality Inspector"],
        "processes": ["BOM definition", "Material procurement", "Work order scheduling", "Machine tracking", "Quality inspection", "Shipment"],
        "entities": [
            ("products", "Finished goods.", [
                ("sku", "VARCHAR(50) NOT NULL UNIQUE", "Product SKU"),
                ("name", "VARCHAR(200) NOT NULL", "Product name"),
                ("description", "TEXT", "Product description"),
                ("target_price", "NUMERIC(12,2)", "Target cost"),
            ], [_idx("idx_products_sku", "sku", True)], [("one-to-many", "work_orders", "products.id = work_orders.product_id")], "3NF."),
            ("raw_materials", "Procured input materials.", [
                ("name", "VARCHAR(150) NOT NULL", "Material name"),
                ("unit", "VARCHAR(20)", "kg / pcs / m"),
                ("stock_qty", "NUMERIC(10,2) DEFAULT 0", "On-hand quantity"),
                ("unit_cost", "NUMERIC(10,2)", "Cost per unit"),
            ], [], [], ""),
            ("bills_of_materials", "Materials required per product.", [
                ("product_id", _REF.format(t="products"), "Finished product"),
                ("material_id", _REF.format(t="raw_materials"), "Required material"),
                ("quantity", "NUMERIC(10,2) NOT NULL", "Quantity per unit"),
            ], [_idx("idx_bom_product", "product_id")], [], "Unique on (product_id, material_id)."),
            ("machines", "Production machines and state.", [
                ("name", "VARCHAR(120) NOT NULL", "Machine name"),
                ("status", "VARCHAR(20) DEFAULT 'idle'", "Idle / running / down"),
                ("capacity_per_hour", "NUMERIC(10,2)", "Production capacity"),
                ("last_maintenance", "DATE", "Last service"),
            ], [], [("one-to-many", "work_orders", "machines.id = work_orders.machine_id")], ""),
            ("work_orders", "Scheduled production runs.", [
                ("product_id", _REF.format(t="products"), "Produced product"),
                ("machine_id", _REF.format(t="machines"), "Assigned machine"),
                ("quantity", "INTEGER NOT NULL", "Order quantity"),
                ("status", "VARCHAR(20) DEFAULT 'planned'", "Planned / running / completed / rejected"),
                ("started_at", "TIMESTAMPTZ", "Start time"),
                ("finished_at", "TIMESTAMPTZ", "Completion time"),
            ], [_idx("idx_workorders_product", "product_id"), _idx("idx_workorders_machine", "machine_id")], [("one-to-many", "quality_checks", "work_orders.id = quality_checks.work_order_id")], ""),
            ("quality_checks", "Inspection results gating output.", [
                ("work_order_id", _REF.format(t="work_orders"), "Inspected order"),
                ("inspector_id", _REF.format(t="users"), "Inspecting user"),
                ("result", "VARCHAR(20) NOT NULL", "Pass / fail / rework"),
                ("notes", "TEXT", "Inspection notes"),
                ("checked_at", "TIMESTAMPTZ DEFAULT now()", "Check time"),
            ], [], [], "A work order cannot be completed without a passing quality check."),
            ("shipments", "Finished goods outbound.", [
                ("work_order_id", _REF.format(t="work_orders"), "Shipped order"),
                ("tracking_number", "VARCHAR(100)", "Carrier tracking"),
                ("shipped_at", "TIMESTAMPTZ", "Shipment time"),
                ("destination", "TEXT", "Delivery address"),
            ], [], [], ""),
        ],
        "modules": [
            {"name": "Product Definition", "purpose": "Products, materials and BOMs", "entities": ["products", "raw_materials", "bills_of_materials"]},
            {"name": "Production", "purpose": "Work orders and machine scheduling", "entities": ["work_orders", "machines"]},
            {"name": "Quality & Logistics", "purpose": "Quality checks and shipments", "entities": ["quality_checks", "shipments"]},
        ],
        "business_rules": [
            "A work order cannot start if material stock is below the BOM requirement.",
            "A work order is blocked at 'completed' until a passing quality check exists.",
            "Machines in 'down' status cannot receive new work orders.",
        ],
        "future_expansion": ["IoT machine telemetry", "Predictive maintenance", "Supplier scorecards", "Batch traceability"],
        "workflows": [
            {"name": "Production run", "description": "From BOM to shipment.", "steps": [
                "Product and BOM defined", "Materials procured", "Work order scheduled",
                "Machine runs production", "Quality inspection", "Shipment dispatched",
            ]},
        ],
    },
    "social": {
        "label": "Social Media",
        "core_workflow": "Users create profiles, post content, interact through likes and comments, follow each other, join groups and receive notifications.",
        "primary_users": ["End users", "Content creators", "Group moderators", "Admins"],
        "roles": ["User", "Creator", "Moderator", "Administrator"],
        "processes": ["Profile management", "Content publishing", "Engagement", "Following", "Group moderation", "Notification delivery"],
        "entities": [
            ("posts", "User-generated content.", [
                ("author_id", _REF.format(t="users"), "Posting author"),
                ("content", "TEXT NOT NULL", "Post body"),
                ("media_urls", "JSONB", "Attached media"),
                ("visibility", "VARCHAR(15) DEFAULT 'public'", "Public / friends / private"),
                ("created_at", "TIMESTAMPTZ DEFAULT now()", "Publish time"),
            ], [_idx("idx_posts_author_time", "author_id"), _idx("idx_posts_created", "created_at")], [
                ("one-to-many", "comments", "posts.id = comments.post_id"),
                ("one-to-many", "likes", "posts.id = likes.post_id"),
            ], "Feed queries rely on the created_at index."),
            ("comments", "Replies on posts.", [
                ("post_id", _REF.format(t="posts"), "Commented post"),
                ("author_id", _REF.format(t="users"), "Comment author"),
                ("content", "TEXT NOT NULL", "Comment text"),
                ("parent_id", _REF_OPT.format(t="comments"), "Reply parent (self-ref)"),
                ("created_at", "TIMESTAMPTZ DEFAULT now()", "Comment time"),
            ], [_idx("idx_comments_post", "post_id")], [], "Self-referencing for nested threads."),
            ("likes", "Reactions on posts.", [
                ("post_id", _REF.format(t="posts"), "Liked post"),
                ("user_id", _REF.format(t="users"), "Reacting user"),
                ("created_at", "TIMESTAMPTZ DEFAULT now()", "Reaction time"),
            ], [_idx("uq_likes", "post_id", True)], [], "Unique on (post_id, user_id) prevents duplicate reactions."),
            ("follows", "User follow relationships.", [
                ("follower_id", _REF.format(t="users"), "Following user"),
                ("followee_id", _REF.format(t="users"), "Followed user"),
                ("created_at", "TIMESTAMPTZ DEFAULT now()", "Follow time"),
            ], [_idx("uq_follows", "follower_id", True)], [], "Unique on (follower_id, followee_id); self-follows blocked."),
            ("groups", "Interest-based communities.", [
                ("name", "VARCHAR(150) NOT NULL", "Group name"),
                ("description", "TEXT", "Group description"),
                ("privacy", "VARCHAR(15) DEFAULT 'public'", "Public / private"),
                ("owner_id", _REF.format(t="users"), "Group owner"),
            ], [], [], ""),
            ("notifications", "User notification queue.", [
                ("user_id", _REF.format(t="users"), "Recipient"),
                ("type", "VARCHAR(40)", "Like / comment / follow"),
                ("payload", "JSONB", "Notification data"),
                ("read_at", "TIMESTAMPTZ", "Read time (null = unread)"),
                ("created_at", "TIMESTAMPTZ DEFAULT now()", "Creation time"),
            ], [_idx("idx_notifications_user_unread", "user_id")], [], "Unread notifications are the hot query path."),
        ],
        "modules": [
            {"name": "Content", "purpose": "Posts, comments and reactions", "entities": ["posts", "comments", "likes"]},
            {"name": "Social Graph", "purpose": "Follows and groups", "entities": ["follows", "groups"]},
            {"name": "Notifications", "purpose": "Event-driven user alerts", "entities": ["notifications"]},
        ],
        "business_rules": [
            "A user cannot follow themselves.",
            "A comment can only reply to a comment of the same post.",
            "Moderators can hide posts in their groups; hidden posts stop being served.",
        ],
        "future_expansion": ["Reels/short video", "Hashtags and search", "DMs", "Analytics dashboards"],
        "workflows": [
            {"name": "Post lifecycle", "description": "From publishing to engagement.", "steps": [
                "Author creates post", "Content moderation scan", "Post published",
                "Followers notified", "Likes and comments", "Engagement feeds update",
            ]},
        ],
    },
}

# ---------------------------------------------------------------------------
# Recipe-sourced domains (entities reuse the proven v1 table designs)
# ---------------------------------------------------------------------------

RECIPE_DOMAINS: dict[str, dict[str, Any]] = {
    "hospital": {
        "label": "Healthcare",
        "core_workflow": "Patients register, book appointments with doctors across departments, receive consultations and prescriptions, and are billed for services.",
        "primary_users": ["Patients", "Doctors", "Reception staff", "Hospital administrators"],
        "roles": ["Patient", "Doctor", "Receptionist", "Admin", "Pharmacist"],
        "processes": ["Patient registration", "Appointment scheduling", "Consultation", "Prescription", "Billing", "Record keeping"],
        "entities": None,  # sourced from recipe tables
        "modules": [
            {"name": "Patient Management", "purpose": "Registration and patient records", "entities": ["patients"]},
            {"name": "Clinical Care", "purpose": "Departments, doctors, appointments and medical records", "entities": ["departments", "doctors", "appointments", "medical_records"]},
            {"name": "Billing", "purpose": "Invoices and payments", "entities": ["billing"]},
        ],
        "business_rules": [
            "An appointment cannot double-book a doctor at the same time slot.",
            "Medical records are append-only and audit-logged.",
            "Billing requires a completed visit or consultation.",
        ],
        "future_expansion": ["E-prescriptions", "Lab and radiology modules", "Insurance claims", "Telehealth"],
        "workflows": [
            {"name": "Patient journey", "description": "From registration to billing.", "steps": [
                "Patient registers", "Appointment booked", "Doctor consults",
                "Prescription issued", "Billing completed", "Records updated",
            ]},
        ],
    },
    "food": {
        "label": "Food & Delivery",
        "core_workflow": "Customers discover restaurants, order dishes, pay, and a courier delivers while the restaurant manages the order lifecycle.",
        "primary_users": ["Customers", "Restaurant owners", "Couriers", "Admins"],
        "roles": ["Customer", "Restaurant Owner", "Courier", "Admin"],
        "processes": ["Restaurant onboarding", "Menu management", "Order placement", "Payment", "Courier dispatch", "Delivery tracking", "Reviews"],
        "entities": None,
        "modules": [
            {"name": "Restaurants", "purpose": "Restaurant profiles and menus", "entities": ["restaurants", "menu_items"]},
            {"name": "Orders", "purpose": "Order lifecycle and line items", "entities": ["orders", "order_items"]},
            {"name": "Delivery", "purpose": "Courier dispatch and tracking", "entities": ["couriers"]},
            {"name": "Community", "purpose": "Ratings and feedback", "entities": ["reviews"]},
        ],
        "business_rules": [
            "An order cannot be dispatched without payment confirmation.",
            "Menu items marked unavailable cannot be ordered.",
            "Courier rating is computed from completed deliveries only.",
        ],
        "future_expansion": ["Live geofencing", "Scheduled pre-orders", "Subscription plans", "Dark kitchens"],
        "workflows": [
            {"name": "Order fulfilment", "description": "From menu to doorstep.", "steps": [
                "Customer browses menus", "Order placed", "Payment confirmed",
                "Restaurant prepares", "Courier dispatched", "Order delivered", "Review requested",
            ]},
        ],
    },
    "ecommerce": {
        "label": "E-Commerce",
        "core_workflow": "Customers browse a categorized catalog, manage carts, place orders, pay, and track fulfilment while inventory and payments are reconciled.",
        "primary_users": ["Customers", "Merchants", "Support agents", "Admins"],
        "roles": ["Customer", "Merchant", "Support Agent", "Admin"],
        "processes": ["Catalog browsing", "Cart management", "Checkout", "Payment", "Fulfilment", "Returns"],
        "entities": None,
        "modules": [
            {"name": "Catalog", "purpose": "Products and categories", "entities": ["products", "categories"]},
            {"name": "Orders", "purpose": "Checkout and order lifecycle", "entities": ["orders", "order_items"]},
            {"name": "Inventory & Payments", "purpose": "Stock movements and payment capture", "entities": ["inventory_movements", "payments"]},
        ],
        "business_rules": [
            "Stock cannot drop below zero; order placement reserves inventory.",
            "Payment capture must precede order confirmation.",
            "Refunds must reference the original payment transaction.",
        ],
        "future_expansion": ["Wishlists", "Promotion engine", "Marketplace sellers", "Subscription products"],
        "workflows": [
            {"name": "Checkout flow", "description": "From cart to fulfilment.", "steps": [
                "Customer browses catalog", "Adds to cart", "Checks out",
                "Payment captured", "Order confirmed", "Inventory reserved", "Shipment dispatched",
            ]},
        ],
    },
    "inventory": {
        "label": "Inventory Management",
        "core_workflow": "Stock is organized by SKU and warehouse, replenished through purchase orders from suppliers, and tracked with an immutable movement ledger and alerts.",
        "primary_users": ["Warehouse staff", "Procurement teams", "Business owners"],
        "roles": ["Warehouse Operator", "Procurement Manager", "Admin"],
        "processes": ["SKU management", "Stock movement posting", "Purchase ordering", "Low-stock alerting", "Reconciliation"],
        "entities": None,
        "modules": [
            {"name": "Catalog", "purpose": "Products, SKUs and categories", "entities": ["products", "categories"]},
            {"name": "Stock Operations", "purpose": "Warehouses and the movement ledger", "entities": ["warehouses", "stock_movements"]},
            {"name": "Procurement", "purpose": "Suppliers and purchase orders", "entities": ["suppliers", "purchase_orders"]},
        ],
        "business_rules": [
            "Stock movements are immutable; corrections are new movements.",
            "A purchase order can only be marked received when quantities match.",
            "Low-stock alerts trigger when on-hand falls below reorder level.",
        ],
        "future_expansion": ["Barcode/QR scanning", "Forecasting", "Multi-warehouse transfers", "Supplier portals"],
        "workflows": [
            {"name": "Replenishment", "description": "From stock-out signal to shelf.", "steps": [
                "Low-stock alert fires", "Purchase order created", "Supplier fulfils",
                "Goods received", "Movement posted", "Stock reconciled",
            ]},
        ],
    },
    "erp": {
        "label": "Education (ERP)",
        "core_workflow": "Students enroll across departments and courses, attend classes, receive grades, and manage fees while faculty teach and administrators govern.",
        "primary_users": ["Students", "Faculty", "Administrators", "Finance staff"],
        "roles": ["Student", "Faculty", "Admin", "Finance Officer"],
        "processes": ["Admissions", "Enrollment", "Course delivery", "Attendance", "Grading", "Fee management"],
        "entities": None,
        "modules": [
            {"name": "Academic Records", "purpose": "Students, faculty, departments and courses", "entities": ["students", "faculty", "departments", "courses"]},
            {"name": "Enrollment", "purpose": "Registrations, attendance and grades", "entities": ["enrollments", "attendance"]},
            {"name": "Finance", "purpose": "Fee structure and payments", "entities": ["fees"]},
        ],
        "business_rules": [
            "A student cannot enroll twice in the same course per semester.",
            "Attendance is recorded once per enrollment per day.",
            "Fee status gates exam registration.",
        ],
        "future_expansion": ["Timetables", "Hostel management", "Placements", "Learning management"],
        "workflows": [
            {"name": "Academic term", "description": "From enrollment to results.", "steps": [
                "Student admitted", "Course enrollment", "Classes attended",
                "Grades awarded", "Fees settled", "Transcript issued",
            ]},
        ],
    },
    "chat": {
        "label": "Communication",
        "core_workflow": "Users create direct and group conversations, exchange messages and files in real time, react to messages, and track read state.",
        "primary_users": ["Consumers", "Teams", "Channel admins"],
        "roles": ["User", "Group Admin", "System Admin"],
        "processes": ["Conversation creation", "Messaging", "File sharing", "Reactions", "Read tracking", "Search"],
        "entities": None,
        "modules": [
            {"name": "Conversations", "purpose": "Direct and group threads", "entities": ["conversations", "conversation_members"]},
            {"name": "Messaging", "purpose": "Messages, reactions and read state", "entities": ["messages", "message_reactions"]},
        ],
        "business_rules": [
            "A direct conversation between two users is unique.",
            "Only conversation members can post messages.",
            "Deleting a message preserves the thread with a tombstone.",
        ],
        "future_expansion": ["Voice/video calls", "Message encryption", "AI reply suggestions", "Channels & threads"],
        "workflows": [
            {"name": "Real-time message flow", "description": "From send to delivery.", "steps": [
                "User opens conversation", "Message sent", "Server validates membership",
                "Message persisted", "Socket fan-out", "Read receipts update",
            ]},
        ],
    },
    "ai": {
        "label": "AI & Analytics",
        "core_workflow": "Users upload documents, the system queues analysis jobs, models extract insights, scores are produced, and results are stored for review and re-analysis.",
        "primary_users": ["Job seekers", "Recruiters", "Analysts", "Admins"],
        "roles": ["User", "Analyst", "Admin"],
        "processes": ["Document upload", "Processing queue", "Model inference", "Scoring", "Result review", "Re-analysis"],
        "entities": None,
        "modules": [
            {"name": "Document Ingestion", "purpose": "Uploads and processing state", "entities": ["documents"]},
            {"name": "AI Processing", "purpose": "Inference runs and structured outputs", "entities": ["analyses", "prompts"]},
        ],
        "business_rules": [
            "Files are virus-scanned before processing.",
            "An analysis cannot be overwritten; re-analysis creates a new record.",
            "Model and version are recorded per analysis for reproducibility.",
        ],
        "future_expansion": ["Batch pipelines", "Model A/B evaluation", "Feedback loops", "Data export"],
        "workflows": [
            {"name": "Analysis pipeline", "description": "From upload to insight.", "steps": [
                "User uploads document", "File validated and scanned",
                "Job queued", "Model processes", "Structured results stored", "User notified",
            ]},
        ],
    },
    "saas": {
        "label": "SaaS / Productivity",
        "core_workflow": "Teams operate in workspaces, organize work into projects and tasks, collaborate with assignments and deadlines, and track subscription plans.",
        "primary_users": ["Team members", "Workspace admins", "Billing managers"],
        "roles": ["Member", "Workspace Admin", "Owner"],
        "processes": ["Workspace setup", "Project creation", "Task management", "Assignment", "Progress tracking"],
        "entities": None,
        "modules": [
            {"name": "Workspaces", "purpose": "Tenant container and membership", "entities": ["workspaces"]},
            {"name": "Projects & Tasks", "purpose": "Work organization and assignment", "entities": ["projects", "tasks"]},
        ],
        "business_rules": [
            "Feature availability is gated by the workspace plan.",
            "Tasks cannot be assigned to users outside the workspace.",
            "Archived projects keep data but hide from active lists.",
        ],
        "future_expansion": ["Time tracking", "Automations", "Templates", "Public APIs"],
        "workflows": [
            {"name": "Work delivery", "description": "From task to completion.", "steps": [
                "Task created", "Assigned and prioritized", "Work in progress",
                "Review requested", "Task completed", "Analytics updated",
            ]},
        ],
    },
}

# ---------------------------------------------------------------------------
# Combined registry + helpers
# ---------------------------------------------------------------------------

DOMAIN_META: dict[str, dict[str, Any]] = {}
DOMAIN_META.update(RECIPE_DOMAINS)
DOMAIN_META.update(NEW_DOMAINS)
DOMAIN_META["custom"] = {
    "label": "Custom Domain",
    "core_workflow": "Users register and operate on the domain's core records, with role-scoped access and audited state transitions.",
    "primary_users": ["End users", "Managers", "Administrators"],
    "roles": ["Member", "Manager", "Administrator"],
    "processes": ["Core record management", "Workflow execution", "Reporting"],
    "entities": None,
    "modules": [
        {"name": "Core Operations", "purpose": "Primary domain records and workflows", "entities": []},
        {"name": "Reporting", "purpose": "Dashboards and exports", "entities": []},
    ],
    "business_rules": [
        "Record status changes are written to the immutable audit log.",
        "Only users with an administrative role may approve state transitions.",
    ],
    "future_expansion": ["Real-time dashboards", "Advanced analytics", "Mobile application"],
    "workflows": [
        {"name": "Core record workflow", "description": "From creation to completion.", "steps": [
            "Record created", "Details validated", "Workflow advances",
            "Record completed", "Audit log updated",
        ]},
    ],
}

DETECTION_KEYWORDS: list[tuple[str, list[str]]] = [
    ("smart_city", ["smart city", "smart-city", "city management", "municipal", "traffic", "public transport", "utility management", "utilities", "waste management", "emergency services", "citizen services", "urban", "parking", "street light", "sensor network", "transit", "iot infrastructure"]),
    ("hospital", ["hospital", "clinic", "patient", "doctor", "health", "medical", "healthcare"]),
    ("food", ["food", "restaurant", "delivery", "meal", "recipe", "cuisine", "grocery"]),
    ("ecommerce", ["ecommerce", "e-commerce", "shop", "store", "product", "cart", "marketplace", "retail online"]),
    ("startup", ["startup", "incubator", "founder", "investor", "pitch", "funding", "vc"]),
    ("agriculture", ["agriculture", "farm", "crop", "agri", "harvest", "field"]),
    ("finance", ["finance", "bank", "account", "budget", "invoice", "payment", "loan", "ledger", "fintech"]),
    ("travel", ["travel", "tour", "trip", "hotel", "flight", "booking", "destination"]),
    ("retail", ["retail", "pos", "store management", "cashier", "promotion"]),
    ("manufacturing", ["manufacturing", "factory", "production", "bom", "machine", "work order", "quality"]),
    ("social", ["social media", "social", "feed", "follow", "post", "community", "hashtag"]),
    ("inventory", ["inventory", "stock", "warehouse", "supply", "supplier", "sku"]),
    ("erp", ["erp", "college", "university", "campus", "student", "school", "education", "academic", "enrollment"]),
    ("chat", ["chat", "messaging", "conversation", "message", "realtime"]),
    ("ai", ["ai", "analyzer", "resume", "ml", "nlp", "insight", "recommendation engine", "cv", "analytics"]),
    ("saas", ["saas", "task", "todo", "project management", "workspace", "crm", "subscription"]),
]


def detect_domain(category: str, name: str, description: str, features: list[str]) -> str:
    """Classify the project idea into a business domain.

    Scored matching: the domain with the most keyword hits wins, so specific
    signals (e.g. 'college', 'student', 'erp') beat generic ones (e.g.
    'payment', 'store'). Ties fall through to the earlier entry in
    ``DETECTION_KEYWORDS``, which lists the more specific domains first.

    Returns ``"custom"`` when no known domain matches, so projects with a
    bespoke domain never inherit the entity model of a generic fallback.
    """
    blob = f"{category} {name} {description} {' '.join(features)}".lower()
    best_key = "custom"
    best_score = 0
    for key, keywords in DETECTION_KEYWORDS:
        score = sum(1 for k in keywords if k in blob)
        if score > best_score:
            best_score = score
            best_key = key
    return best_key


def domain_tables(domain_key: str) -> list[dict[str, Any]]:
    """Return the domain's entity set as full table dicts."""
    meta = DOMAIN_META.get(domain_key, DOMAIN_META["saas"])
    if meta.get("entities") is not None:
        return [expand_entity_spec(spec) for spec in meta["entities"]]
    from app.services.ai.templates import TABLE_RECIPES  # local import avoids cycle

    recipes = TABLE_RECIPES.get(domain_key, TABLE_RECIPES["saas"])
    tables = [dict(t) for t in recipes]
    for table in tables:
        table.setdefault("normalization_notes", "Designed in third normal form; columns depend only on the primary key.")
    return tables


def domain_meta(domain_key: str) -> dict[str, Any]:
    meta = dict(DOMAIN_META.get(domain_key, DOMAIN_META["saas"]))
    meta["key"] = domain_key
    meta["keywords"] = [kw for key, kws in DETECTION_KEYWORDS if key == domain_key for kw in kws]
    return meta
