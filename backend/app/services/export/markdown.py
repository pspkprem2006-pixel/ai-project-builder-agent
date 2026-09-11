"""Render a V2 blueprint dict into professional Markdown."""

from __future__ import annotations

import json
from typing import Any


def _bullet(items: list[Any] | None) -> str:
    if not items:
        return ""
    return "\n".join(
        f"- {item}" if isinstance(item, str) else f"- **{item.get('name', item.get('title', ''))}** — {_detail(item)}"
        for item in items
    )


def _detail(item: dict[str, Any]) -> str:
    for key in ("why", "explanation", "description", "detail", "reason", "mitigation", "value"):
        if item.get(key):
            return str(item[key])
    return ""


def _kv_list(items: list[Any] | None) -> str:
    if not items:
        return ""
    return "\n".join(f"- **{item.get('name', item.get('role', ''))}**: {_detail(item)}" for item in items)


def _code_block(lang: str, content: str) -> list[str]:
    return [f"```{lang}", content, "```", ""]


# ---------------------------------------------------------------------------
# Section renderers
# ---------------------------------------------------------------------------

def render_analysis(analysis: dict[str, Any]) -> str:
    lines = ["## 1. Requirements Analysis", ""]
    lines.append("### Problem Statement")
    lines.append(analysis.get("problem_statement", ""))
    lines.append("")
    lines.append("### Objectives")
    lines.append(_bullet(analysis.get("objectives")))
    lines.append("")
    lines.append("### Target Audience")
    lines.append(_bullet(analysis.get("target_audience")))
    lines.append("")
    lines.append("### Functional Requirements")
    for fr in analysis.get("functional_requirements", []):
        lines.append(
            f"- **{fr.get('id')}** · {fr.get('title')} — {fr.get('description')} "
            f"_(priority: {fr.get('priority')})_"
        )
    lines.append("")
    lines.append("### Non-Functional Requirements")
    for nfr in analysis.get("non_functional_requirements", []):
        lines.append(f"- **{nfr.get('id')}** · {nfr.get('title')} — {nfr.get('description')}")
    lines.append("")
    lines.append("### Constraints & Assumptions")
    lines.append("**Constraints:**")
    lines.append(_bullet(analysis.get("constraints")))
    lines.append("")
    lines.append("**Assumptions:**")
    lines.append(_bullet(analysis.get("assumptions")))
    lines.append("")
    lines.append("### Acceptance Criteria")
    lines.append(_bullet(analysis.get("acceptance_criteria")))
    lines.append("")
    complexity = analysis.get("complexity_score", {})
    lines.append("### Complexity Score")
    lines.append(f"- **Score**: {complexity.get('score', 'N/A')} / 100 — **{complexity.get('level', 'Medium')}**")
    lines.append(f"- **Reasoning**: {complexity.get('reasoning', '')}")
    lines.append(f"- **Estimated time**: {complexity.get('estimated_time', 'N/A')}")
    team = complexity.get("estimated_team", {})
    lines.append("- **Team**: " + ", ".join(f"{r.get('role')} ×{r.get('count')}" for r in team.get("roles", [])) + f" (total {team.get('total', 'N/A')})")
    lines.append("")
    lines.append("### Suggested Improvements")
    lines.append(_bullet(analysis.get("suggested_improvements")))
    lines.append("")
    lines.append("### Risks")
    for risk in analysis.get("risks", []):
        lines.append(
            f"- **{risk.get('risk')}** — likelihood: {risk.get('likelihood')}, impact: {risk.get('impact')}. "
            f"Mitigation: {risk.get('mitigation')}"
        )
    lines.append("")
    return "\n".join(lines)


def render_domain(domain: dict[str, Any]) -> str:
    lines = [
        "## 2. Domain Understanding",
        "",
        f"**Identified domain**: {domain.get('domain_label', '')} "
        f"(`{domain.get('identified_domain', '')}`{', custom' if domain.get('is_custom_domain') else ''})",
        "",
        f"**Reasoning**: {domain.get('domain_reasoning', '')}",
        "",
        "### Core Business Workflow",
        domain.get("core_workflow", ""),
        "",
        "### Primary Users",
        _bullet(domain.get("primary_users")),
        "",
        "### Roles",
        _bullet(domain.get("roles")),
        "",
        "### Processes",
        _bullet(domain.get("processes")),
        "",
        "### Domain Knowledge Notes",
        _bullet(domain.get("domain_knowledge_notes")),
        "",
        "### Future Expansion",
        _bullet(domain.get("future_expansion")),
        "",
    ]
    return "\n".join(lines)


