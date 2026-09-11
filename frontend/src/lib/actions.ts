import { api } from "./api";

export interface ActionMeta {
  id: string;
  name: string;
  category: "analysis" | "transformation" | "diagram" | "code" | "documentation";
  description: string;
  execution_mode: "short" | "long";
  mutates_project: boolean;
  supports_fallback: boolean;
  requires_blueprint: boolean;
  inputs: Record<string, unknown>;
  apply_mode: "none" | "patch" | "replace" | "merge";
  depends_on: string[];
}

export interface ActionCatalog {
  items: ActionMeta[];
}

export interface ActionExecuteRequest {
  inputs: Record<string, unknown>;
}

export interface ActionArtifact {
  kind: "codegen-zip" | "diagram" | "ci-cd" | "test-scaffold";
  filename: string;
  download_url: string;
}

export interface ActionResult {
  action_id: string;
  status: "success" | "fallback" | "validation_failed" | "llm_failed" | "error" | "accepted";
  message: string | null;
  result: Record<string, unknown> | null;
  section: string | null;
  warnings: string[];
  provider: string | null;
  artifact: ActionArtifact | null;
  job_id: number | null;
}

export type QualityStatus = "valid" | "invalid" | "partial";

export interface ActionHistoryItem {
  id: number;
  action_id: string;
  action_name: string;
  status: string;
  provider: string | null;
  section: string | null;
  warning_count: number;
  applied: boolean;
  applied_at: string | null;
  created_at: string;
  completed_at: string | null;
  quality: QualityStatus | null;
  completeness: number | null;
}

export interface ActionHistoryResponse {
  items: ActionHistoryItem[];
  total: number;
  limit: number;
  offset: number;
}

export interface ActionDetail extends ActionHistoryItem {
  project_id: number;
  input: Record<string, unknown> | null;
  result: Record<string, unknown> | null;
  warnings: string[];
  blueprint_revision: number;
  applied_by: number | null;
  consistency_status: string | null;
  artifact_available: boolean;
}

export interface ActionApplyResponse {
  success: boolean;
  message: string;
  revision: number;
  section: string | null;
}

const IMPLEMENTED_ACTIONS = new Set([
  // Analysis
  "explain-project",
  "explain-section",
  // Transform (section-scoped)
  "improve-requirements",
  "generate-architecture",
  "generate-database-design",
  "generate-api-specification",
  "generate-uiux-plan",
  "generate-testing-strategy",
  "generate-deployment-plan",
  "generate-security-recommendations",
  "generate-project-roadmap",
  "transform-section",
  // Phase 10: Specialized AI Actions
  "security-audit",
  "generate-test-strategy",
  "generate-ci-cd",
  "generate-sprint-plan",
  "generate-risk-register",
  "generate-compliance-map",
  // Diagrams
  "generate-diagram-c4",
  "generate-diagram-class",
  "generate-diagram-component",
  "generate-diagram-deployment",
  "generate-diagram-erd",
  "generate-diagram-flowchart",
  "generate-diagram-overview",
  "generate-diagram-sequence",
  // Codegen
  "generate-express",
  "generate-fastapi",
  "generate-nextjs",
  "generate-prisma",
  "generate-react",
  "generate-sql",
  "generate-sqlalchemy",
  "generate-spring",
]);

export function isImplementedAction(actionId: string): boolean {
  return IMPLEMENTED_ACTIONS.has(actionId);
}

