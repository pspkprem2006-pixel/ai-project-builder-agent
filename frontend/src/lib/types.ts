export interface User {
  id: number;
  email: string;
  full_name: string;
  is_active: boolean;
  created_at: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  user: User;
}

export interface ProjectInput {
  name: string;
  description: string;
  category: string;
  target_users: string;
  features: string[];
  preferred_frontend: string;
  preferred_backend: string;
  database: string;
  auth_method: string;
  deployment_platform: string;
  language: string;
}

export interface ProjectListItem {
  id: number;
  name: string;
  description: string;
  category: string;
  status: "draft" | "processing" | "complete" | "failed";
  ai_provider: string;
  preferred_frontend: string;
  preferred_backend: string;
  database: string;
  created_at: string;
  updated_at: string;
  last_generated_at: string | null;
}

export interface Project extends ProjectListItem {
  user_id: number;
  target_users: string;
  features: string[];
  auth_method: string;
  deployment_platform: string;
  language: string;
  blueprint: Blueprint | null;
  generation_error: string | null;
}

export interface ProjectList {
  items: ProjectListItem[];
  total: number;
  page: number;
  page_size: number;
}

export type GenerationJobStatus = "queued" | "running" | "completed" | "failed" | "cancelled";

export interface GenerationJob {
  id: number;
  project_id: number;
  status: GenerationJobStatus;
  current_stage: string;
  progress: number;
  attempt_count: number;
  error_message: string | null;
  created_at: string | null;
  started_at: string | null;
  completed_at: string | null;
}

export interface GenerateResponse {
  status: string;
  detail: string;
  project_id: number;
  job_id: number | null;
}

export interface ProjectStatistics {
  total_projects: number;
  completed: number;
  in_progress: number;
  drafts: number;
  by_category: Record<string, number>;
  by_status: Record<string, number>;
  by_stack: Record<string, number>;
  last_generated_at: string | null;
}

export interface AISuggestion {
  title: string;
  detail: string;
  category: string;
}

export interface Blueprint {
  project: {
    id: number;
    name: string;
    description: string;
    category: string;
    features: string[];
    stack: Record<string, string>;
  };
  metadata: {
    generated_at: string;
    provider: string;
    version: string;
  };
  analysis: Record<string, unknown>;
  domain_understanding: Record<string, unknown>;
  business_processes: Record<string, unknown>;
  technology_selection: Record<string, unknown>;
  technology_evaluation: Record<string, unknown>;
  design_decisions: Record<string, unknown>;
  tradeoffs: Record<string, unknown>;
  architecture: Record<string, unknown>;
  database: Record<string, unknown>;
  api: Record<string, unknown>;
  ui_ux: Record<string, unknown>;
  security: Record<string, unknown>;
  performance: Record<string, unknown>;
  scalability: Record<string, unknown>;
  cost_estimation: Record<string, unknown>;
  business_risks: Record<string, unknown>;
  roadmap: Record<string, unknown>;
  product_evolution: Record<string, unknown>;
  adr: Record<string, unknown>;
  testing: Record<string, unknown>;
  documentation: Record<string, unknown>;
  validation: Record<string, unknown>;
  deployment: Record<string, unknown>;
}

export const FRONTEND_OPTIONS = ["Next.js", "React", "Angular", "Vue"];
export const BACKEND_OPTIONS = ["FastAPI", "Django", "Node.js", "Spring Boot"];
export const DATABASE_OPTIONS = ["PostgreSQL", "MySQL", "MongoDB"];
export const AUTH_OPTIONS = ["JWT", "OAuth", "Firebase"];
export const DEPLOYMENT_OPTIONS = ["Docker", "Railway", "Render", "AWS", "Azure"];
export const LANGUAGE_OPTIONS = ["TypeScript", "Python", "JavaScript", "Java"];

export const CATEGORY_OPTIONS = [
  "Healthcare",
  "Education",
  "Food & Delivery",
  "E-Commerce",
  "Business",
  "AI & Analytics",
  "Communication",
  "Finance",
  "Social",
  "General",
];

export const STATUS_LABEL: Record<string, string> = {
  draft: "Draft",
  processing: "Generating...",
  complete: "Ready",
  failed: "Failed",
};

export const JOB_STAGE_LABEL: Record<string, string> = {
  queued: "Queued",
  starting: "Starting agents",
  generating: "Architecting blueprint",
  finalizing: "Finalizing blueprint",
  persisting: "Saving blueprint",
  completed: "Complete",
  failed: "Failed",
  cancelled: "Cancelled",
};

export const JOB_ACTIVE_STATUSES = new Set<GenerationJobStatus>(["queued", "running"]);