def render_business_processes(processes: dict[str, Any]) -> str:
    lines = ["## 3. Business Process Modeling", "", processes.get("summary", ""), ""]
    for wf in processes.get("workflows", []):
        lines.append(f"### {wf.get('name')}")
        lines.append(f"_{wf.get('description', '')}_")
        lines.append("")
        lines.append("**Actors**: " + ", ".join(wf.get("actors", [])))
        lines.append("")
        lines.append("**Steps**:")
        for i, step in enumerate(wf.get("steps", []), start=1):
            lines.append(f"{i}. {step}")
        lines.append("")
        if wf.get("diagram"):
            lines.append("```mermaid")
            lines.append(wf["diagram"])
            lines.append("```")
            lines.append("")
    lines.append("### Business Rules")
    for rule in processes.get("business_rules", []):
        lines.append(f"- **{rule.get('rule')}** — enforced: {rule.get('where_enforced', '')}")
    lines.append("")
    lines.append("### Role Permissions")
    for perm in processes.get("role_permissions", []):
        lines.append(f"- **{perm.get('role')}**: " + ", ".join(perm.get("can", [])))
    lines.append("")
    lines.append("### Critical Processes")
    lines.append(_bullet(processes.get("critical_processes")))
    lines.append("")
    return "\n".join(lines)


def render_technology(tech: dict[str, Any]) -> str:
    lines = ["## 4. Technology Selection", "", tech.get("summary", ""), ""]
    lines.append("### Selected Stack")
    for entry in tech.get("selected_stack", []):
        lines.append(f"#### {entry.get('layer')}")
        version = f" (v{entry.get('version')})" if entry.get("version") else ""
        lines.append(f"**{entry.get('technology')}**{version}")
        lines.append("")
        lines.append(f"- **Reason**: {entry.get('reason', '')}")
        if entry.get("alternatives"):
            lines.append("- **Alternatives**: " + ", ".join(entry["alternatives"]))
        if entry.get("tradeoffs"):
            lines.append(f"- **Tradeoffs**: {entry.get('tradeoffs')}")
        lines.append("")
    lines.append("### Key Libraries")
    lines.append(_kv_list(tech.get("key_libraries")))
    lines.append("")
    lines.append("### Architecture Patterns")
    lines.append(_kv_list(tech.get("architecture_patterns")))
    lines.append("")
    lines.append("### Decision Matrix")
    for decision in tech.get("decision_matrix", []):
        lines.append(
            f"- **{decision.get('decision')}** → **{decision.get('chosen')}**. Options: "
            f"{', '.join(decision.get('options_considered', []))}. Reason: {decision.get('reason', '')}"
        )
    lines.append("")
    lines.append("### Constraints")
    lines.append(_bullet(tech.get("constraints")))
    lines.append("")
    return "\n".join(lines)


def render_architecture(architecture: dict[str, Any]) -> str:
    lines = ["## 5. Architecture", "", architecture.get("summary", ""), ""]
    lines.append("### Architectural Patterns")
    for pattern in architecture.get("patterns", []):
        lines.append(f"- **{pattern.get('pattern')}** — {pattern.get('explanation', '')}")
        if pattern.get("why_here"):
            lines.append(f"  - _Why here_: {pattern.get('why_here')}")
    lines.append("")
    diagrams = [
        ("High-Level Architecture", "high_level_architecture"),
        ("Component Diagram", "component_diagram"),
        ("Data Flow", "data_flow"),
        ("Service Communication", "service_communication"),
        ("Deployment Architecture", "deployment_architecture"),
    ]
    for title, key in diagrams:
        lines.append(f"### {title}")
        lines.extend(_code_block("mermaid", architecture.get(key, "")))
    lines.append("### Components")
    for comp in architecture.get("components", []):
        lines.append(f"- **{comp.get('name')}** ({comp.get('technology')}): {comp.get('responsibility')}")
    lines.append("")
    lines.append("### Design Decisions")
    for decision in architecture.get("design_decisions", []):
        lines.append(f"- **{decision.get('decision')}**: {decision.get('rationale', '')}")
    lines.append("")
    return "\n".join(lines)


