"use client";

import { Module } from "./module";
import { getSectionDisplayName } from "./ai-actions";
import { SECTION_CONTENT_RENDERERS } from "./sections";
import { isImplementedAction, mapSectionActionToEngine } from "@/lib/actions";
import type { Blueprint } from "@/lib/types";

type Json = Record<string, unknown>;

interface BlueprintWorkspaceProps {
  blueprint: Blueprint;
  generationStatus?: "pending" | "complete" | "failed";
  onAction?: (actionId: string, sectionKey: string) => void;
  busyAction?: string | null;
}

const MODULE_ORDER: Array<keyof Blueprint> = [
  "analysis",
  "domain_understanding",
  "business_processes",
  "technology_selection",
  "technology_evaluation",
  "design_decisions",
  "tradeoffs",
  "architecture",
  "database",
  "api",
  "ui_ux",
  "security",
  "performance",
  "scalability",
  "cost_estimation",
  "business_risks",
  "roadmap",
  "product_evolution",
  "adr",
  "testing",
  "documentation",
  "deployment",
  "validation",
];

const INITIALLY_EXPANDED = new Set(["analysis", "architecture", "database"]);

function getImplementedActionsForSection(sectionKey: string): Set<string> {
  const implemented = new Set<string>();
  // Explain is always implemented per section
  implemented.add("explain");
  // Codegen actions
  const codegenActions = ["sql", "prisma", "sqlalchemy", "fastapi", "express", "spring", "react", "nextjs"];
  codegenActions.forEach((a) => implemented.add(a));
  // Diagram actions
  implemented.add("mermaid");
  implemented.add("c4");
  implemented.add("drawio");
  // Transform/generate actions
  if (sectionKey in ["analysis", "architecture", "database", "api", "ui_ux", "testing", "deployment", "security", "roadmap"]) {
    implemented.add("generate");
    implemented.add("refine");
  }
  // Phase 10: Specialized project-level actions mapped to relevant sections
  if (sectionKey === "security") {
    implemented.add("security-audit");
    implemented.add("generate-compliance-map");
  }
  if (sectionKey === "testing") {
    implemented.add("generate-test-strategy");
  }
  if (sectionKey === "deployment") {
    implemented.add("generate-ci-cd");
  }
  if (sectionKey === "roadmap") {
    implemented.add("generate-sprint-plan");
  }
  if (sectionKey === "business_risks") {
    implemented.add("generate-risk-register");
  }
  // validation only has explain implemented
  return implemented;
}

export function BlueprintWorkspace({
  blueprint,
  generationStatus = "complete",
  onAction,
  busyAction = null,
}: BlueprintWorkspaceProps) {
  return (
    <div className="space-y-4">
      {MODULE_ORDER.map((sectionKey) => {
        const data = blueprint[sectionKey];
        const render =
          SECTION_CONTENT_RENDERERS[sectionKey] ??
          (() => <p className="text-sm text-muted-foreground">No content renderer available.</p>);
        const implementedActions = getImplementedActionsForSection(sectionKey);
        return (
          <Module
            key={sectionKey}
            id={sectionKey}
            title={getSectionDisplayName(sectionKey)}
            sectionKey={sectionKey}
            data={(data && typeof data === "object" ? data : null) as Json | null}
            renderContent={render}
            generationStatus={generationStatus}
            onAction={onAction}
            busyAction={busyAction}
            implementedActions={implementedActions}
            initiallyExpanded={INITIALLY_EXPANDED.has(sectionKey)}
          />
        );
      })}
    </div>
  );
}
