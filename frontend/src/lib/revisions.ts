import { api } from "./api";

export type DiffOp = "add" | "remove" | "change";

export interface DiffItem {
  op: DiffOp;
  path: string[];
  before: unknown;
  after: unknown;
}

export interface RevisionSummary {
  revision: number;
  created_at: string;
  source_action: string;
  section: string;
  action_result_id: number | null;
  applied_by: number | null;
  summary: string[];
}

export interface RevisionListResponse {
  items: RevisionSummary[];
  total: number;
  limit: number;
  offset: number;
}

export interface RevisionDetail {
  revision: number;
  created_at: string;
  source_action: string;
  section: string;
  action_result_id: number | null;
  applied_by: number | null;
  previous_section: unknown;
  current_section: unknown;
  changed: DiffItem[];
  summary: string[];
}

export interface RevisionChangeEntry {
  revision: number;
  created_at: string;
  source_action: string;
  section: string;
  action_result_id: number | null;
  applied_by: number | null;
  before: unknown;
  after: unknown;
  changed: DiffItem[];
  summary: string[];
}

export interface RevisionCompare {
  from_revision: RevisionChangeEntry;
  to_revision: RevisionChangeEntry;
  combined: RevisionChangeEntry | null;
}

export interface RevisionRestoreResponse {
  success: boolean;
  message: string;
  revision: number;
  section: string;
}

export async function fetchRevisionHistory(
  projectId: number,
  limit = 20,
  offset = 0
): Promise<RevisionListResponse> {
  return api.get<RevisionListResponse>(
    `/projects/${projectId}/revisions?limit=${limit}&offset=${offset}`
  );
}

export async function fetchRevisionDetail(
  projectId: number,
  revision: number
): Promise<RevisionDetail> {
  return api.get<RevisionDetail>(`/projects/${projectId}/revisions/${revision}`);
}

export async function compareRevisions(
  projectId: number,
  fromRevision: number,
  toRevision: number
): Promise<RevisionCompare> {
  return api.get<RevisionCompare>(
    `/projects/${projectId}/revisions/compare?from_revision=${fromRevision}&to_revision=${toRevision}`
  );
}

export async function restoreRevision(
  projectId: number,
  revision: number,
  expectedCurrentRevision: number
): Promise<RevisionRestoreResponse> {
  return api.post<RevisionRestoreResponse>(
    `/projects/${projectId}/revisions/${revision}/restore`,
    { confirm: true, expected_current_revision: expectedCurrentRevision }
  );
}

const SOURCE_ACTION_LABELS: Record<string, string> = {
  "restore-revision": "Restore revision",
  "improve-requirements": "Improve requirements",
  "generate-architecture": "Generate architecture",
  "generate-database-design": "Generate database design",
  "generate-project-roadmap": "Generate roadmap",
  "generate-test-strategy": "Generate test strategy",
  "generate-risk-register": "Generate risk register",
  "generate-ci-cd": "Generate CI/CD",
};

export function sourceActionLabel(sourceAction: string): string {
  if (SOURCE_ACTION_LABELS[sourceAction]) return SOURCE_ACTION_LABELS[sourceAction];
  return sourceAction.replaceAll("_", " ").replace(/^\w/, (c) => c.toUpperCase());
}

export function diffPathLabel(path: string[]): string {
  if (path.length === 0) return "section";
  return path.map((segment) => segment.replaceAll("_", " ")).join(" → ");
}