def render_database(database: dict[str, Any]) -> str:
    lines = ["## 6. Database Design", "", database.get("summary", ""), ""]
    lines.append("### Entity Relationship Diagram")
    lines.extend(_code_block("mermaid", database.get("erd_diagram", "")))
    lines.append("### Tables")
    for table in database.get("tables", []):
        lines.append(f"#### {table.get('name')}")
        lines.append(f"_{table.get('purpose', '')}_")
        lines.append("")
        lines.append("| Column | Type | Constraints | Description |")
        lines.append("|--------|------|-------------|-------------|")
        for col in table.get("columns", []):
            lines.append(
                f"| {col.get('name')} | `{col.get('type')}` | {', '.join(col.get('constraints', []))} | {col.get('description', '')} |"
            )
        lines.append("")
        if table.get("indexes"):
            lines.append("Indexes: " + ", ".join(i.get("name", "") for i in table["indexes"]))
        if table.get("relationships"):
            lines.append(
                "Relationships: "
                + "; ".join(f"{r.get('type')} → {r.get('to_table')} ({r.get('on')})" for r in table["relationships"])
            )
        if table.get("normalization_notes"):
            lines.append(f"Normalization: _{table['normalization_notes']}_")
        lines.append("")
    sql = database.get("sql_scripts", {})
    lines.append("### SQL DDL")
    lines.extend(_code_block("sql", sql.get("create_tables", "")))
    lines.append("### Migration Scripts")
    for migration in database.get("migration_scripts", []):
        lines.append(f"- **{migration.get('file')}** — {migration.get('description')}")
    lines.append("")
    seed = database.get("seed_data", {})
    lines.append("### Seed Data")
    lines.append(f"- **{seed.get('file', '')}** — {seed.get('description', '')}")
    if seed.get("sql"):
        lines.extend(_code_block("sql", seed["sql"]))
    lines.append("### Data Integrity Rules")
    lines.append(_bullet(database.get("data_integrity_rules")))
    lines.append("")
    return "\n".join(lines)


def render_api(api: dict[str, Any]) -> str:
    lines = ["## 7. API Specification", "", api.get("summary", ""), ""]
    lines.append(f"- **Base URL**: `{api.get('base_url', '')}`")
    auth = api.get("auth", {})
    lines.append(f"- **Authentication**: {auth.get('method', '')} — {auth.get('description', '')}")
    lines.append(f"  - Flow: {auth.get('flow', '')}")
    lines.append("")
    for endpoint in api.get("endpoints", []):
        method = endpoint.get("method", "GET")
        lines.append(f"### {method} `{endpoint.get('path')}`")
        lines.append(f"_{endpoint.get('description', '')}_")
        lines.append("")
        lines.append(f"- **Authentication**: {endpoint.get('authentication', 'None')}")
        lines.append("- **Request**:")
        req = endpoint.get("request", {})
        if req:
            lines.extend(_code_block("json", json.dumps(req, indent=2)))
        lines.append("- **Response**:")
        resp = endpoint.get("response", {})
        if resp:
            lines.extend(_code_block("json", json.dumps(resp, indent=2)))
        if endpoint.get("validation_rules"):
            lines.append("- **Validation rules**:")
            for rule in endpoint["validation_rules"]:
                lines.append(f"  - {rule}")
        lines.append("- **Status codes**: " + ", ".join(f"{sc.get('code')} ({sc.get('meaning')})" for sc in endpoint.get("status_codes", [])))
        lines.append("")
    lines.append("### Business Workflow Mapping")
    for mapping in api.get("business_workflow_mapping", []):
        lines.append(f"- **{mapping.get('workflow')}**: " + ", ".join(mapping.get("endpoints", [])))
    lines.append("")
    lines.append("### Pagination")
    lines.append(api.get("pagination", ""))
    lines.append("")
    lines.append("### Error Format")
    lines.extend(_code_block("json", api.get("error_format", "")))
    return "\n".join(lines)


