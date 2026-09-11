"use client";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/card";
import { Loader2 } from "lucide-react";

type SectionKey =
  | "database"
  | "api"
  | "architecture"
  | "ui_ux"
  | "roadmap"
  | "security"
  | "performance"
  | "scalability"
  | "cost_estimation"
  | "business_risks"
  | "design_decisions"
  | "tradeoffs"
  | "technology_evaluation"
  | "product_evolution"
  | "adr"
  | "testing"
  | "documentation"
  | "deployment"
  | "validation"
  | "analysis"
  | "domain_understanding"
  | "business_processes"
  | "technology_selection";

interface AIAction {
  id: string;
  label: string;
  description: string;
  icon?: React.ReactNode;
}

interface SectionActions {
  [key: string]: AIAction[];
}

const SECTION_ACTIONS: SectionActions = {
  database: [
    { id: "explain", label: "Explain this section", description: "Get a plain-language summary of the database design" },
    { id: "sql", label: "Generate SQL", description: "Produce CREATE TABLE statements for the schema" },
    { id: "prisma", label: "Generate Prisma Schema", description: "Create a Prisma schema from the ERD" },
    { id: "sqlalchemy", label: "Generate SQLAlchemy Models", description: "Create SQLAlchemy 2.0 models with relationships" },
  ],
  api: [
    { id: "explain", label: "Explain APIs", description: "Summarize endpoints, auth, and workflows" },
    { id: "fastapi", label: "Generate FastAPI", description: "Create FastAPI routes with Pydantic models" },
    { id: "express", label: "Generate Express.js", description: "Create Express routes with Zod validation" },
    { id: "spring", label: "Generate Spring Boot", description: "Create Spring Boot controllers and DTOs" },
  ],
  architecture: [
    { id: "explain", label: "Explain Design", description: "Walk through patterns, components, and data flows" },
    { id: "mermaid", label: "Generate Mermaid", description: "Produce Mermaid diagrams for all architecture views" },
    { id: "drawio", label: "Generate Draw.io", description: "Export architecture as Draw.io XML" },
    { id: "c4", label: "Generate C4 Diagram", description: "Create C4 context/container/component diagrams" },
  ],
  ui_ux: [
    { id: "explain", label: "Explain UI", description: "Summarize screens, flows, and design system" },
    { id: "react", label: "Generate React", description: "Create React components with Tailwind" },
    { id: "nextjs", label: "Generate Next.js", description: "Create Next.js 15 App Router pages" },
    { id: "flutter", label: "Generate Flutter", description: "Create Flutter widgets for the screens" },
  ],
  roadmap: [
    { id: "explain", label: "Explain Roadmap", description: "Summarize milestones, critical path, and team plan" },
    { id: "sprint", label: "Generate Sprint Plan", description: "Break weekly milestones into sprint-ready tasks" },
    { id: "github", label: "Generate GitHub Issues", description: "Create GitHub issues with labels and milestones" },
    { id: "jira", label: "Generate Jira Tasks", description: "Create Jira epics, stories, and tasks" },
    { id: "generate-sprint-plan", label: "Generate Sprint Plan", description: "Derive implementation plan: epics, sprints, goals, tasks, dependencies, priorities, effort estimates, critical path" },
  ],
  security: [
    { id: "explain", label: "Explain Security", description: "Summarize OWASP coverage and controls" },
    { id: "audit", label: "Generate Security Audit", description: "Create a security audit checklist" },
    { id: "threat", label: "Generate Threat Model", description: "Create STRIDE threat model for the architecture" },
    { id: "compliance", label: "Generate Compliance Map", description: "Map controls to GDPR, SOC2, ISO27001" },
    { id: "security-audit", label: "Security Audit", description: "Analyze authentication, authorization, data protection, API security, secrets, dependencies, infrastructure, deployment, logging, and domain-specific threats" },
  ],
  performance: [
    { id: "explain", label: "Explain Performance", description: "Summarize bottlenecks and optimizations" },
    { id: "queries", label: "Generate Index Scripts", description: "Create SQL index statements for hot queries" },
    { id: "cache", label: "Generate Cache Strategy", description: "Produce Redis caching patterns for hot data" },
    { id: "load", label: "Generate Load Test Plan", description: "Create k6/Locust scripts for key endpoints" },
  ],
  scalability: [
    { id: "explain", label: "Explain Scalability", description: "Summarize growth scenarios and migration triggers" },
    { id: "k8s", label: "Generate K8s Manifests", description: "Create Kubernetes Deployments, Services, HPA" },
    { id: "terraform", label: "Generate Terraform", description: "Create IaC for the target cloud platform" },
    { id: "capacity", label: "Generate Capacity Model", description: "Calculate resource needs per scenario" },
  ],
  cost_estimation: [
    { id: "explain", label: "Explain Costs", description: "Break down dev, infra, and operational costs" },
    { id: "optimize", label: "Generate Optimization Plan", description: "Identify cost reduction opportunities" },
    { id: "budget", label: "Generate Budget Template", description: "Create a monthly/annual budget spreadsheet" },
    { id: "roi", label: "Generate ROI Model", description: "Build a cost-benefit analysis template" },
  ],
  business_risks: [
    { id: "explain", label: "Explain Risks", description: "Summarize likelihood, impact, and mitigations" },
    { id: "register", label: "Generate Risk Register", description: "Create a risk register with owners and dates" },
    { id: "mitigation", label: "Generate Mitigation Plan", description: "Create action plans for high-priority risks" },
    { id: "monitor", label: "Generate Risk Dashboard", description: "Define KPIs and alerts for risk monitoring" },
    { id: "generate-risk-register", label: "Generate Risk Register", description: "Analyze technical, security, operational, scalability, dependency, delivery, data, compliance, vendor risks with severity, mitigation, owner role, monitoring signal" },
  ],
  design_decisions: [
    { id: "explain", label: "Explain Decisions", description: "Summarize key decisions and their rationale" },
    { id: "adr", label: "Generate ADRs", description: "Create Architecture Decision Records" },
    { id: "tradeoffs", label: "Generate Tradeoff Matrix", description: "Create a decision vs alternatives matrix" },
    { id: "review", label: "Generate Decision Review", description: "Create a template for decision review meetings" },
  ],
  tradeoffs: [
    { id: "explain", label: "Explain Tradeoffs", description: "Summarize chosen vs alternative with rationale" },
    { id: "matrix", label: "Generate Comparison Matrix", description: "Create a feature-by-feature comparison" },
    { id: "decision", label: "Generate Decision Log", description: "Document all tradeoff decisions chronologically" },
  ],
  technology_evaluation: [
    { id: "explain", label: "Explain Evaluation", description: "Summarize how each technology was scored" },
    { id: "matrix", label: "Generate Decision Matrix", description: "Create a technology selection matrix" },
    { id: "poc", label: "Generate PoC Plan", description: "Create a proof-of-concept plan for top candidates" },
  ],
  product_evolution: [
    { id: "explain", label: "Explain Evolution", description: "Summarize the 5-version product roadmap" },
    { id: "roadmap", label: "Generate Release Plan", description: "Create a release timeline with dependencies" },
    { id: "migration", label: "Generate Migration Checklist", description: "Create migration tasks per version" },
  ],
  adr: [
    { id: "explain", label: "Explain ADRs", description: "Summarize all architecture decisions" },
    { id: "index", label: "Generate ADR Index", description: "Create a searchable ADR index page" },
    { id: "template", label: "Generate ADR Template", description: "Create a blank ADR template for future use" },
  ],
  testing: [
    { id: "explain", label: "Explain Testing", description: "Summarize unit, integration, and E2E strategies" },
    { id: "unit", label: "Generate Unit Tests", description: "Create Jest/Vitest unit test scaffolding" },
    { id: "integration", label: "Generate Integration Tests", description: "Create Testcontainers integration tests" },
    { id: "e2e", label: "Generate E2E Tests", description: "Create Playwright/Cypress E2E scenarios" },
    { id: "generate-test-strategy", label: "Generate Test Strategy", description: "Derive practical testing strategy: unit, integration, API, database, frontend, E2E, security, performance, test data, CI execution" },
  ],
  documentation: [
    { id: "explain", label: "Explain Docs", description: "Summarize all generated documentation" },
    { id: "readme", label: "Enhance README", description: "Rewrite README with badges, screenshots, TOC" },
    { id: "api", label: "Generate API Reference", description: "Create OpenAPI-based API documentation" },
    { id: "guides", label: "Generate User Guides", description: "Create step-by-step user guides" },
  ],
  deployment: [
    { id: "explain", label: "Explain Deployment", description: "Summarize infra, CI/CD, and runbooks" },
    { id: "docker", label: "Generate Dockerfile", description: "Create optimized multi-stage Dockerfile" },
    { id: "compose", label: "Generate docker-compose", description: "Create local development compose file" },
    { id: "ci", label: "Generate CI/CD Pipeline", description: "Create GitHub Actions / GitLab CI pipeline" },
    { id: "generate-ci-cd", label: "Generate CI/CD Pipeline", description: "Stack-aware CI/CD: install/build, lint, test, security checks, artifacts, deployment, environments, secrets, rollback" },
  ],
  validation: [
    { id: "explain", label: "Explain Validation", description: "Summarize quality checks and gaps" },
    { id: "report", label: "Generate Quality Report", description: "Create a formal quality assurance report" },
    { id: "checklist", label: "Generate Release Checklist", description: "Create a pre-release verification checklist" },
  ],
  default: [
    { id: "explain", label: "Explain this section", description: "Get a plain-language summary" },
    { id: "generate", label: "Generate Artifact", description: "Create a code artifact for this section" },
    { id: "refine", label: "Refine with AI", description: "Ask AI to improve this section" },
    { id: "export", label: "Export Section", description: "Download this section as Markdown/JSON" },
  ],
};

