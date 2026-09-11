"""Mermaid diagram generators.

Every generator takes the stored blueprint and returns a fresh Mermaid
source string. Because generation happens on demand, the diagrams always
mirror the current blueprint — regeneration is automatic by construction.
"""

from __future__ import annotations

from typing import Any

from app.services.codegen.base import pascal_case, singularize
from app.services.diagrams import base


def _erd_type(column: dict[str, Any]) -> str:
    raw = str(column.get("type") or "").upper()
    if "SERIAL" in raw:
        return "int"
    if "INT" in raw or "BIGINT" in raw or "SMALLINT" in raw:
        return "int"
    if "VARCHAR" in raw or "CHAR" in raw or "TEXT" in raw:
        return "varchar"
    if "TIMESTAMP" in raw or "DATE" in raw or "TIME" in raw:
        return "datetime"
    if "NUMERIC" in raw or "DECIMAL" in raw or "DOUBLE" in raw or "REAL" in raw:
        return "decimal"
    if "BOOLEAN" in raw or "BOOL" in raw:
        return "bool"
    if "UUID" in raw:
        return "uuid"
    if "JSON" in raw:
        return "json"
    if "ARRAY" in raw:
        return "array"
    return "varchar"


def _class_type(column: dict[str, Any]) -> str:
    raw = str(column.get("type") or "").upper()
    if "SERIAL" in raw:
        return "int"
    if "INT" in raw or "BIGINT" in raw or "SMALLINT" in raw:
        return "int"
    if "VARCHAR" in raw or "CHAR" in raw or "TEXT" in raw:
        return "str"
    if "TIMESTAMP" in raw or "DATE" in raw or "TIME" in raw:
        return "datetime"
    if "NUMERIC" in raw or "DECIMAL" in raw or "DOUBLE" in raw or "REAL" in raw:
        return "Decimal"
    if "BOOLEAN" in raw or "BOOL" in raw:
        return "bool"
    if "UUID" in raw:
        return "UUID"
    if "JSON" in raw:
        return "dict"
    if "ARRAY" in raw:
        return "list"
    return "str"


def _erd_entity(table: dict[str, Any]) -> str:
    name = base.node_id(str(table.get("name") or "table"))
    lines = [f"    {name.upper()} {{"]
    for column in base.columns(table):
        col_name = base.node_id(str(column.get("name") or "column"))
        type_name = _erd_type(column)
        marker = ""
        if base.is_pk(column):
            marker = " PK"
        elif base.is_fk(column):
            marker = " FK"
        lines.append(f"        {type_name} {col_name}{marker}")
    lines.append("    }")
    return "\n".join(lines)


def generate_overview(blueprint: dict[str, Any]) -> str:
    """High-level system overview diagram."""
    info = base.project_info(blueprint)
    stack_info = base.stack(blueprint)
    name = base.escape_label(info.get("name") or "Application")
    frontend = base.escape_label(stack_info.get("frontend") or "Frontend")
    backend = base.escape_label(stack_info.get("backend") or "Backend")
    database = base.escape_label(stack_info.get("database") or "Database")
    auth = base.escape_label(stack_info.get("auth") or "JWT")
    api = base.section(blueprint, "api")
    platform = base.escape_label(
        api.get("deployment_platform") or info.get("deployment_platform") or "Hosting Platform"
    )

    lines = [
        f"%% System overview for {name} — regenerated from the blueprint",
        "flowchart LR",
        '    U(["User"])',
        f'    FE["{frontend}"]',
        f'    API["Backend API ({backend})"]',
        f'    DB[("{database}")]',
        f'    AUTH["{auth} Auth"]',
        f'    HOST["{platform}"]',
        "    U -->|HTTPS| FE",
        "    FE -->|JSON over /api| API",
        "    API <-->|verify token| AUTH",
        "    API -->|queries| DB",
        "    FE -.->|static assets| HOST",
        "    API -.->|runs on| HOST",
        "    DB -.->|backed up| HOST",
    ]
    return "\n".join(lines)


def generate_erd(blueprint: dict[str, Any]) -> str:
    """Entity Relationship Diagram derived from the database section."""
    table_items = base.tables(blueprint)
    if not table_items:
        return "erDiagram\n    %% No tables found in the blueprint"

    lines = ["%% ERD — regenerated from the blueprint database section", "erDiagram"]
    for table in table_items:
        lines.append(_erd_entity(table))

    known = {base.node_id(str(t.get("name") or "")).upper() for t in table_items}
    seen: set[tuple[str, str]] = set()
    for source, target, rel_type in base.relationship_links(blueprint):
        src_id, tgt_id = base.node_id(source).upper(), base.node_id(target).upper()
        if src_id not in known or tgt_id not in known:
            continue
        if (src_id, tgt_id) in seen:
            continue
        seen.add((src_id, tgt_id))
        rel_type_lower = rel_type.lower()
        if "many-to-many" in rel_type_lower or "many to many" in rel_type_lower:
            cardinality = "}o--o{"
        elif "one-to-one" in rel_type_lower or "one to one" in rel_type_lower:
            cardinality = "||--||"
        else:
            cardinality = "||--o{"
        lines.append(f'    {src_id} {cardinality} {tgt_id} : "has"')
    return "\n".join(lines)