def render_ui_ux(ui_ux: dict[str, Any]) -> str:
    lines = ["## 8. UI/UX Plan", ""]
    lines.append("### Design Principles")
    lines.append(_bullet(ui_ux.get("design_principles")))
    lines.append("")
    lines.append("### Screens")
    for screen in ui_ux.get("screens", []):
        lines.append(
            f"- **{screen.get('name')}** (`{screen.get('route')}`) — {screen.get('purpose')}. "
            f"Components: {', '.join(screen.get('key_components', []))}"
        )
    lines.append("")
    lines.append("### Navigation Flow")
    lines.extend(_code_block("mermaid", ui_ux.get("navigation_flow", "")))
    lines.append("### Components")
    lines.append(_kv_list(ui_ux.get("components")))
    lines.append("")
    lines.append("### Forms")
    for form in ui_ux.get("forms", []):
        lines.append(
            f"- **{form.get('name')}**: "
            + ", ".join(f"{f.get('name')} ({f.get('type')}, {f.get('validation')})" for f in form.get("fields", []))
        )
    lines.append("")
    lines.append("### Dashboard Layout")
    lines.append(ui_ux.get("dashboard_layout", ""))
    lines.append("")
    lines.append("### Responsive Strategy")
    lines.append(ui_ux.get("responsive_strategy", ""))
    lines.append("")
    colors = ui_ux.get("colors", {})
    lines.append("### Color System")
    for key, value in colors.items():
        lines.append(f"- **{key}**: {value}")
    lines.append("")
    typography = ui_ux.get("typography", {})
    lines.append("### Typography")
    lines.append(f"- **Family**: {typography.get('font_family', '')}")
    lines.append(f"- **Headings**: {typography.get('headings', '')}")
    lines.append(f"- **Body**: {typography.get('body', '')}")
    lines.append("")
    lines.append("### User Journeys")
    for journey in ui_ux.get("user_journeys", []):
        lines.append(f"- **{journey.get('journey')}**: " + " → ".join(journey.get("screens", [])))
    lines.append("")
    lines.append("### Reusable UI Components")
    lines.append(_bullet(ui_ux.get("reusable_components")))
    lines.append("")
    return "\n".join(lines)


def render_roadmap(roadmap: dict[str, Any]) -> str:
    lines = ["## 9. Development Roadmap", "", roadmap.get("summary", ""), ""]
    lines.append(f"- **Total estimated hours**: {roadmap.get('total_estimated_hours', 'N/A')}")
    lines.append("")
    for milestone in roadmap.get("weekly_milestones", []):
        lines.append(f"### Week {milestone.get('week')} — {milestone.get('theme')}")
        lines.append(f"_Goal: {milestone.get('goal', '')}_")
        lines.append("")
        lines.append("| Task | Hours | Deliverable |")
        lines.append("|------|-------|-------------|")
        for task in milestone.get("tasks", []):
            lines.append(f"| {task.get('task')} | {task.get('hours')} | {task.get('deliverable')} |")
        lines.append("")
        lines.append(f"_Week total: {milestone.get('week_hours')}h_")
        lines.append("")
    lines.append("### Critical Path")
    lines.append(_bullet(roadmap.get("critical_path")))
    lines.append("")
    lines.append("### Team Plan")
    lines.append(_kv_list(roadmap.get("team_plan")))
    lines.append("")
    return "\n".join(lines)


def render_testing(testing: dict[str, Any]) -> str:
    lines = ["## 10. Testing Strategy", "", testing.get("summary", ""), ""]
    sections = [
        ("Unit Tests", "unit_tests"),
        ("Integration Tests", "integration_tests"),
        ("API Tests", "api_tests"),
        ("Security Tests", "security_tests"),
        ("Performance Tests", "performance_tests"),
        ("Edge Cases", "edge_cases"),
    ]
    for title, key in sections:
        lines.append(f"### {title}")
        for item in testing.get(key, []):
            name = item.get("name", item.get("threat", item.get("metric", "")))
            lines.append(f"- **{name}**: {item.get('scenario', item.get('flow', ''))}")
            if item.get("threshold"):
                lines[-1] += f" (threshold: {item['threshold']})"
        lines.append("")
    lines.append("### Test Data")
    lines.append(testing.get("test_data", ""))
    lines.append("")
    lines.append("### QA Checklist")
    lines.append(_bullet(testing.get("qa_checklist")))
    lines.append("")
    return "\n".join(lines)