function getActionsForSection(section: SectionKey): AIAction[] {
  return SECTION_ACTIONS[section] || SECTION_ACTIONS.default;
}

interface AIActionsPanelProps {
  sectionKey: SectionKey;
  onAction?: (actionId: string, sectionKey: SectionKey) => void;
  busyAction?: string | null;
  implementedActions?: Set<string>;
}

export function AIActionsPanel({ sectionKey, onAction, busyAction, implementedActions }: AIActionsPanelProps) {
  const actions = getActionsForSection(sectionKey);
  const isDefault = !SECTION_ACTIONS[sectionKey];

  return (
    <Card className="border-l-4 border-primary/20 bg-primary/5">
      <CardHeader className="pb-3">
        <CardTitle className="text-base flex items-center gap-2">
          <span className="text-xs font-mono text-primary/70">AI Actions</span>
          {isDefault && <Badge tone="info" className="ml-2">Generic</Badge>}
        </CardTitle>
      </CardHeader>
      <CardContent className="pt-0">
        <div className="grid gap-2 sm:grid-cols-2">
          {actions.map((action) => {
            const busy = busyAction === action.id;
            const isImplemented = implementedActions?.has(action.id) ?? false;
            return (
              <Button
                key={action.id}
                variant={isImplemented ? "outline" : "ghost"}
                size="sm"
                className={`h-auto min-h-[56px] px-3 py-2 text-left justify-start gap-2 ${!isImplemented ? "opacity-60" : ""}`}
                onClick={() => onAction?.(action.id, sectionKey)}
                disabled={busy || Boolean(busyAction) || !isImplemented}
                title={!isImplemented ? "Coming soon — not yet implemented" : undefined}
              >
                <div className="flex flex-col items-start gap-0.5">
                  <span className="flex items-center gap-2 font-medium text-sm">
                    {busy && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
                    {!isImplemented && <span className="text-xs bg-muted px-1.5 py-0.5 rounded">Soon</span>}
                    {action.label}
                  </span>
                  <span className="text-xs text-muted-foreground">
                    {busy ? "Generating project files..." : !isImplemented ? "Coming soon" : action.description}
                  </span>
                </div>
              </Button>
            );
          })}
        </div>
      </CardContent>
    </Card>
  );
}

export function getSectionDisplayName(sectionKey: string): string {
  const names: Record<string, string> = {
    analysis: "Requirements Analysis",
    domain_understanding: "Domain Understanding",
    business_processes: "Business Process Modeling",
    technology_selection: "Technology Selection",
    technology_evaluation: "Technology Evaluation",
    design_decisions: "Design Decisions",
    tradeoffs: "Trade-off Analysis",
    architecture: "Architecture",
    database: "Database Design",
    api: "API Specification",
    ui_ux: "UI/UX Plan",
    security: "Security Review",
    performance: "Performance Review",
    scalability: "Scalability Planning",
    cost_estimation: "Cost Estimation",
    business_risks: "Business Risk Analysis",
    roadmap: "Development Roadmap",
    product_evolution: "Product Evolution",
    adr: "Architecture Decision Records",
    testing: "Testing Strategy",
    documentation: "Documentation",
    deployment: "Deployment & DevOps",
    validation: "Blueprint Quality Review",
  };
  return names[sectionKey] || sectionKey;
}