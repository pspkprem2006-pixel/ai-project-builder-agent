import { api } from "./api";

export interface DiagramInfo {
  id: string;
  label: string;
  description: string;
  category: string;
  format: string;
}

export interface DiagramSource {
  id: string;
  title: string;
  format: string;
  source: string;
  generated_at: string;
  blueprint_generated_at: string | null;
}

export const DIAGRAM_CATEGORY_LABELS: Record<string, string> = {
  architecture: "Architecture",
  database: "Database",
  api: "API",
  business: "Business",
};

export async function listDiagrams(projectId: number): Promise<DiagramInfo[]> {
  return api.get<DiagramInfo[]>(`/projects/${projectId}/diagrams`);
}

export async function getDiagramSource(projectId: number, diagramId: string): Promise<DiagramSource> {
  return api.get<DiagramSource>(`/projects/${projectId}/diagrams/${diagramId}`);
}