def render_documentation(documentation: dict[str, Any]) -> str:
    lines = ["## 11. Documentation", ""]
    lines.append("### README")
    lines.extend(_code_block("markdown", documentation.get("readme", "")))
    sections = [
        ("Installation Guide", "installation_guide"),
        ("API Documentation", "api_documentation"),
        ("Architecture Documentation", "architecture_documentation"),
        ("Database Documentation", "database_documentation"),
        ("Deployment Guide", "deployment_guide"),
        ("Contribution Guide", "contribution_guide"),
    ]
    for title, key in sections:
        lines.append(f"### {title}")
        lines.append(documentation.get(key, ""))
        lines.append("")
    lines.append("### Future Improvements")
    lines.append(_bullet(documentation.get("future_improvements")))
    lines.append("")
    return "\n".join(lines)


def render_technology_evaluation(tech: dict[str, Any]) -> str:
    lines = ["## 4. Technology Evaluation", "", tech.get("summary", ""), ""]
    for cat in tech.get("categories", []):
        lines.append(f"### {cat.get('layer', '')}")
        lines.append(f"**Selected**: {cat.get('selected', '')}")
        lines.append("")
        lines.append("**Options Compared**:")
        for opt in cat.get("options", []):
            lines.append(f"- **{opt.get('technology')}** ({opt.get('type', '')}) — Strengths: {', '.join(opt.get('strengths', []))}; Weaknesses: {', '.join(opt.get('weaknesses', []))}")
        lines.append("")
        lines.append("**Ratings**:")
        for r in cat.get("ratings", []):
            lines.append(f"- {r.get('option')}: {r.get('score')}/10 — {r.get('verdict')}")
        lines.append("")
        lines.append(f"**Rationale**: {cat.get('selection_rationale', '')}")
        lines.append("")
    lines.append("### Constraints")
    lines.append(_bullet(tech.get("constraints")))
    lines.append("")
    return "\n".join(lines)


def render_design_decisions(dd: dict[str, Any]) -> str:
    lines = ["## 5. Design Decisions", "", dd.get("summary", ""), ""]
    for d in dd.get("decisions", []):
        lines.append(f"### {d.get('id', '')}: {d.get('topic', '')}")
        lines.append(f"**Decision**: {d.get('decision', '')}")
        lines.append("")
        lines.append(f"**Alternatives**: {', '.join(d.get('alternatives', []))}")
        lines.append("")
        lines.append("**Why Chosen**:")
        lines.append(_bullet(d.get("why_chosen")))
        lines.append("")
        lines.append("**Advantages**:")
        lines.append(_bullet(d.get("advantages")))
        lines.append("")
        lines.append("**Disadvantages**:")
        lines.append(_bullet(d.get("disadvantages")))
        lines.append("")
        lines.append("**Risks**:")
        for r in d.get("risks", []):
            lines.append(f"- {r.get('risk')} (likelihood: {r.get('likelihood')}, impact: {r.get('impact')}) — Mitigation: {r.get('mitigation')}")
        lines.append("")
        lines.append(f"**Final Justification**: {d.get('final_justification', '')}")
        lines.append("")
    return "\n".join(lines)


def render_tradeoffs(to: dict[str, Any]) -> str:
    lines = ["## 6. Trade-off Analysis", "", to.get("summary", ""), ""]
    for t in to.get("tradeoffs", []):
        lines.append(f"### {t.get('topic', '')}")
        lines.append(f"**Chosen**: {t.get('chosen', '')}")
        lines.append(f"**Alternative**: {t.get('alternative', '')}")
        lines.append("")
        lines.append("**Benefits**:")
        lines.append(_bullet(t.get("benefits")))
        lines.append("")
        lines.append("**Drawbacks**:")
        lines.append(_bullet(t.get("drawbacks")))
        lines.append("")
        lines.append(f"**Reason for Selection**: {t.get('reason_for_selection', '')}")
        lines.append("")
    return "\n".join(lines)


