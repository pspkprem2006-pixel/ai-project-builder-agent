"""Registry of diagram generators.

Diagrams are generated on demand from the current blueprint, so they are
always synchronized with it — there is no stored copy to go stale.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from app.services.diagrams import generators

GeneratorFn = Callable[[dict[str, Any]], str]

DIAGRAMS: dict[str, dict[str, Any]] = {
    "overview": {
        "label": "System Overview",
        "description": "End-to-end view of users, frontend, API, auth and data store.",
        "category": "architecture",
        "handler": generators.generate_overview,
    },
    "erd": {
        "label": "Entity Relationship",
        "description": "All tables, columns, keys and relationships from the database design.",
        "category": "database",
        "handler": generators.generate_erd,
    },
    "sequence": {
        "label": "API Sequence",
        "description": "Request flows between user, frontend, API, services and database.",
        "category": "api",
        "handler": generators.generate_sequence,
    },
    "class": {
        "label": "Class Diagram",
        "description": "Domain model classes with attributes and associations.",
        "category": "database",
        "handler": generators.generate_class,
    },
    "component": {
        "label": "Component Diagram",
        "description": "Client, web, API, service and data layers as components.",
        "category": "architecture",
        "handler": generators.generate_component,
    },
    "deployment": {
        "label": "Deployment Diagram",
        "description": "How the system is hosted, including the deployment platform.",
        "category": "architecture",
        "handler": generators.generate_deployment,
    },
    "c4": {
        "label": "C4 Model",
        "description": "C4 system context: users, system, containers and external hosts.",
        "category": "architecture",
        "handler": generators.generate_c4,
    },
    "flowchart": {
        "label": "Business Flowchart",
        "description": "Step-by-step flowchart of the primary business workflow.",
        "category": "business",
        "handler": generators.generate_flowchart,
    },
}


def diagram_ids() -> list[str]:
    return list(DIAGRAMS.keys())


def generate_diagram(diagram_id: str, blueprint: dict[str, Any]) -> str:
    return DIAGRAMS[diagram_id]["handler"](blueprint)