def generate_sequence(blueprint: dict[str, Any]) -> str:
    """Sequence diagram for the API flows described in the blueprint."""
    api = base.section(blueprint, "api")
    auth_method = base.escape_label(
        base.stack(blueprint).get("auth") or api.get("auth", {}).get("method") or "JWT"
    )
    items = base.endpoints(blueprint)
    lines = [
        "%% API sequence diagram — regenerated from the blueprint",
        "sequenceDiagram",
        "    autonumber",
        "    actor User as User",
        "    participant FE as Frontend",
        "    participant API as Backend API",
        "    participant SVC as Service Layer",
        "    participant DB as Database",
        "",
        "    User->>FE: Register / Login",
        f"    FE->>API: POST /auth/register ({auth_method})",
        "    API->>SVC: authenticate & issue token",
        "    SVC-->>API: access token",
        "    API-->>FE: 201 Created + token",
        "    FE-->>User: authenticated session",
    ]
    for _index, endpoint in enumerate(items[:10]):
        method = str(endpoint.get("method") or "GET").upper()
        path = str(endpoint.get("path") or "/")
        status = "200 OK"
        status_codes = endpoint.get("status_codes")
        if isinstance(status_codes, list) and status_codes:
            first = status_codes[0]
            if isinstance(first, dict):
                code = str(first.get("code") or "200")
                meaning = base.escape_label(first.get("meaning") or "OK", 24)
                status = f"{code} {meaning}"
        label = base.escape_label(endpoint.get("description") or path, 36)
        lines += [
            "",
            f"    FE->>API: {method} {path}",
            f"    API->>SVC: handle {method} {path}",
            f"    SVC->>DB: query for {label}",
            "    DB-->>SVC: result",
            "    SVC-->>API: processed",
            f"    API-->>FE: {status}",
        ]
    return "\n".join(lines)


def generate_class(blueprint: dict[str, Any]) -> str:
    """Class diagram derived from the blueprint database model."""
    table_items = base.tables(blueprint)
    if not table_items:
        return "classDiagram\n    %% No tables found in the blueprint"

    lines = ["%% Class diagram — regenerated from the blueprint model", "classDiagram"]
    known = {base.node_id(str(t.get("name") or "")) for t in table_items}
    for table in table_items:
        class_name = pascal_case(singularize(str(table.get("name") or "table")))
        lines.append(f"    class {class_name} {{")
        for column in base.columns(table):
            type_name = _class_type(column)
            col_name = base.node_id(str(column.get("name") or "column"))
            lines.append(f"        +{type_name} {col_name}")
        lines.append("    }")

    seen: set[tuple[str, str]] = set()
    class_names = {pascal_case(singularize(t)) for t in known}
    for source, target, _rel_type in base.relationship_links(blueprint):
        src_name = pascal_case(singularize(source))
        tgt_name = pascal_case(singularize(target))
        if src_name not in class_names or tgt_name not in class_names:
            continue
        if (src_name, tgt_name) in seen:
            continue
        seen.add((src_name, tgt_name))
        lines.append(f'    {src_name} "1" --> "0..*" {tgt_name} : has')
    return "\n".join(lines)


def generate_component(blueprint: dict[str, Any]) -> str:
    """Component diagram built from the architecture and stack sections."""
    info = base.project_info(blueprint)
    stack_info = base.stack(blueprint)
    name = base.escape_label(info.get("name") or "Application")
    frontend = base.escape_label(stack_info.get("frontend") or "Frontend")
    backend = base.escape_label(stack_info.get("backend") or "Backend")
    database = base.escape_label(stack_info.get("database") or "Database")
    components = base.components(blueprint)

    lines = [
        f"%% Component diagram for {name} — regenerated from the blueprint",
        "flowchart LR",
        '    subgraph Client["Client"]',
        '        U["User"]',
        "    end",
        '    subgraph Web["Web Layer"]',
        f'        UI["{frontend}"]',
        "    end",
        '    subgraph API["API Layer"]',
        f'        API1["{backend} REST API"]',
        "    end",
        '    subgraph Services["Service Layer"]',
    ]
    svc_ids: list[str] = []
    for index, component in enumerate(components[:8]):
        comp_name = base.escape_label(component.get("name") or f"Service {index + 1}")
        technology = component.get("technology")
        tech = f" ({base.escape_label(technology)})" if technology else ""
        svc_id = f"S{index + 1}"
        svc_ids.append(svc_id)
        lines.append(f'        {svc_id}["{comp_name}{tech}"]')
    lines.append("    end")
    lines += [
        '    subgraph Data["Data Layer"]',
        f'        DB[("{database}")]',
        "    end",
        "    U -->|HTTPS| UI",
        "    UI -->|JSON /api| API1",
    ]
    for svc_id in svc_ids:
        lines.append(f"    API1 --> {svc_id}")
        lines.append(f"    {svc_id} --> DB")
    if not svc_ids:
        lines.append("    API1 --> DB")
    return "\n".join(lines)