def render_security(sec: dict[str, Any]) -> str:
    lines = ["## 7. Security Review", "", sec.get("summary", ""), ""]
    lines.append(f"**Security Score**: {sec.get('security_score', 0)}/100")
    lines.append("")
    for a in sec.get("assessment", []):
        lines.append(f"### {a.get('category', '')}")
        lines.append(f"**Status**: {a.get('status', '')}")
        lines.append(f"{a.get('details', '')}")
        lines.append(f"**Recommendation**: {a.get('recommendation', '')}")
        lines.append("")
    lines.append("### OWASP Top 10")
    for o in sec.get("owasp", []):
        lines.append(f"- **{o.get('rank', '')} {o.get('name', '')}** — {o.get('status', '')}: {', '.join(o.get('controls', []))}")
    lines.append("")
    lines.append("### Privacy & GDPR")
    for g in sec.get("privacy", {}).get("gdpr", []):
        lines.append(f"- {g}")
    lines.append("")
    lines.append("### Recommendations")
    lines.append(_bullet(sec.get("recommendations")))
    lines.append("")
    return "\n".join(lines)


def render_performance(perf: dict[str, Any]) -> str:
    lines = ["## 8. Performance Review", "", perf.get("summary", ""), ""]
    lines.append(f"**Performance Score**: {perf.get('performance_score', 0)}/100")
    lines.append("")
    for c in perf.get("checklist", []):
        lines.append(f"### {c.get('area', '')}")
        lines.append(f"{c.get('recommendation', '')} — *Impact: {c.get('impact', '')}*")
        lines.append("")
    lines.append("### Expected Bottlenecks")
    for b in perf.get("bottlenecks", []):
        lines.append(f"- **{b.get('stage')}**: {b.get('cause')} → Remedy: {b.get('remedy')}")
    lines.append("")
    lines.append("### Database Tuning")
    for r in perf.get("database_tuning", {}).get("recommendations", []):
        lines.append(f"- {r}")
    lines.append("")
    return "\n".join(lines)


def render_scalability(scal: dict[str, Any]) -> str:
    lines = ["## 9. Scalability Planning", "", scal.get("summary", ""), ""]
    for s in scal.get("scenarios", []):
        lines.append(f"### Scenario {s.get('scenario')}: {s.get('scale')}")
        lines.append(f"{s.get('assumptions', '')}")
        lines.append("")
        lines.append("**Bottlenecks**:")
        lines.append(_bullet(s.get("expected_bottlenecks")))
        lines.append("")
        lines.append(f"**Strategy**: {s.get('scaling_strategy', '')}")
        lines.append(f"**Database**: {s.get('database_scaling', '')}")
        lines.append(f"**Caching**: {s.get('caching', '')}")
        lines.append(f"**CDN**: {s.get('cdn', '')}")
        lines.append(f"**Load Balancer**: {s.get('load_balancer', '')}")
        lines.append(f"**Auto-scaling**: {s.get('auto_scaling', '')}")
        lines.append(f"**Queue**: {s.get('queue_requirements', '')}")
        lines.append(f"**Microservices**: {s.get('microservices_migration', '')}")
        lines.append(f"**Infra Changes**: {s.get('infrastructure_changes', '')}")
        lines.append("")
    lines.append(f"**Approach**: {scal.get('approach', '')}")
    lines.append("")
    return "\n".join(lines)


def render_cost(cost: dict[str, Any]) -> str:
    lines = ["## 10. Cost Estimation", "", cost.get("summary", ""), ""]
    dc = cost.get("development_cost", {})
    lines.append("### Development Cost")
    lines.append(f"- **Total**: ${dc.get('estimated_total', 0):,} ({dc.get('estimated_hours', 0)} hrs)")
    lines.append("")
    for b in dc.get("breakdown", []):
        lines.append(f"- {b.get('item')}: ${b.get('amount', 0):,}")
    lines.append("")
    ic = cost.get("infrastructure_cost", {})
    lines.append("### Infrastructure Cost (Monthly)")
    lines.append(f"- **Monthly**: ${ic.get('monthly_total', 0):,}")
    for b in ic.get("breakdown", []):
        lines.append(f"- {b.get('item')}: ${b.get('amount', 0):,}/mo")
    lines.append("")
    lines.append("### AI Cost")
    ai = cost.get("ai_cost", {})
    lines.append(f"- Monthly: ${ai.get('monthly_total', 0):,}, Yearly: ${ai.get('yearly_total', 0):,}")
    lines.append("")
    lines.append("### Maintenance Cost")
    mc = cost.get("maintenance_cost", {})
    lines.append(f"- Monthly: ${mc.get('monthly_total', 0):,}")
    lines.append("")
    st = cost.get("summary_table", {})
    lines.append("### Summary")
    lines.append(f"- **One-time (Development)**: ${st.get('one_time_total', 0):,}")
    lines.append(f"- **Monthly Recurring**: ${st.get('monthly_total', 0):,}")
    lines.append(f"- **Yearly Recurring**: ${st.get('yearly_total', 0):,}")
    lines.append("")
    lines.append("### Optimization Strategies")
    lines.append(_bullet(cost.get("optimization_strategies")))
    lines.append("")
    return "\n".join(lines)


