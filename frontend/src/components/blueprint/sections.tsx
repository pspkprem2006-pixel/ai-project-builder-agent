"use client";

import { useState } from "react";
import { RefreshCw } from "lucide-react";
import { api } from "@/lib/api";
import { Mermaid } from "@/components/mermaid";
import { Badge, Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import type { Blueprint } from "@/lib/types";

type Json = Record<string, any>;

function List({ items }: { items?: any[] }) {
  if (!items || items.length === 0) return <p className="text-sm text-muted-foreground">—</p>;
  return (
    <ul className="space-y-1.5">
      {items.map((item, i) => {
        if (typeof item === "string") return <li key={i} className="text-sm">{item}</li>;
        const name =
          item.name ??
          item.title ??
          item.role ??
          item.pattern ??
          item.decision ??
          item.workflow ??
          item.tool ??
          item.journey ??
          item.area ??
          item.section ??
          item.task ??
          item.threat ??
          item.risk ??
          item.id ??
          "Item";
        const detail =
          item.why ??
          item.explanation ??
          item.description ??
          item.purpose ??
          item.rationale ??
          item.reason ??
          item.scenario ??
          item.flow ??
          item.mitigation ??
          item.gap ??
          item.suggestion ??
          item.issue ??
          item.message ??
          item.value ??
          item.what ??
          item.responsibility ??
          "";
        return (
          <li key={i} className="text-sm">
            {detail ? (
              <>
                <span className="font-medium">{name}</span>
                {item.likelihood && item.impact && (
                  <span className="text-muted-foreground"> ({item.likelihood} likelihood · {item.impact} impact)</span>
                )}
                {item.status && (
                  <Badge tone={item.status === "fail" ? "danger" : item.status === "warn" ? "warning" : "success"} className="ml-2">
                    {item.status}
                  </Badge>
                )}
                <span className="text-muted-foreground"> — {detail}</span>
              </>
            ) : (
              <span className="font-medium">{name}</span>
            )}
          </li>
        );
      })}
    </ul>
  );
}

function Diagram({ chart, title }: { chart?: string; title?: string }) {
  if (!chart) return null;
  return <Mermaid chart={chart} title={title} />;
}

function CodeBlock({ label, code }: { label?: string; code?: string }) {
  if (!code) return null;
  return (
    <div className="space-y-1.5">
      {label && <p className="text-sm font-medium">{label}</p>}
      <pre className="overflow-x-auto rounded-md bg-slate-900 p-4 text-xs leading-relaxed text-slate-100">{code}</pre>
    </div>
  );
}

function Section({ id, title, children }: { id: string; title: string; children: React.ReactNode }) {
  return (
    <Card id={id} className="scroll-mt-24">
      <CardHeader>
        <CardTitle>{title}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">{children}</CardContent>
    </Card>
  );
}

function SubHeading({ children }: { children: React.ReactNode }) {
  return <h4 className="pt-2 text-sm font-semibold uppercase tracking-wide text-muted-foreground">{children}</h4>;
}

function PillList({ items }: { items?: string[] }) {
  if (!items || items.length === 0) return null;
  return (
    <div className="flex flex-wrap gap-1.5">
      {items.map((s, i) => (
        <span key={i} className="rounded-full border bg-secondary/40 px-2.5 py-0.5 text-xs">
          {s}
        </span>
      ))}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Per-section content renderers (used by the modular workspace)       */
/* ------------------------------------------------------------------ */

export function AnalysisContent({ data }: { data: Json }) {
  const a = data;
  return (
    <div className="space-y-4">
      {a.problem_statement && (
        <>
          <SubHeading>Problem Statement</SubHeading>
          <p className="text-sm leading-relaxed">{a.problem_statement}</p>
        </>
      )}
      <SubHeading>Objectives</SubHeading>
      <List items={a.objectives} />
      <SubHeading>Target Audience</SubHeading>
      <List items={a.target_audience} />
      <SubHeading>Functional Requirements</SubHeading>
      <div className="space-y-1.5">
        {(a.functional_requirements || []).map((fr: Json, i: number) => (
          <p key={i} className="text-sm">
            <span className="font-medium">{fr.id}</span> · {fr.title}
            <span className="text-muted-foreground"> — {fr.description}</span>
            <Badge tone={fr.priority === "Must Have" ? "danger" : "info"} className="ml-2">{fr.priority}</Badge>
          </p>
        ))}
      </div>
      <SubHeading>Non-Functional Requirements</SubHeading>
      <div className="space-y-1.5">
        {(a.non_functional_requirements || []).map((nfr: Json, i: number) => (
          <p key={i} className="text-sm">
            <span className="font-medium">{nfr.id}</span> · {nfr.title}
            <span className="text-muted-foreground"> — {nfr.description}</span>
          </p>
        ))}
      </div>
      <SubHeading>Constraints</SubHeading>
      <List items={a.constraints} />
      <SubHeading>Assumptions</SubHeading>
      <List items={a.assumptions} />
      <SubHeading>Acceptance Criteria</SubHeading>
      <List items={a.acceptance_criteria} />
      {a.complexity_score && (
        <>
          <SubHeading>Complexity Score</SubHeading>
          <div className="space-y-2">
            <p className="text-sm">
              <Badge tone={a.complexity_score.level === "High" ? "danger" : a.complexity_score.level === "Medium" ? "warning" : "success"}>
                {a.complexity_score.score}/10 · {a.complexity_score.level}
              </Badge>
              <span className="ml-3 text-muted-foreground">{a.complexity_score.estimated_time}</span>
            </p>
            <p className="text-sm text-muted-foreground">{a.complexity_score.reasoning}</p>
            {a.complexity_score.estimated_team && (
              <p className="text-sm">
                <span className="font-medium">Team:</span>{" "}
                {(a.complexity_score.estimated_team.roles || []).map((r: Json) => `${r.count}× ${r.role}`).join(" · ")}
              </p>
            )}
          </div>
        </>
      )}
      <SubHeading>Suggested Improvements</SubHeading>
      <List items={a.suggested_improvements} />
      <SubHeading>Risks</SubHeading>
      <List items={a.risks} />
    </div>
  );
}

export function DomainUnderstandingContent({ data }: { data: Json }) {
  const du = data;
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <p className="text-sm font-medium">{du.domain_label || du.identified_domain}</p>
        {du.is_custom_domain && <Badge tone="warning">custom domain</Badge>}
        <Badge tone="info">{du.identified_domain}</Badge>
      </div>
      {du.domain_reasoning && <p className="text-sm text-muted-foreground">{du.domain_reasoning}</p>}
      <SubHeading>Core Workflow</SubHeading>
      <p className="text-sm leading-relaxed">{du.core_workflow}</p>
      <SubHeading>Primary Users</SubHeading>
      <List items={du.primary_users} />
      <SubHeading>Roles</SubHeading>
      <PillList items={du.roles} />
      <SubHeading>Processes</SubHeading>
      <List items={du.processes} />
      <SubHeading>Domain Knowledge</SubHeading>
      <List items={du.domain_knowledge_notes} />
      <SubHeading>Future Expansion</SubHeading>
      <List items={du.future_expansion} />
    </div>
  );
}

export function BusinessProcessesContent({ data }: { data: Json }) {
  const bp = data;
  return (
    <div className="space-y-4">
      <p className="text-sm leading-relaxed">{bp.summary}</p>
      <SubHeading>Workflows</SubHeading>
      <div className="space-y-4">
        {(bp.workflows || []).map((w: Json, i: number) => (
          <div key={i} className="rounded-lg border bg-secondary/30 p-3">
            <p className="font-medium">{w.name}</p>
            <p className="mb-2 text-xs text-muted-foreground">{w.description}</p>
            <p className="text-xs"><span className="text-muted-foreground">Actors:</span> {(w.actors || []).join(", ")}</p>
            <ol className="mt-2 list-decimal space-y-1 pl-5">
              {(w.steps || []).map((s: string, j: number) => (
                <li key={j} className="text-sm">{s}</li>
              ))}
            </ol>
            <Diagram chart={w.diagram} />
          </div>
        ))}
      </div>
      <SubHeading>Business Rules</SubHeading>
      <div className="space-y-1.5">
        {(bp.business_rules || []).map((r: Json, i: number) => (
          <p key={i} className="text-sm">
            <span className="font-medium">{r.rule}</span>
            <span className="text-muted-foreground"> — enforced at {r.where_enforced}</span>
          </p>
        ))}
      </div>
      <SubHeading>Role Permissions</SubHeading>
      <div className="space-y-1.5">
        {(bp.role_permissions || []).map((rp: Json, i: number) => (
          <p key={i} className="text-sm">
            <span className="font-medium">{rp.role}:</span>{" "}
            <span className="text-muted-foreground">{(rp.can || []).join(", ")}</span>
          </p>
        ))}
      </div>
      <SubHeading>Critical Processes</SubHeading>
      <List items={bp.critical_processes} />
    </div>
  );
}

export function TechnologySelectionContent({ data }: { data: Json }) {
  const ts = data;
  return (
    <div className="space-y-4">
      <p className="text-sm leading-relaxed">{ts.summary}</p>
      <SubHeading>Selected Stack</SubHeading>
      <div className="space-y-3">
        {(ts.selected_stack || []).map((s: Json, i: number) => (
          <div key={i} className="rounded-lg border bg-secondary/30 p-3">
            <p className="text-sm">
              <Badge tone="info" className="mr-2">{s.layer}</Badge>
              <span className="font-medium">{s.technology}</span>
              {s.version && <code className="ml-2 rounded bg-secondary px-1.5 py-0.5 text-xs">{s.version}</code>}
            </p>
            <p className="mt-1 text-sm text-muted-foreground">{s.reason}</p>
            {s.tradeoffs && <p className="text-xs text-muted-foreground">Tradeoffs: {s.tradeoffs}</p>}
            {s.alternatives?.length > 0 && <p className="text-xs text-muted-foreground">Alternatives: {s.alternatives.join(", ")}</p>}
          </div>
        ))}
      </div>
      <SubHeading>Key Libraries</SubHeading>
      <div className="space-y-1.5">
        {(ts.key_libraries || []).map((l: Json, i: number) => (
          <p key={i} className="text-sm">
            <code className="rounded bg-secondary px-1.5 py-0.5 text-xs">{l.name}</code>
            <span className="text-muted-foreground"> — {l.purpose} ({l.why})</span>
          </p>
        ))}
      </div>
      <SubHeading>Architecture Patterns</SubHeading>
      <div className="space-y-1.5">
        {(ts.architecture_patterns || []).map((p: Json, i: number) => (
          <p key={i} className="text-sm">
            <span className="font-medium">{p.name}</span>
            <span className="text-muted-foreground"> — {p.why}</span>
            {p.applied_to && <span className="text-muted-foreground"> (applied to {p.applied_to})</span>}
          </p>
        ))}
      </div>
      <SubHeading>Decision Matrix</SubHeading>
      <div className="space-y-1.5">
        {(ts.decision_matrix || []).map((d: Json, i: number) => (
          <p key={i} className="text-sm">
            <span className="font-medium">{d.decision}:</span> <span className="text-muted-foreground">{d.chosen}</span>
            <span className="text-muted-foreground"> — {d.reason}</span>
            {d.options_considered?.length > 0 && (
              <span className="text-xs text-muted-foreground"> (considered: {d.options_considered.join(", ")})</span>
            )}
          </p>
        ))}
      </div>
      <SubHeading>Constraints</SubHeading>
      <List items={ts.constraints} />
    </div>
  );
}

export function ArchitectureContent({ data }: { data: Json }) {
  const arch = data;
  return (
    <div className="space-y-4">
      <p className="text-sm leading-relaxed">{arch.summary}</p>
      <SubHeading>Patterns</SubHeading>
      <div className="space-y-1.5">
        {(arch.patterns || []).map((p: Json, i: number) => (
          <p key={i} className="text-sm">
            <span className="font-medium">{p.pattern}</span>
            <span className="text-muted-foreground"> — {p.explanation}</span>
            {p.why_here && <span className="text-xs text-muted-foreground"> (why here: {p.why_here})</span>}
          </p>
        ))}
      </div>
      <Diagram chart={arch.high_level_architecture} title="High-Level Architecture" />
      <Diagram chart={arch.component_diagram} title="Component Diagram" />
      <Diagram chart={arch.data_flow} title="Data Flow" />
      <Diagram chart={arch.service_communication} title="Service Communication" />
      <Diagram chart={arch.deployment_architecture} title="Deployment Architecture" />
      <SubHeading>Components</SubHeading>
      <div className="space-y-1.5">
        {(arch.components || []).map((c: Json, i: number) => (
          <p key={i} className="text-sm">
            <span className="font-medium">{c.name}</span>
            {c.technology && <Badge tone="info" className="ml-2">{c.technology}</Badge>}
            <span className="text-muted-foreground"> — {c.responsibility}</span>
          </p>
        ))}
      </div>
      <SubHeading>Design Decisions</SubHeading>
      <div className="space-y-1.5">
        {(arch.design_decisions || []).map((d: Json, i: number) => (
          <p key={i} className="text-sm">
            <span className="font-medium">{d.decision}</span>
            <span className="text-muted-foreground"> — {d.rationale}</span>
          </p>
        ))}
      </div>
    </div>
  );
}

export function DatabaseContent({ data }: { data: Json }) {
  const db = data;
  return (
    <div className="space-y-4">
      <p className="text-sm leading-relaxed">{db.summary}</p>
      <Diagram chart={db.erd_diagram} title="Entity Relationship Diagram" />
      <SubHeading>Tables</SubHeading>
      <div className="space-y-4">
        {(db.tables || []).map((table: Json) => (
          <div key={table.name} className="rounded-lg border bg-secondary/30 p-3">
            <p className="font-medium">{table.name}</p>
            <p className="mb-2 text-xs text-muted-foreground">{table.purpose}</p>
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead>
                  <tr className="border-b text-muted-foreground">
                    <th className="py-1 pr-3">Column</th>
                    <th className="py-1 pr-3">Type</th>
                    <th className="py-1 pr-3">Constraints</th>
                    <th className="py-1">Description</th>
                  </tr>
                </thead>
                <tbody>
                  {(table.columns || []).map((col: Json, i: number) => (
                    <tr key={i} className="border-b border-secondary">
                      <td className="py-1.5 pr-3 font-mono">{col.name}</td>
                      <td className="py-1.5 pr-3 font-mono">{col.type}</td>
                      <td className="py-1.5 pr-3">{col.constraints?.join(", ") || ""}</td>
                      <td className="py-1.5">{col.description}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {table.indexes?.length > 0 && (
              <p className="mt-2 text-xs text-muted-foreground">
                Indexes: {table.indexes.map((i: Json) => `${i.name}${i.unique ? " (unique)" : ""}`).join(", ")}
              </p>
            )}
            {table.relationships?.length > 0 && (
              <p className="text-xs text-muted-foreground">
                Relationships: {table.relationships.map((r: Json) => `${r.type} → ${r.to_table}${r.on ? ` on ${r.on}` : ""}`).join("; ")}
              </p>
            )}
            {table.normalization_notes && (
              <p className="mt-1 text-xs italic text-muted-foreground">Normalization: {table.normalization_notes}</p>
            )}
          </div>
        ))}
      </div>
      <CodeBlock label="SQL DDL" code={db.sql_scripts?.create_tables} />
      <CodeBlock label="Indexes" code={db.sql_scripts?.indexes} />
      <CodeBlock label="Constraints" code={db.sql_scripts?.constraints} />
      <SubHeading>Migration Scripts</SubHeading>
      <div className="space-y-3">
        {(db.migration_scripts || []).map((m: Json, i: number) => (
          <div key={i} className="space-y-1">
            <p className="text-sm">
              <code className="rounded bg-secondary px-1.5 py-0.5 text-xs">{m.file}</code>
              <span className="text-muted-foreground"> — {m.description}</span>
            </p>
            <CodeBlock code={m.sql} />
          </div>
        ))}
      </div>
      <CodeBlock label={`Seed Data (${db.seed_data?.file || ""})`} code={db.seed_data?.sql} />
      <SubHeading>Data Integrity Rules</SubHeading>
      <List items={db.data_integrity_rules} />
    </div>
  );
}

export function ApiContent({ data }: { data: Json }) {
  const api = data;
  return (
    <div className="space-y-4">
      <p className="text-sm leading-relaxed">{api.summary}</p>
      <p className="text-sm">
        <span className="font-medium">Base URL:</span> <code className="rounded bg-secondary px-1.5 py-0.5 text-xs">{api.base_url}</code>
        <span className="ml-4 font-medium">Auth:</span> {api.auth?.method} — {api.auth?.description}
      </p>
      {api.auth?.flow && <p className="text-xs text-muted-foreground">Flow: {api.auth.flow}</p>}
      <div className="space-y-4">
        {(api.endpoints || []).map((ep: Json, i: number) => (
          <div key={i} className="rounded-lg border bg-secondary/30 p-3">
            <p className="flex flex-wrap items-center gap-2">
              <Badge tone={ep.method === "GET" ? "info" : ep.method === "POST" ? "success" : ep.method === "DELETE" ? "danger" : "warning"}>
                {ep.method}
              </Badge>
              <code className="font-mono text-sm">{ep.path}</code>
            </p>
            <p className="mt-1 text-sm text-muted-foreground">{ep.description}</p>
            <p className="mt-1 text-xs">
              <span className="text-muted-foreground">Auth:</span> {ep.authentication}
            </p>
            {ep.validation_rules?.length > 0 && (
              <p className="mt-1 text-xs text-muted-foreground">
                Validation: {ep.validation_rules.join(" · ")}
              </p>
            )}
            <p className="mt-1 text-xs text-muted-foreground">
              Status codes: {ep.status_codes?.map((sc: Json) => `${sc.code} (${sc.meaning})`).join(" · ")}
            </p>
          </div>
        ))}
      </div>
      <p className="text-sm"><span className="font-medium">Pagination:</span> {api.pagination}</p>
      <p className="text-sm"><span className="font-medium">Error format:</span> {api.error_format}</p>
      <SubHeading>Business Workflow Mapping</SubHeading>
      <div className="space-y-1.5">
        {(api.business_workflow_mapping || []).map((m: Json, i: number) => (
          <p key={i} className="text-sm">
            <span className="font-medium">{m.workflow}:</span>{" "}
            {(m.endpoints || []).map((ep: string) => <code key={ep} className="mr-1.5 rounded bg-secondary px-1.5 py-0.5 text-xs">{ep}</code>)}
          </p>
        ))}
      </div>
    </div>
  );
}

export function UiUxContent({ data }: { data: Json }) {
  const ui = data;
  return (
    <div className="space-y-4">
      <SubHeading>Design Principles</SubHeading>
      <List items={ui.design_principles} />
      <SubHeading>Screens</SubHeading>
      <div className="space-y-1.5">
        {(ui.screens || []).map((s: Json, i: number) => (
          <p key={i} className="text-sm">
            <span className="font-medium">{s.name}</span>{" "}
            <code className="rounded bg-secondary px-1 py-0.5 text-xs">{s.route}</code>
            <span className="text-muted-foreground"> — {s.purpose}</span>
            {s.key_components?.length > 0 && (
              <span className="text-xs text-muted-foreground"> ({s.key_components.join(", ")})</span>
            )}
          </p>
        ))}
      </div>
      <Diagram chart={ui.navigation_flow} title="Navigation Flow" />
      <SubHeading>Components</SubHeading>
      <div className="space-y-1.5">
        {(ui.components || []).map((c: Json, i: number) => (
          <p key={i} className="text-sm">
            <span className="font-medium">{c.name}</span>
            <span className="text-muted-foreground"> — {c.purpose}</span>
            {c.props?.length > 0 && <span className="text-xs text-muted-foreground"> (props: {c.props.join(", ")})</span>}
          </p>
        ))}
      </div>
      <SubHeading>Forms</SubHeading>
      <div className="space-y-3">
        {(ui.forms || []).map((f: Json, i: number) => (
          <div key={i} className="rounded-lg border bg-secondary/30 p-3">
            <p className="text-sm font-medium">{f.name}</p>
            <ul className="mt-1 space-y-0.5">
              {(f.fields || []).map((fd: Json, j: number) => (
                <li key={j} className="text-xs text-muted-foreground">
                  {fd.name} ({fd.type}){fd.validation ? ` — ${fd.validation}` : ""}
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
      <SubHeading>Data Tables</SubHeading>
      <div className="space-y-1.5">
        {(ui.tables || []).map((t: Json, i: number) => (
          <p key={i} className="text-sm">
            <span className="font-medium">{t.name}</span>
            <span className="text-muted-foreground"> — {t.columns?.join(", ")}</span>
          </p>
        ))}
      </div>
      {ui.dashboard_layout && (
        <>
          <SubHeading>Dashboard Layout</SubHeading>
          <p className="text-sm leading-relaxed">{ui.dashboard_layout}</p>
        </>
      )}
      <SubHeading>Colors</SubHeading>
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-5">
        {Object.entries(ui.colors || {}).map(([key, value]) => (
          <div key={key} className="rounded-md border p-2 text-center">
            <p className="text-xs font-medium capitalize">{key}</p>
            <p className="text-[10px] text-muted-foreground">{String(value)}</p>
          </div>
        ))}
      </div>
      <p className="text-sm"><span className="font-medium">Typography:</span> {ui.typography?.font_family} — {ui.typography?.body}</p>
      <p className="text-sm"><span className="font-medium">Responsive:</span> {ui.responsive_strategy}</p>
      <SubHeading>User Journeys</SubHeading>
      <div className="space-y-1.5">
        {(ui.user_journeys || []).map((j: Json, i: number) => (
          <p key={i} className="text-sm">
            <span className="font-medium">{j.journey}:</span>{" "}
            <span className="text-muted-foreground">{(j.screens || []).join(" → ")}</span>
          </p>
        ))}
      </div>
    </div>
  );
}

export function TechnologyEvaluationContent({ data }: { data: Json }) {
  const ts_eval = data;
  if (!ts_eval || Object.keys(ts_eval).length === 0) {
    return <p className="text-sm text-muted-foreground">No technology evaluation data available.</p>;
  }
  return (
    <div className="space-y-4">
      <p className="text-sm leading-relaxed">{ts_eval.summary}</p>
      <SubHeading>Categories</SubHeading>
      <div className="space-y-4">
        {(ts_eval.categories || []).map((c: Json, i: number) => (
          <div key={i} className="rounded-lg border bg-secondary/30 p-3">
            <p className="font-medium">{c.layer}</p>
            <p className="mt-1 text-sm">
              <Badge tone="info" className="mr-2">Selected</Badge>
              <span className="font-medium">{c.selected}</span>
            </p>
            <p className="mt-1 text-sm text-muted-foreground">{c.selection_rationale}</p>
            {c.rejected_options?.length > 0 && (
              <p className="mt-1 text-xs text-muted-foreground">
                Rejected: {c.rejected_options.join(", ")}
              </p>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

export function DesignDecisionsContent({ data }: { data: Json }) {
  const dd = data;
  if (!dd || Object.keys(dd).length === 0) {
    return <p className="text-sm text-muted-foreground">No design decisions available.</p>;
  }
  return (
    <div className="space-y-4">
      <p className="text-sm leading-relaxed">{dd.summary}</p>
      <SubHeading>Decisions</SubHeading>
      <div className="space-y-4">
        {(dd.decisions || []).map((d: Json, i: number) => (
          <div key={i} className="rounded-lg border bg-secondary/30 p-3">
            <p className="font-medium">{d.id}: {d.topic}</p>
            <p className="mt-1 text-sm">
              <span className="font-medium">Decision:</span> {d.decision}
            </p>
            <p className="mt-1 text-xs text-muted-foreground">
              Alternatives: {d.alternatives?.join(", ") || "—"}
            </p>
            <p className="mt-1 text-sm text-muted-foreground">{d.why_chosen?.[0] || d.final_justification}</p>
            {d.advantages?.length > 0 && (
              <p className="mt-1 text-xs text-muted-foreground">Advantages: {d.advantages.join(", ")}</p>
            )}
            {d.disadvantages?.length > 0 && (
              <p className="mt-1 text-xs text-muted-foreground">Disadvantages: {d.disadvantages.join(", ")}</p>
            )}
            {d.risks?.length > 0 && (
              <p className="mt-1 text-xs text-muted-foreground">
                Risk: {d.risks[0].risk} ({d.risks[0].likelihood} / {d.risks[0].impact}) — {d.risks[0].mitigation}
              </p>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

export function TradeoffsContent({ data }: { data: Json }) {
  const to = data;
  if (!to || Object.keys(to).length === 0) {
    return <p className="text-sm text-muted-foreground">No trade-off analysis available.</p>;
  }
  return (
    <div className="space-y-4">
      <p className="text-sm leading-relaxed">{to.summary}</p>
      <SubHeading>Tradeoffs</SubHeading>
      <div className="space-y-3">
        {(to.tradeoffs || []).map((t: Json, i: number) => (
          <div key={i} className="rounded-lg border bg-secondary/30 p-3">
            <p className="font-medium">{t.topic}</p>
            <p className="mt-1 text-sm">
              <Badge tone="success" className="mr-2">Chosen</Badge>
              <span className="font-medium">{t.chosen}</span>
              <Badge tone="warning" className="ml-2 mr-2">vs</Badge>
              <span className="font-medium">{t.alternative}</span>
            </p>
            <p className="mt-1 text-xs text-muted-foreground">{t.reason_for_selection}</p>
            {t.benefits?.length > 0 && (
              <p className="mt-1 text-xs text-muted-foreground">Benefits: {t.benefits.join(", ")}</p>
            )}
            {t.drawbacks?.length > 0 && (
              <p className="mt-1 text-xs text-muted-foreground">Drawbacks: {t.drawbacks.join(", ")}</p>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

export function SecurityContent({ data }: { data: Json }) {
  const sec = data;
  if (!sec || Object.keys(sec).length === 0) {
    return <p className="text-sm text-muted-foreground">No security review available.</p>;
  }
  return (
    <div className="space-y-4">
      <p className="text-sm leading-relaxed">{sec.summary}</p>
      <SubHeading>Security Score</SubHeading>
      <p className="text-sm">
        <Badge tone={sec.security_score >= 90 ? "success" : sec.security_score >= 70 ? "warning" : "danger"}>
          {sec.security_score}/100
        </Badge>
      </p>
      <SubHeading>Assessment</SubHeading>
      <div className="space-y-2">
        {(sec.assessment || []).map((a: Json, i: number) => (
          <div key={i} className="rounded-lg border bg-secondary/30 p-3">
            <p className="font-medium">{a.category}</p>
            <p className="mt-1 text-sm text-muted-foreground">{a.details}</p>
            <p className="mt-1 text-xs text-muted-foreground">Recommendation: {a.recommendation}</p>
          </div>
        ))}
      </div>
      <SubHeading>OWASP Top 10</SubHeading>
      <div className="space-y-1.5">
        {(sec.owasp || []).map((o: Json, i: number) => (
          <p key={i} className="text-sm">
            <span className="font-medium">{o.rank} {o.name}</span> — {o.status}
            <span className="text-xs text-muted-foreground"> ({o.controls?.join(", ")})</span>
          </p>
        ))}
      </div>
    </div>
  );
}

export function PerformanceContent({ data }: { data: Json }) {
  const perf = data;
  if (!perf || Object.keys(perf).length === 0) {
    return <p className="text-sm text-muted-foreground">No performance review available.</p>;
  }
  return (
    <div className="space-y-4">
      <p className="text-sm leading-relaxed">{perf.summary}</p>
      <SubHeading>Performance Score</SubHeading>
      <p className="text-sm">
        <Badge tone={perf.performance_score >= 90 ? "success" : perf.performance_score >= 70 ? "warning" : "danger"}>
          {perf.performance_score}/100
        </Badge>
      </p>
      <SubHeading>Checklist</SubHeading>
      <div className="space-y-2">
        {(perf.checklist || []).map((c: Json, i: number) => (
          <div key={i} className="rounded-lg border bg-secondary/30 p-3">
            <p className="font-medium">{c.area}</p>
            <p className="mt-1 text-sm text-muted-foreground">{c.recommendation}</p>
            <Badge tone={c.impact === "High" ? "danger" : c.impact === "Medium" ? "warning" : "info"} className="mt-1">
              {c.impact} impact
            </Badge>
          </div>
        ))}
      </div>
      <SubHeading>Expected Bottlenecks</SubHeading>
      <div className="space-y-1.5">
        {(perf.bottlenecks || []).map((b: Json, i: number) => (
          <p key={i} className="text-sm">
            <span className="font-medium">{b.stage}</span>: {b.cause} → {b.remedy}
          </p>
        ))}
      </div>
    </div>
  );
}

export function ScalabilityContent({ data }: { data: Json }) {
  const scal = data;
  if (!scal || Object.keys(scal).length === 0) {
    return <p className="text-sm text-muted-foreground">No scalability planning available.</p>;
  }
  return (
    <div className="space-y-4">
      <p className="text-sm leading-relaxed">{scal.summary}</p>
      <SubHeading>Scenarios</SubHeading>
      <div className="space-y-4">
        {(scal.scenarios || []).map((s: Json, i: number) => (
          <div key={i} className="rounded-lg border bg-secondary/30 p-3">
            <p className="font-medium">Scenario {s.scenario}: {s.scale}</p>
            <p className="mt-1 text-xs text-muted-foreground">{s.assumptions}</p>
            <p className="mt-1 text-xs text-muted-foreground"><span className="font-medium">Bottlenecks:</span> {s.expected_bottlenecks?.join(", ")}</p>
            <p className="mt-1 text-xs text-muted-foreground"><span className="font-medium">Strategy:</span> {s.scaling_strategy}</p>
            <p className="mt-1 text-xs text-muted-foreground"><span className="font-medium">DB:</span> {s.database_scaling} | <span className="font-medium">Cache:</span> {s.caching} | <span className="font-medium">CDN:</span> {s.cdn}</p>
          </div>
        ))}
      </div>
      <p className="text-sm text-muted-foreground">{scal.approach}</p>
    </div>
  );
}

export function CostEstimationContent({ data }: { data: Json }) {
  const cost = data;
  if (!cost || Object.keys(cost).length === 0) {
    return <p className="text-sm text-muted-foreground">No cost estimation available.</p>;
  }
  return (
    <div className="space-y-4">
      <p className="text-sm leading-relaxed">{cost.summary}</p>
      <SubHeading>Development Cost</SubHeading>
      <p className="text-sm">Total: ${cost.development_cost?.estimated_total?.toLocaleString()} ({cost.development_cost?.estimated_hours} hrs)</p>
      <SubHeading>Monthly Recurring</SubHeading>
      <p className="text-sm">Infrastructure: ${cost.infrastructure_cost?.monthly_total}/mo | AI: ${cost.ai_cost?.monthly_total}/mo | Maintenance: ${cost.maintenance_cost?.monthly_total}/mo</p>
      <SubHeading>Summary</SubHeading>
      <p className="text-sm">One-time: ${cost.summary_table?.one_time_total?.toLocaleString()} | Monthly: ${cost.summary_table?.monthly_total?.toLocaleString()} | Yearly: ${cost.summary_table?.yearly_total?.toLocaleString()}</p>
      <SubHeading>Optimization Strategies</SubHeading>
      <List items={cost.optimization_strategies} />
    </div>
  );
}

export function BusinessRisksContent({ data }: { data: Json }) {
  const br = data;
  if (!br || Object.keys(br).length === 0) {
    return <p className="text-sm text-muted-foreground">No business risk analysis available.</p>;
  }
  return (
    <div className="space-y-4">
      <p className="text-sm leading-relaxed">{br.summary}</p>
      <SubHeading>Risks</SubHeading>
      <div className="space-y-3">
        {(br.risks || []).map((r: Json, i: number) => (
          <div key={i} className="rounded-lg border bg-secondary/30 p-3">
            <p className="font-medium">{r.risk} ({r.type})</p>
            <p className="mt-1 text-sm">
              <Badge tone={r.level === "High" ? "danger" : r.level === "Medium" ? "warning" : "info"}>{r.level}</Badge>
              <span className="ml-2 text-muted-foreground">Likelihood: {r.likelihood} | Impact: {r.impact}</span>
            </p>
            <p className="mt-1 text-xs text-muted-foreground">{r.warning}</p>
            <p className="mt-1 text-xs text-muted-foreground">Mitigation: {r.mitigation?.join(", ")}</p>
          </div>
        ))}
      </div>
      <p className="text-sm">Overall: {br.overall_risk_level} (Score: {br.risk_score})</p>
    </div>
  );
}

export function RoadmapContent({ data }: { data: Json }) {
  const roadmap = data;
  return (
    <div className="space-y-4">
      <p className="text-sm leading-relaxed">{roadmap.summary}</p>
      <p className="text-sm">
        <span className="font-medium">Total estimated hours:</span> {roadmap.total_estimated_hours}
      </p>
      <div className="space-y-4">
        {(roadmap.weekly_milestones || []).map((m: Json) => (
          <div key={m.week} className="rounded-lg border bg-secondary/30 p-3">
            <p className="font-medium">
              Week {m.week} — {m.theme}
            </p>
            <p className="mb-2 text-xs text-muted-foreground">{m.goal}</p>
            <ul className="space-y-1">
              {(m.tasks || []).map((t: Json, i: number) => (
                <li key={i} className="flex items-center justify-between text-sm">
                  <span>{t.task}</span>
                  <span className="text-xs text-muted-foreground">{t.hours}h</span>
                </li>
              ))}
            </ul>
            <p className="mt-2 text-xs font-medium">Week total: {m.week_hours}h</p>
          </div>
        ))}
      </div>
      <SubHeading>Critical Path</SubHeading>
      <List items={roadmap.critical_path} />
      <SubHeading>Team Plan</SubHeading>
      <div className="space-y-1.5">
        {(roadmap.team_plan || []).map((t: Json, i: number) => (
          <p key={i} className="text-sm">
            <span className="font-medium">{t.role}</span>
            <span className="text-muted-foreground"> — {t.focus}</span>
          </p>
        ))}
      </div>
    </div>
  );
}

export function ProductEvolutionContent({ data }: { data: Json }) {
  const evolution = data;
  if (!evolution || Object.keys(evolution).length === 0) {
    return <p className="text-sm text-muted-foreground">No product evolution roadmap available.</p>;
  }
  return (
    <div className="space-y-4">
      <p className="text-sm leading-relaxed">{evolution.summary}</p>
      <p className="text-sm">
        <span className="font-medium">Current phase:</span> <Badge tone="info">{evolution.current_phase}</Badge>
      </p>
      <SubHeading>Versions</SubHeading>
      <div className="space-y-4">
        {(evolution.versions || []).map((v: Json, i: number) => (
          <div key={i} className="rounded-lg border bg-secondary/30 p-3">
            <p className="font-medium">{v.version} — {v.name}</p>
            <p className="mt-1 text-sm text-muted-foreground">{v.objective}</p>
            <p className="mt-1 text-xs text-muted-foreground"><span className="font-medium">Features:</span> {v.features?.join(" · ")}</p>
            <p className="mt-1 text-xs text-muted-foreground"><span className="font-medium">Architecture changes:</span> {v.architecture_changes?.join(" · ")}</p>
            <p className="mt-1 text-xs text-muted-foreground"><span className="font-medium">Migration:</span> {v.migration_requirements?.join(" · ")}</p>
          </div>
        ))}
      </div>
      <SubHeading>Long-Term Strategy</SubHeading>
      <p className="text-sm leading-relaxed">{evolution.long_term_strategy}</p>
    </div>
  );
}

export function AdrContent({ data }: { data: Json }) {
  const adr = data;
  if (!adr || Object.keys(adr).length === 0) {
    return <p className="text-sm text-muted-foreground">No architecture decision records available.</p>;
  }
  return (
    <div className="space-y-4">
      <p className="text-sm leading-relaxed">{adr.summary}</p>
      <SubHeading>Records</SubHeading>
      <div className="space-y-4">
        {(adr.records || []).map((r: Json, i: number) => (
          <div key={i} className="rounded-lg border bg-secondary/30 p-3">
            <p className="font-medium">{r.id} — {r.title}</p>
            <p className="mt-1 text-sm text-muted-foreground">{r.context}</p>
            <p className="mt-1 text-xs text-muted-foreground"><span className="font-medium">Problem:</span> {r.problem}</p>
            <p className="mt-1 text-xs text-muted-foreground">
              <span className="font-medium">Alternatives:</span> {r.alternatives?.join(", ") || "—"}
            </p>
            <p className="mt-1 text-xs">
              <span className="font-medium">Chosen:</span> <Badge tone="success" className="ml-1">{r.chosen_solution}</Badge>
            </p>
            <p className="mt-1 text-xs text-muted-foreground"><span className="font-medium">Reasoning:</span> {r.reasoning?.join("; ") || r.reasoning}</p>
            {r.consequences && (
              <div className="mt-1 text-xs text-muted-foreground">
                <p><span className="font-medium">Positive:</span> {r.consequences.positive?.join(", ") || "—"}</p>
                <p><span className="font-medium">Negative:</span> {r.consequences.negative?.join(", ") || "—"}</p>
              </div>
            )}
            {r.future_considerations?.length > 0 && (
              <p className="mt-1 text-xs text-muted-foreground"><span className="font-medium">Future:</span> {r.future_considerations.join(" · ")}</p>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

export function TestingContent({ data }: { data: Json }) {
  const testing = data;
  return (
    <div className="space-y-4">
      <p className="text-sm leading-relaxed">{testing.summary}</p>
      {[
        ["Unit Tests", testing.unit_tests],
        ["Integration Tests", testing.integration_tests],
        ["API Tests", testing.api_tests],
        ["Security Tests", testing.security_tests],
        ["Performance Tests", testing.performance_tests],
        ["Edge Cases", testing.edge_cases],
      ].map(([title, items]: any[]) => (
        <div key={title}>
          <SubHeading>{title}</SubHeading>
          <List items={items} />
        </div>
      ))}
      <SubHeading>Test Data</SubHeading>
      <p className="text-sm leading-relaxed whitespace-pre-wrap">{testing.test_data}</p>
      <SubHeading>QA Checklist</SubHeading>
      <List items={testing.qa_checklist} />
    </div>
  );
}

export function DocumentationContent({ data }: { data: Json }) {
  const docs = data;
  return (
    <div className="space-y-4">
      <SubHeading>README</SubHeading>
      <pre className="overflow-x-auto rounded-md bg-secondary/50 p-4 text-xs leading-relaxed">{docs.readme}</pre>
      {[
        ["Installation Guide", docs.installation_guide],
        ["API Documentation", docs.api_documentation],
        ["Architecture Documentation", docs.architecture_documentation],
        ["Database Documentation", docs.database_documentation],
        ["Deployment Guide", docs.deployment_guide],
        ["Contribution Guide", docs.contribution_guide],
      ].map(([title, content]: any[]) => (
        <div key={title}>
          <SubHeading>{title}</SubHeading>
          <p className="text-sm leading-relaxed whitespace-pre-wrap">{content}</p>
        </div>
      ))}
      <SubHeading>Future Improvements</SubHeading>
      <List items={docs.future_improvements} />
    </div>
  );
}

function SemanticConsistencyBlock({ validation }: { validation: Json }) {
  const semantic = (validation.semantic_consistency || {}) as Json;
  const score = (validation.quality_report || {}).semantic_consistency_score ?? semantic.semantic_score;
  if (score === undefined && semantic.skipped !== true) return null;
  const report = (semantic.report || []) as Json[];
  const failed = report.filter((r: Json) => r.status === "FAIL");

  return (
    <div className="rounded-lg border bg-secondary/30 p-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-xs font-medium">Semantic consistency</span>
        {score !== undefined ? (
          <Badge tone={Number(score) >= 90 ? "success" : Number(score) >= 70 ? "warning" : "danger"} className="text-sm">
            {score}/100
          </Badge>
        ) : (
          <Badge tone="warning">skipped</Badge>
        )}
        {semantic.overall && <span className="text-xs text-muted-foreground">{semantic.overall}</span>}
        {validation.semantic_regenerated && (
          <Badge tone="info">regenerated: {(validation.semantic_regenerated as string[]).join(", ")}</Badge>
        )}
      </div>
      {failed.length > 0 && (
        <div className="mt-2 space-y-1.5">
          {failed.map((r: Json, i: number) => (
            <p key={i} className="text-sm">
              <Badge tone="danger" className="mr-2">FAIL</Badge>
              <span className="font-medium">{r.label}</span>
              <span className="text-muted-foreground"> — {r.reason}</span>
            </p>
          ))}
        </div>
      )}
      {semantic.skipped === true && (
        <p className="mt-2 text-xs text-muted-foreground">
          No Domain Context recorded for this blueprint, so the cross-domain vocabulary scan was skipped.
        </p>
      )}
    </div>
  );
}

export function ValidationContent({ data }: { data: Json }) {
  const validation = data;
  const [regenerating, setRegenerating] = useState<string | null>(null);
  const report = (validation.quality_report || {}) as Json;

  const regenerate = async (section: string) => {
    setRegenerating(section);
    try {
      const idMatch = window.location.pathname.match(/\/projects\/(\d+)/);
      const projectId = idMatch ? Number(idMatch[1]) : null;
      if (!projectId) throw new Error("Project id not found");
      await api.post(`/projects/${projectId}/regenerate-section`, { section });
      window.dispatchEvent(new Event("blueprint-refresh"));
    } catch (err) {
      alert(`Regeneration failed: ${err instanceof Error ? err.message : "unknown error"}`);
    } finally {
      setRegenerating(null);
    }
  };

  const scoreTone = (score: number) =>
    score >= 90 ? "success" : score >= 70 ? "warning" : ("danger" as "success" | "warning" | "danger");

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <p className="text-sm">{validation.overall_verdict}</p>
        <Badge tone={validation.passed ? "success" : "danger"}>
          {validation.passed ? "Passed" : "Failed"}
        </Badge>
      </div>
      {report.overall_quality !== undefined && (
        <div className="flex flex-wrap items-center gap-4 rounded-lg border bg-secondary/30 p-3">
          <div className="flex items-center gap-2">
            <span className="text-xs text-muted-foreground">Overall quality</span>
            <Badge tone={scoreTone(Number(report.overall_quality))} className="text-sm">
              {report.overall_quality}/100
            </Badge>
          </div>
          {report.production_readiness_score !== undefined && (
            <div className="flex items-center gap-2">
              <span className="text-xs text-muted-foreground">Production readiness</span>
              <Badge tone={scoreTone(Number(report.production_readiness_score))} className="text-sm">
                {report.production_readiness_score}/100
              </Badge>
            </div>
          )}
          {report.readiness && <Badge tone="info">{String(report.readiness)}</Badge>}
          {report.summary && <span className="text-xs text-muted-foreground">{report.summary}</span>}
        </div>
      )}
      <SemanticConsistencyBlock validation={validation} />
      <SubHeading>Checks</SubHeading>
      <div className="space-y-2">
        {(validation.checks || []).map((c: Json, i: number) => (
          <div key={i} className="rounded-lg border bg-secondary/30 p-3">
            <p className="text-sm">
              <Badge tone={c.status === "fail" ? "danger" : c.status === "warn" ? "warning" : "success"} className="mr-2">
                {c.status}
              </Badge>
              <span className="font-medium">{c.area}</span>
            </p>
            <p className="mt-1 text-sm text-muted-foreground">{c.message}</p>
            {c.recommendation && <p className="text-xs text-muted-foreground">Recommendation: {c.recommendation}</p>}
          </div>
        ))}
      </div>
      <SubHeading>Gaps</SubHeading>
      <div className="space-y-1.5">
        {(validation.gaps || []).map((g: Json, i: number) => (
          <p key={i} className="text-sm">
            <span className="font-medium">{g.section}:</span> <span className="text-muted-foreground">{g.gap}</span>
            {g.suggestion && <span className="text-xs text-muted-foreground"> → {g.suggestion}</span>}
          </p>
        ))}
      </div>
      <SubHeading>Consistency Fixes</SubHeading>
      <div className="space-y-1.5">
        {(validation.consistency_fixes || []).map((f: Json, i: number) => (
          <div key={i} className="flex flex-wrap items-center justify-between gap-2 rounded-lg border bg-secondary/30 p-2.5">
            <p className="text-sm">
              <span className="font-medium">{f.section}:</span> <span className="text-muted-foreground">{f.issue}</span>
              {f.fixed_by && <span className="text-xs text-muted-foreground"> — fixed by {f.fixed_by}</span>}
            </p>
            <Button
              size="sm"
              variant="outline"
              disabled={regenerating !== null}
              loading={regenerating === f.section}
              onClick={() => regenerate(String(f.section))}
            >
              <RefreshCw className="h-3.5 w-3.5" /> Regenerate {String(f.section)}
            </Button>
          </div>
        ))}
      </div>
    </div>
  );
}

export function DeploymentContent({ data }: { data: Json }) {
  const deploy = data;
  return (
    <div className="space-y-4">
      <CodeBlock label="Dockerfile" code={deploy.dockerfile} />
      <CodeBlock label="docker-compose.yml" code={deploy.docker_compose} />
      <CodeBlock label="GitHub Actions" code={deploy.github_actions} />
      <SubHeading>Environment Variables</SubHeading>
      <div className="space-y-1">
        {(deploy.environment_variables || []).map((v: Json, i: number) => (
          <p key={i} className="text-sm">
            <code className="rounded bg-secondary px-1.5 py-0.5 text-xs">{v.name}</code>
            <span className="text-muted-foreground"> — {v.purpose}</span>
            {v.secret && <Badge tone="danger" className="ml-2">secret</Badge>}
          </p>
        ))}
      </div>
      <SubHeading>Production Guide</SubHeading>
      <pre className="overflow-x-auto rounded-md bg-secondary/50 p-4 text-xs leading-relaxed">{deploy.production_guide}</pre>
      <SubHeading>Monitoring</SubHeading>
      <List items={deploy.monitoring} />
      <p className="text-sm"><span className="font-medium">Logging:</span> {deploy.logging_strategy}</p>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Renderer registry — maps blueprint section keys to content          */
/* ------------------------------------------------------------------ */

export const SECTION_CONTENT_RENDERERS: Record<string, (data: Json) => React.ReactNode> = {
  analysis: (d) => <AnalysisContent data={d} />,
  domain_understanding: (d) => <DomainUnderstandingContent data={d} />,
  business_processes: (d) => <BusinessProcessesContent data={d} />,
  technology_selection: (d) => <TechnologySelectionContent data={d} />,
  technology_evaluation: (d) => <TechnologyEvaluationContent data={d} />,
  design_decisions: (d) => <DesignDecisionsContent data={d} />,
  tradeoffs: (d) => <TradeoffsContent data={d} />,
  architecture: (d) => <ArchitectureContent data={d} />,
  database: (d) => <DatabaseContent data={d} />,
  api: (d) => <ApiContent data={d} />,
  ui_ux: (d) => <UiUxContent data={d} />,
  security: (d) => <SecurityContent data={d} />,
  performance: (d) => <PerformanceContent data={d} />,
  scalability: (d) => <ScalabilityContent data={d} />,
  cost_estimation: (d) => <CostEstimationContent data={d} />,
  business_risks: (d) => <BusinessRisksContent data={d} />,
  roadmap: (d) => <RoadmapContent data={d} />,
  product_evolution: (d) => <ProductEvolutionContent data={d} />,
  adr: (d) => <AdrContent data={d} />,
  testing: (d) => <TestingContent data={d} />,
  documentation: (d) => <DocumentationContent data={d} />,
  validation: (d) => <ValidationContent data={d} />,
  deployment: (d) => <DeploymentContent data={d} />,
};

/* ------------------------------------------------------------------ */
/* Legacy full-page view (kept for reference / long-doc export)        */
/* ------------------------------------------------------------------ */

export function BlueprintView({ blueprint }: { blueprint: Blueprint }) {
  const a = blueprint.analysis as Json;
  const du = blueprint.domain_understanding as Json;
  const bp = blueprint.business_processes as Json;
  const ts = blueprint.technology_selection as Json;
  const ts_eval = blueprint.technology_evaluation as Json;
  const dd = blueprint.design_decisions as Json;
  const to = blueprint.tradeoffs as Json;
  const arch = blueprint.architecture as Json;
  const db = blueprint.database as Json;
  const api = blueprint.api as Json;
  const ui = blueprint.ui_ux as Json;
  const sec = blueprint.security as Json;
  const perf = blueprint.performance as Json;
  const scal = blueprint.scalability as Json;
  const cost = blueprint.cost_estimation as Json;
  const br = blueprint.business_risks as Json;
  const roadmap = blueprint.roadmap as Json;
  const evolution = blueprint.product_evolution as Json;
  const adr = blueprint.adr as Json;
  const testing = blueprint.testing as Json;
  const docs = blueprint.documentation as Json;
  const validation = blueprint.validation as Json;
  const deploy = blueprint.deployment as Json;

  return (
    <div className="space-y-5">
      <Section id="analysis" title="1 · Requirements Analysis">
        <AnalysisContent data={a} />
      </Section>

      <Section id="domain" title="2 · Domain Understanding">
        <DomainUnderstandingContent data={du} />
      </Section>

      <Section id="processes" title="3 · Business Process Modeling">
        <BusinessProcessesContent data={bp} />
      </Section>

      <Section id="tech" title="4 · Technology Selection">
        <TechnologySelectionContent data={ts} />
      </Section>

      <Section id="architecture" title="5 · Architecture">
        <ArchitectureContent data={arch} />
      </Section>

      <Section id="database" title="6 · Database Design">
        <DatabaseContent data={db} />
      </Section>

      <Section id="api" title="7 · API Specification">
        <ApiContent data={api} />
      </Section>

      <Section id="uiux" title="8 · UI/UX Plan">
        <UiUxContent data={ui} />
      </Section>

      <Section id="tech_eval" title="9 · Technology Evaluation">
        <TechnologyEvaluationContent data={ts_eval} />
      </Section>

      <Section id="design" title="10 · Design Decisions">
        <DesignDecisionsContent data={dd} />
      </Section>

      <Section id="tradeoffs" title="11 · Trade-off Analysis">
        <TradeoffsContent data={to} />
      </Section>

      <Section id="security" title="12 · Security Review">
        <SecurityContent data={sec} />
      </Section>

      <Section id="performance" title="13 · Performance Review">
        <PerformanceContent data={perf} />
      </Section>

      <Section id="scalability" title="14 · Scalability Planning">
        <ScalabilityContent data={scal} />
      </Section>

      <Section id="cost" title="15 · Cost Estimation">
        <CostEstimationContent data={cost} />
      </Section>

      <Section id="risks" title="16 · Business Risk Analysis">
        <BusinessRisksContent data={br} />
      </Section>

      <Section id="roadmap" title="17 · Development Roadmap">
        <RoadmapContent data={roadmap} />
      </Section>

      <Section id="evolution" title="18 · Product Evolution">
        <ProductEvolutionContent data={evolution} />
      </Section>

      <Section id="adr" title="19 · Architecture Decision Records">
        <AdrContent data={adr} />
      </Section>

      <Section id="testing" title="20 · Testing Strategy">
        <TestingContent data={testing} />
      </Section>

      <Section id="docs" title="21 · Documentation">
        <DocumentationContent data={docs} />
      </Section>

      <Section id="validation" title="22 · Cross-Validation">
        <ValidationContent data={validation} />
      </Section>

      <Section id="deployment" title="23 · Deployment & DevOps">
        <DeploymentContent data={deploy} />
      </Section>
    </div>
  );
}