export function mapSectionActionToEngine(sectionKey: string, actionId: string): string | null {
  // Map frontend per-section actions to engine action IDs
  if (actionId === "explain") {
    return "explain-section";
  }
  // Project-level specialized actions (Phase 10)
  const PROJECT_ACTIONS: Record<string, string> = {
    "security-audit": "security-audit",
    "generate-test-strategy": "generate-test-strategy",
    "generate-ci-cd": "generate-ci-cd",
    "generate-sprint-plan": "generate-sprint-plan",
    "generate-risk-register": "generate-risk-register",
    "generate-compliance-map": "generate-compliance-map",
  };
  if (actionId in PROJECT_ACTIONS) {
    return PROJECT_ACTIONS[actionId];
  }
  // Codegen actions
  const CODEGEN_MAP: Record<string, string> = {
    sql: "generate-sql",
    prisma: "generate-prisma",
    sqlalchemy: "generate-sqlalchemy",
    fastapi: "generate-fastapi",
    express: "generate-express",
    spring: "generate-spring",
    react: "generate-react",
    nextjs: "generate-nextjs",
  };
  if (actionId in CODEGEN_MAP) {
    return CODEGEN_MAP[actionId];
  }
  // Diagram actions
  const DIAGRAM_MAP: Record<string, string> = {
    mermaid: "generate-diagram-flowchart",
    c4: "generate-diagram-c4",
    drawio: "generate-diagram-flowchart",
  };
  if (actionId in DIAGRAM_MAP) {
    return DIAGRAM_MAP[actionId];
  }
  // Transform actions per section
  const TRANSFORM_MAP: Record<string, string> = {
    analysis: "improve-requirements",
    architecture: "generate-architecture",
    database: "generate-database-design",
    api: "generate-api-specification",
    ui_ux: "generate-uiux-plan",
    testing: "generate-testing-strategy",
    deployment: "generate-deployment-plan",
    security: "generate-security-recommendations",
    roadmap: "generate-project-roadmap",
    default: "transform-section",
  };
  if (sectionKey in TRANSFORM_MAP && actionId === "generate") {
    return TRANSFORM_MAP[sectionKey];
  }
  if (actionId === "refine" && sectionKey in TRANSFORM_MAP) {
    return TRANSFORM_MAP[sectionKey];
  }
  // Project-level explain
  if (actionId === "explain-project") {
    return "explain-project";
  }
  return null;
}

export async function fetchActionCatalog(projectId: number): Promise<ActionMeta[]> {
  const catalog = await api.get<ActionCatalog>(`/projects/${projectId}/actions`);
  return catalog.items;
}

export async function executeAction(
  projectId: number,
  actionId: string,
  inputs: Record<string, unknown> = {}
): Promise<ActionResult> {
  const result = await api.post<ActionResult>(`/projects/${projectId}/actions/${actionId}`, { inputs });
  return result;
}

export async function fetchActionHistory(
  projectId: number,
  limit = 20,
  offset = 0
): Promise<ActionHistoryResponse> {
  return api.get<ActionHistoryResponse>(
    `/projects/${projectId}/actions/history?limit=${limit}&offset=${offset}`
  );
}

export async function fetchActionResultDetail(projectId: number, resultId: number): Promise<ActionDetail> {
  return api.get<ActionDetail>(`/projects/${projectId}/actions/history/${resultId}`);
}

export async function applyActionResult(
  projectId: number,
  resultId: number,
  confirm: boolean
): Promise<ActionApplyResponse> {
  return api.post<ActionApplyResponse>(`/projects/${projectId}/actions/history/${resultId}/apply`, {
    confirm,
  });
}

export async function generateActionArtifact(
  projectId: number,
  actionId: string
): Promise<ActionResult> {
  return api.post<ActionResult>(`/projects/${projectId}/actions/${actionId}/artifact`);
}

export const ARTIFACT_CAPABLE_ACTIONS = new Set(["generate-ci-cd", "generate-test-strategy"]);

export function artifactKindLabel(kind: ActionArtifact["kind"]): string {
  switch (kind) {
    case "ci-cd":
      return "CI/CD configuration";
    case "test-scaffold":
      return "Test scaffolding";
    case "codegen-zip":
      return "Code ZIP";
    case "diagram":
      return "Diagram";
  }
}

export function qualityLabel(quality: QualityStatus | null): string {
  switch (quality) {
    case "valid":
      return "Valid";
    case "partial":
      return "Partial";
    case "invalid":
      return "Invalid";
    default:
      return "Unknown";
  }
}