def render_risks(risks: dict[str, Any]) -> str:
    lines = ["## 11. Business Risk Analysis", "", risks.get("summary", ""), ""]
    for r in risks.get("risks", []):
        lines.append(f"### {r.get('risk', '')}")
        lines.append(f"- **Type**: {r.get('type', '')}")
        lines.append(f"- **Likelihood**: {r.get('likelihood', '')} | **Impact**: {r.get('impact', '')} | **Level**: {r.get('level', '')}")
        lines.append(f"- **Warning**: {r.get('warning', '')}")
        lines.append("- **Mitigation**:")
        lines.append(_bullet(r.get("mitigation")))
        lines.append("")
    lines.append(f"**Overall Risk Level**: {risks.get('overall_risk_level', '')} (Score: {risks.get('risk_score', 0)})")
    lines.append("")
    return "\n".join(lines)


def render_evolution(evo: dict[str, Any]) -> str:
    lines = ["## 12. Product Evolution Roadmap", "", evo.get("summary", ""), ""]
    for v in evo.get("versions", []):
        lines.append(f"### {v.get('version', '')}: {v.get('name', '')}")
        lines.append(f"**Objective**: {v.get('objective', '')}")
        lines.append("")
        lines.append("**Features**:")
        lines.append(_bullet(v.get("features")))
        lines.append("")
        lines.append("**Architecture Changes**:")
        lines.append(_bullet(v.get("architecture_changes")))
        lines.append("")
        lines.append("**Migration Requirements**:")
        lines.append(_bullet(v.get("migration_requirements")))
        lines.append("")
    lines.append(f"**Long-term Strategy**: {evo.get('long_term_strategy', '')}")
    lines.append("")
    return "\n".join(lines)


def render_adr(adr: dict[str, Any]) -> str:
    lines = ["## 13. Architecture Decision Records", "", adr.get("summary", ""), ""]
    for r in adr.get("records", []):
        lines.append(f"### {r.get('id', '')}: {r.get('title', '')}")
        lines.append(f"**Context**: {r.get('context', '')}")
        lines.append(f"**Problem**: {r.get('problem', '')}")
        lines.append(f"**Alternatives**: {', '.join(r.get('alternatives', []))}")
        lines.append(f"**Decision**: {r.get('chosen_solution', '')}")
        lines.append("")
        lines.append("**Reasoning**:")
        lines.append(_bullet(r.get("reasoning")))
        lines.append("")
        lines.append("**Consequences**:")
        lines.append("Positive:")
        lines.append(_bullet(r.get("consequences", {}).get("positive")))
        lines.append("Negative:")
        lines.append(_bullet(r.get("consequences", {}).get("negative")))
        lines.append("")
        lines.append("**Future Considerations**:")
        lines.append(_bullet(r.get("future_considerations")))
        lines.append("")
    return "\n".join(lines)