def generate_deployment(blueprint: dict[str, Any]) -> str:
    """Deployment diagram from the stack and deployment sections."""
    info = base.project_info(blueprint)
    stack_info = base.stack(blueprint)
    name = base.escape_label(info.get("name") or "Application")
    frontend = base.escape_label(stack_info.get("frontend") or "Frontend")
    backend = base.escape_label(stack_info.get("backend") or "Backend")
    database = base.escape_label(stack_info.get("database") or "Database")
    platform = base.escape_label(
        info.get("deployment_platform") or stack_info.get("deployment") or "Cloud Host"
    )
    deploy = base.section(blueprint, "deployment")

    lines = [
        f"%% Deployment diagram for {name} — regenerated from the blueprint",
        "flowchart TB",
        '    subgraph Internet["Internet"]',
        '        B["Browser"]',
        "    end",
        f'    subgraph Cloud["{platform}"]',
        '        subgraph AppTier["Application Tier"]',
        f'            FE["{frontend}"]',
        f'            BE["{backend}"]',
        "        end",
        '        subgraph DataTier["Data Tier"]',
        f'            DB[("{database}")]',
        "        end",
        "    end",
        "    B -->|HTTPS| FE",
        "    FE -->|REST / GraphQL| BE",
        "    BE -->|SQL| DB",
    ]
    monitoring = deploy.get("monitoring")
    if isinstance(monitoring, list) and monitoring:
        first = monitoring[0]
        tool = first.get("tool") if isinstance(first, dict) else str(first)
        if tool:
            lines.append(f'    BE -.->|telemetry| MON["{base.escape_label(tool)}"]')
    return "\n".join(lines)


def generate_c4(blueprint: dict[str, Any]) -> str:
    """C4 Context model derived from the blueprint."""
    info = base.project_info(blueprint)
    stack_info = base.stack(blueprint)
    name = base.escape_label(info.get("name") or "Application", 50)
    description = base.escape_label(info.get("description") or "A software system", 80)
    frontend = base.escape_label(stack_info.get("frontend") or "Frontend")
    backend = base.escape_label(stack_info.get("backend") or "Backend")
    database = base.escape_label(stack_info.get("database") or "Database")
    platform = base.escape_label(
        info.get("deployment_platform") or stack_info.get("deployment") or "Cloud Host"
    )

    lines = [
        f"%% C4 model for {name} — regenerated from the blueprint",
        "C4Context",
        f"title System Context for {name}",
        '    Person(user, "User", "Interacts with the application")',
        f'    System(app, "{name}", "{description}")',
        f'    Container(web, "{frontend}", "Web application", "User interface")',
        f'    Container(api, "{backend}", "Backend API", "REST API")',
        f'    ContainerDb(db, "{database}", "Relational database", "SQL")',
        f'    System_Ext(host, "{platform}", "Hosting platform")',
        '    Rel(user, web, "Uses")',
        '    Rel(web, api, "Calls — JSON /api")',
        '    Rel(api, db, "Reads / writes — SQL")',
        '    Rel(api, host, "Deploys to")',
    ]
    return "\n".join(lines)


def generate_flowchart(blueprint: dict[str, Any]) -> str:
    """Business process flowchart from the blueprint workflows."""
    workflow_items = base.workflows(blueprint)
    lines = [
        "%% Business process flowchart — regenerated from the blueprint",
        "flowchart TD",
    ]
    if not workflow_items:
        core = base.section(blueprint, "domain_understanding").get("core_workflow")
        lines.append(f'    A["{base.escape_label(core or "Core workflow")}"]')
        return "\n".join(lines)

    workflow = workflow_items[0]
    lines.append(f'    A(["Start: {base.escape_label(workflow.get("name") or "Workflow")}"])')
    steps = [s for s in (workflow.get("steps") or []) if isinstance(s, str) and s.strip()][:12]
    previous = "A"
    for index, step in enumerate(steps, start=1):
        node = f"N{index}"
        lines.append(f'    {node}["{base.escape_label(step)}"]')
        lines.append(f"    {previous} --> {node}")
        previous = node
    lines.append('    Z(["End"])')
    lines.append(f"    {previous} --> Z")
    return "\n".join(lines)