def render_validation(validation: dict[str, Any]) -> str:
    lines = ["## 14. Blueprint Quality Review", "", validation.get("overall_verdict", ""), ""]
    qr = validation.get("quality_report", {})
    if qr:
        lines.append("### Quality Scores")
        lines.append(f"- **Overall Quality**: {qr.get('overall_quality', 0)}/100")
        lines.append(f"- **Consistency**: {qr.get('consistency', 0)}/100")
        lines.append(f"- **Architecture**: {qr.get('architecture', 0)}/100")
        lines.append(f"- **Security**: {qr.get('security', 0)}/100")
        lines.append(f"- **Performance**: {qr.get('performance', 0)}/100")
        lines.append(f"- **Documentation**: {qr.get('documentation', 0)}/100")
        lines.append(f"- **Readiness**: {qr.get('readiness', '')}")
        lines.append(f"- **Confidence Score**: {qr.get('confidence_score', 0)}/100")
        lines.append(f"- **Summary**: {qr.get('summary', '')}")
        lines.append("")
    for c in validation.get("checks", []):
        icon = {"pass": "[PASS]", "warn": "[WARN]", "fail": "[FAIL]"}.get(c.get("status", ""), "[?]")
        lines.append(f"- {icon} **{c.get('area')}**: {c.get('message', '')}")
        if c.get("recommendation"):
            lines.append(f"  - *Recommendation*: {c.get('recommendation')}")
    lines.append("")
    if validation.get("gaps"):
        lines.append("### Gaps")
        for g in validation.get("gaps", []):
            lines.append(f"- **{g.get('section')}**: {g.get('gap')} — {g.get('suggestion', '')}")
        lines.append("")
    if validation.get("consistency_fixes"):
        lines.append("### Consistency Fixes Applied")
        for f in validation.get("consistency_fixes", []):
            lines.append(f"- **{f.get('section')}**: {f.get('issue')} — Fixed by: {f.get('fixed_by', '')}")
        lines.append("")
    return "\n".join(lines)


def render_deployment(deployment: dict[str, Any]) -> str:
    lines = ["## 12. Deployment & DevOps", ""]
    lines.append("### Dockerfile")
    lines.extend(_code_block("dockerfile", deployment.get("dockerfile", "")))
    lines.append("### docker-compose.yml")
    lines.extend(_code_block("yaml", deployment.get("docker_compose", "")))
    lines.append("### Environment Variables")
    lines.append("| Variable | Purpose | Secret |")
    lines.append("|----------|---------|--------|")
    for var in deployment.get("environment_variables", []):
        lines.append(f"| {var.get('name')} | {var.get('purpose')} | {'yes' if var.get('secret') else 'no'} |")
    lines.append("")
    lines.append("### GitHub Actions Workflow")
    lines.extend(_code_block("yaml", deployment.get("github_actions", "")))
    lines.append("### Production Guide")
    lines.extend(_code_block("text", deployment.get("production_guide", "")))
    lines.append("### Monitoring")
    lines.append(_kv_list(deployment.get("monitoring")))
    lines.append("")
    lines.append("### Logging Strategy")
    lines.append(deployment.get("logging_strategy", ""))
    lines.append("")
    lines.append("### CI/CD Pipeline")
    for stage in deployment.get("ci_cd_pipeline", []):
        lines.append(f"- **{stage.get('stage')}**: " + "; ".join(stage.get("actions", [])))
    lines.append("")
    return "\n".join(lines)


def render_blueprint(blueprint: dict[str, Any]) -> str:
    """Render a full V3 blueprint to Markdown."""
    header = f"# {blueprint.get('project', {}).get('name', 'Software Blueprint')}\n"
    meta = blueprint.get("metadata", {})
    header += f"\n> Generated by **AI Project Builder Agent** · provider: `{meta.get('provider', 'template')}` · {meta.get('generated_at', '')}\n\n"

    sections = [
        ("analysis", render_analysis),
        ("domain_understanding", render_domain),
        ("business_processes", render_business_processes),
        ("technology_selection", render_technology),
        ("technology_evaluation", render_technology_evaluation),
        ("design_decisions", render_design_decisions),
        ("tradeoffs", render_tradeoffs),
        ("architecture", render_architecture),
        ("database", render_database),
        ("api", render_api),
        ("ui_ux", render_ui_ux),
        ("security", render_security),
        ("performance", render_performance),
        ("scalability", render_scalability),
        ("cost_estimation", render_cost),
        ("business_risks", render_risks),
        ("roadmap", render_roadmap),
        ("product_evolution", render_evolution),
        ("adr", render_adr),
        ("testing", render_testing),
        ("documentation", render_documentation),
        ("deployment", render_deployment),
        ("validation", render_validation),
    ]
    body = []
    for key, renderer in sections:
        section = blueprint.get(key)
        if section:
            body.append(renderer(section))
    return header + "\n".join(body)
