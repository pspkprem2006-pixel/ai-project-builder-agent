"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import {
  ArrowLeft,
  CheckCircle2,
  Copy,
  Download,
  FilePlus2,
  Loader2,
  Pencil,
  RefreshCw,
  Trash2,
  Wand2,
  X,
  AlertTriangle,
  Zap,
} from "lucide-react";
import { api, ApiError, downloadProject } from "@/lib/api";
import { downloadCodegen, isCodegenAction } from "@/lib/codegen";
import {
  executeAction,
  fetchActionCatalog,
  isImplementedAction,
  mapSectionActionToEngine,
  type ActionMeta,
  type ActionResult,
} from "@/lib/actions";
import { artifactKindLabel, generateActionArtifact } from "@/lib/actions";
import {
  JOB_ACTIVE_STATUSES,
  JOB_STAGE_LABEL,
  STATUS_LABEL,
  type GenerationJob,
  type Project,
} from "@/lib/types";
import { Badge, Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/feedback";
import { BlueprintWorkspace } from "@/components/blueprint/workspace";
import { getSectionDisplayName } from "@/components/blueprint/ai-actions";
import { ActionHistoryPanel } from "@/components/blueprint/action-history";
import { RevisionHistoryPanel } from "@/components/blueprint/revision-history";
import { EditProjectDialog } from "@/components/blueprint/edit-dialog";
import { DiagramsPanel } from "@/components/diagrams/diagrams-panel";
import { DownloadCenterDialog } from "@/components/workspace/download-center";

const EXPORT_FORMATS = [
  { format: "markdown", label: "Markdown (.md)" },
  { format: "pdf", label: "PDF (.pdf)" },
  { format: "docx", label: "DOCX (.docx)" },
  { format: "json", label: "JSON (.json)" },
  { format: "zip", label: "ZIP archive (.zip)" },
];

interface ActionDialogState {
  type: "executing" | "result" | "coming-soon";
  actionId: string;
  sectionKey: string;
  engineActionId?: string;
  result?: ActionResult;
}

export default function ProjectDetailPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const projectId = Number(id);
  const [project, setProject] = useState<Project | null>(null);
  const [job, setJob] = useState<GenerationJob | null>(null);
  const [error, setError] = useState("");
  const [editOpen, setEditOpen] = useState(false);
  const [downloadOpen, setDownloadOpen] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [generatingAction, setGeneratingAction] = useState<string | null>(null);
  const [actionDialog, setActionDialog] = useState<ActionDialogState | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const load = useCallback(async () => {
    try {
      setProject(await api.get<Project>(`/projects/${projectId}`));
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Failed to load project");
    }
  }, [projectId]);

  const loadJob = useCallback(async () => {
    try {
      const jobs = await api.get<GenerationJob[]>(`/projects/${projectId}/jobs`);
      const latest = jobs.length > 0 ? jobs[jobs.length - 1] : null;
      setJob(latest);
      return latest;
    } catch {
      return null;
    }
  }, [projectId]);

  useEffect(() => {
    load();
    void loadJob();
  }, [load, loadJob]);

  useEffect(() => {
    const onRefresh = () => void load();
    window.addEventListener("blueprint-refresh", onRefresh);
    return () => window.removeEventListener("blueprint-refresh", onRefresh);
  }, [load]);

  useEffect(() => {
    if (project?.status === "processing" && !pollRef.current) {
      pollRef.current = setInterval(() => {
        void load();
        void loadJob();
      }, 2000);
    }
    if (project?.status !== "processing" && pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
      void loadJob();
    }
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [project?.status, load, loadJob]);

  const regenerate = async () => {
    setGenerating(true);
    try {
      const resp = await api.post<{ job_id: number | null }>(`/projects/${projectId}/generate`);
      if (resp.job_id) {
        await loadJob();
      }
      await load();
    } finally {
      setGenerating(false);
    }
  };

  const cancelGeneration = async () => {
    if (!job || !JOB_ACTIVE_STATUSES.has(job.status)) return;
    await api.post(`/projects/${projectId}/jobs/${job.id}/cancel`);
    await loadJob();
    await load();
  };

  const remove = async () => {
    if (!confirm("Delete this project and its blueprint?")) return;
    await api.del(`/projects/${projectId}`);
    router.push("/projects");
  };

  const duplicate = async () => {
    await api.post(`/projects/${projectId}/duplicate`);
    router.push("/projects");
  };

  const handleExport = (format: string) => {
    downloadProject(projectId, format, project?.name ?? "project");
  };

  const handleAction = async (actionId: string, sectionKey: string) => {
    // Codegen actions still use direct download
    if (isCodegenAction(actionId)) {
      setGeneratingAction(actionId);
      try {
        await downloadCodegen(projectId, actionId, project?.name ?? "project");
      } catch {
        alert("Code generation failed. Make sure the blueprint has been generated.");
      } finally {
        setGeneratingAction(null);
      }
      return;
    }

    // Map to engine action ID
    const engineActionId = mapSectionActionToEngine(sectionKey, actionId);
    if (!engineActionId) {
      // Unmapped action
      setActionDialog({
        type: "coming-soon",
        actionId,
        sectionKey,
      });
      return;
    }

    const implemented = isImplementedAction(engineActionId);

    if (!implemented) {
      setActionDialog({
        type: "coming-soon",
        actionId,
        sectionKey,
        engineActionId,
      });
      return;
    }

    // Execute implemented action
    setActionDialog({
      type: "executing",
      actionId,
      sectionKey,
      engineActionId,
    });

    try {
      // Build inputs based on action type
      const inputs: Record<string, unknown> = {};
      if (engineActionId === "explain-section" || engineActionId === "transform-section" || engineActionId.startsWith("generate-")) {
        inputs.section = sectionKey;
      }
      if (engineActionId.startsWith("generate-diagram-")) {
        inputs.diagram_id = engineActionId.replace("generate-diagram-", "");
      }
      if (engineActionId.startsWith("generate-") && !engineActionId.startsWith("generate-diagram-")) {
        // Codegen actions: the engine uses the action ID directly
      }

      const result = await executeAction(projectId, engineActionId, inputs);

      if (result.status === "accepted") {
        // Long-running action - poll job status
        setActionDialog({
          type: "result",
          actionId,
          sectionKey,
          engineActionId,
          result: {
            ...result,
            message: "Action queued. Check the jobs panel for progress.",
          },
        });
      } else {
        setActionDialog({
          type: "result",
          actionId,
          sectionKey,
          engineActionId,
          result,
        });
        // If the action mutates the blueprint, trigger a refresh
        if (result.status === "success" || result.status === "fallback") {
          window.dispatchEvent(new Event("blueprint-refresh"));
        }
      }
    } catch (err) {
      const detail = err instanceof ApiError ? err.detail : "Action failed unexpectedly";
      setActionDialog({
        type: "result",
        actionId,
        sectionKey,
        engineActionId,
        result: {
          action_id: engineActionId,
          status: "error",
          message: detail,
          result: null,
          section: null,
          warnings: [],
          provider: null,
          artifact: null,
          job_id: null,
        },
      });
    }
  };

  if (error) {
    return (
      <div className="mx-auto max-w-2xl">
        <Card>
          <CardContent className="space-y-4 py-8 text-center">
            <p className="text-sm text-destructive">{error}</p>
            <Link href="/projects">
              <Button variant="outline"><ArrowLeft className="h-4 w-4" /> Back to projects</Button>
            </Link>
          </CardContent>
        </Card>
      </div>
    );
  }

  if (!project) return <Spinner label="Loading project..." />;

  const statusTone =
    project.status === "complete" ? "success" : project.status === "processing" ? "warning" : project.status === "failed" ? "danger" : "default";

  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <Link href="/projects" className="mb-1 flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
            <ArrowLeft className="h-3.5 w-3.5" /> My Projects
          </Link>
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="text-2xl font-bold">{project.name}</h1>
            <Badge tone={statusTone as "success" | "warning" | "danger" | "default"}>
              {STATUS_LABEL[project.status]}
            </Badge>
            {project.blueprint && (
              <Badge tone="info">{project.ai_provider === "template" ? "Template engine" : `AI generated (${project.ai_provider})`}</Badge>
            )}
          </div>
          <p className="mt-1 line-clamp-2 max-w-2xl text-sm text-muted-foreground">
            {project.description || "No description provided."}
          </p>
          <div className="mt-2 flex flex-wrap gap-1.5">
            <Badge>{project.category}</Badge>
            <Badge>{project.preferred_backend}</Badge>
            <Badge>{project.preferred_frontend}</Badge>
            <Badge>{project.database}</Badge>
            <Badge>{project.auth_method}</Badge>
            <Badge>{project.deployment_platform}</Badge>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {project.status !== "complete" && project.status !== "processing" && (
            <Button onClick={regenerate} loading={generating}>
              <Wand2 className="h-4 w-4" /> Generate Blueprint
            </Button>
          )}
          {project.status === "complete" && (
            <>
              <Button onClick={() => setDownloadOpen(true)} title="Open the download center">
                <Download className="h-4 w-4" /> Download Center
              </Button>
              <div className="relative">
                <select
                  value=""
                  onChange={(e) => e.target.value && handleExport(e.target.value)}
                  className="h-10 cursor-pointer rounded-md border border-input bg-card px-3 text-sm shadow-sm hover:bg-secondary/60 focus-visible:outline-none"
                >
                  <option value="">Export…</option>
                  {EXPORT_FORMATS.map((f) => (
                    <option key={f.format} value={f.format}>
                      {f.label}
                    </option>
                  ))}
                </select>
              </div>
              <Button variant="outline" onClick={() => setEditOpen(true)} title="Edit project">
                <Pencil className="h-4 w-4" /> Edit
              </Button>
              <Button variant="outline" onClick={regenerate} loading={generating} title="Regenerate blueprint">
                <RefreshCw className="h-4 w-4" />
              </Button>
            </>
          )}
          <Button variant="outline" onClick={duplicate} title="Duplicate project">
            <Copy className="h-4 w-4" />
          </Button>
          <Button variant="outline" className="text-destructive hover:text-destructive" onClick={remove} title="Delete project">
            <Trash2 className="h-4 w-4" />
          </Button>
        </div>
      </div>

      {project.status === "failed" && (
        <Card className="border-destructive/40">
          <CardContent className="space-y-2 py-4">
            <p className="flex items-center gap-2 text-sm font-medium text-destructive">
              <Loader2 className="h-4 w-4" /> Generation failed
            </p>
            <p className="text-sm text-muted-foreground">{project.generation_error}</p>
            <Button size="sm" onClick={regenerate} loading={generating}>
              Try again
            </Button>
          </CardContent>
        </Card>
      )}

      {project.status === "processing" && (
        <Card>
          <CardContent className="flex flex-wrap items-center justify-between gap-4 py-6">
            <div className="flex items-center gap-4">
              <Loader2 className="h-6 w-6 animate-spin text-primary" />
              <div>
                <p className="font-medium">The agents are architecting your project…</p>
                <p className="text-sm text-muted-foreground">
                  {job && JOB_ACTIVE_STATUSES.has(job.status)
                    ? `${JOB_STAGE_LABEL[job.current_stage] ?? job.current_stage} — ${job.progress}%`
                    : "Running requirement analysis, architecture, database, API, UI/UX, roadmap, testing, DevOps and documentation agents in parallel."}
                </p>
                {job && JOB_ACTIVE_STATUSES.has(job.status) && job.attempt_count > 1 && (
                  <p className="mt-1 text-xs text-muted-foreground">Retry {job.attempt_count} of 3</p>
                )}
              </div>
            </div>
            {job && JOB_ACTIVE_STATUSES.has(job.status) && (
              <Button variant="outline" size="sm" onClick={cancelGeneration}>
                Cancel generation
              </Button>
            )}
          </CardContent>
          {job && JOB_ACTIVE_STATUSES.has(job.status) && (
            <div className="h-1 w-full bg-secondary">
              <div className="h-full bg-primary transition-all duration-500" style={{ width: `${job.progress}%` }} />
            </div>
          )}
        </Card>
      )}

      {project.status === "draft" && !project.blueprint && (
        <Card>
          <CardContent className="flex flex-col items-center gap-4 py-12 text-center">
            <FilePlus2 className="h-10 w-10 text-muted-foreground" />
            <p className="font-medium">No blueprint yet</p>
            <p className="max-w-md text-sm text-muted-foreground">
              Generate a complete software blueprint — architecture diagrams, database design, API spec, roadmap and more.
            </p>
            <Button onClick={regenerate} loading={generating}>
              <Wand2 className="h-4 w-4" /> Generate Blueprint
            </Button>
          </CardContent>
        </Card>
      )}

      {project.blueprint && (
        <>
          <div className="flex flex-wrap items-center justify-between gap-3">
            <p className="text-sm text-muted-foreground">
              Interactive blueprint — expand a module, search within it, copy or export its content, or run an AI action.
            </p>
          </div>

          <DiagramsPanel projectId={projectId} blueprintUpdatedAt={project.updated_at} />

          <BlueprintWorkspace
            blueprint={project.blueprint}
            generationStatus={
              project.status === "complete" ? "complete" : project.status === "processing" ? "pending" : "failed"
            }
            onAction={handleAction}
            busyAction={generatingAction}
          />

          <ActionHistoryPanel projectId={projectId} />

          <RevisionHistoryPanel projectId={projectId} />
        </>
      )}

      {actionDialog && (
        <ActionResultDialog
          dialog={actionDialog}
          onClose={() => setActionDialog(null)}
          projectName={project.name}
          projectId={projectId}
        />
      )}

      <EditProjectDialog
        open={editOpen}
        onOpenChange={setEditOpen}
        project={project}
        onSaved={(updated) => {
          setProject(updated);
          setEditOpen(false);
        }}
      />

      <DownloadCenterDialog open={downloadOpen} onOpenChange={setDownloadOpen} projectId={projectId} />
    </div>
  );
}

function ActionResultDialog({
  dialog,
  onClose,
  projectName,
  projectId,
}: {
  dialog: ActionDialogState;
  onClose: () => void;
  projectName?: string;
  projectId: number;
}) {
  const { type, actionId, sectionKey, engineActionId, result } = dialog;
  const [artifactBusy, setArtifactBusy] = useState(false);

  const handleGenerateArtifact = async () => {
    if (!engineActionId) return;
    setArtifactBusy(true);
    try {
      const artifactResult = await generateActionArtifact(projectId, engineActionId);
      if (artifactResult.artifact) {
        window.open(artifactResult.artifact.download_url, "_blank");
      }
    } catch (err) {
      alert(err instanceof ApiError ? err.detail : "Artifact generation failed");
    } finally {
      setArtifactBusy(false);
    }
  };

  if (type === "executing") {
    return (
      <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4" onClick={onClose}>
        <Card className="w-full max-w-md" onClick={(e) => e.stopPropagation()}>
          <CardContent className="flex flex-col items-center gap-4 py-8">
            <Loader2 className="h-10 w-10 animate-spin text-primary" />
            <div className="text-center">
              <p className="text-lg font-semibold">Running AI Action</p>
              <p className="text-sm text-muted-foreground mt-1">
                {getSectionDisplayName(sectionKey)} · {engineActionId || actionId}
              </p>
              <p className="text-xs text-muted-foreground mt-2">This may take a moment…</p>
            </div>
          </CardContent>
        </Card>
      </div>
    );
  }

  if (type === "coming-soon") {
    return (
      <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4" onClick={onClose}>
        <Card className="w-full max-w-md" onClick={(e) => e.stopPropagation()}>
          <CardContent className="space-y-4 py-6">
            <div className="flex items-start justify-between gap-4">
              <div>
                <p className="text-lg font-semibold">Coming Soon</p>
                <p className="text-sm text-muted-foreground">
                  {getSectionDisplayName(sectionKey)} · {engineActionId || actionId}
                </p>
              </div>
              <Button variant="ghost" size="icon" onClick={onClose}>
                <X className="h-4 w-4" />
              </Button>
            </div>
            <p className="text-sm text-muted-foreground">
              The <span className="font-medium">{actionId}</span> action for this section is not yet implemented.
              It will be connected in a future phase.
            </p>
            <div className="flex justify-end">
              <Button onClick={onClose}>Close</Button>
            </div>
          </CardContent>
        </Card>
      </div>
    );
  }

  // type === "result"
  const r = result!;
  const isSuccess = r.status === "success";
  const isFallback = r.status === "fallback";
  const isError = r.status === "error" || r.status === "validation_failed" || r.status === "llm_failed";

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4" onClick={onClose}>
      <Card className={`w-full max-w-2xl ${isError ? "border-destructive/40" : ""}`} onClick={(e) => e.stopPropagation()}>
        <CardContent className="space-y-4 py-6">
          <div className="flex items-start justify-between gap-4">
            <div className="flex items-center gap-3">
              {isSuccess && <CheckCircle2 className="h-5 w-5 text-green-500" />}
              {isFallback && <Zap className="h-5 w-5 text-yellow-500" />}
              {isError && <AlertTriangle className="h-5 w-5 text-destructive" />}
              <div>
                <p className="text-lg font-semibold">
                  {isSuccess ? "Action Completed" : isFallback ? "Action Completed (Fallback)" : "Action Failed"}
                </p>
                <p className="text-sm text-muted-foreground">
                  {getSectionDisplayName(sectionKey)} · {engineActionId || actionId}
                </p>
              </div>
            </div>
            <Button variant="ghost" size="icon" onClick={onClose}>
              <X className="h-4 w-4" />
            </Button>
          </div>

          {r.message && (
            <p className={`text-sm ${isError ? "text-destructive" : "text-muted-foreground"}`}>
              {r.message}
            </p>
          )}

          {r.warnings.length > 0 && (
            <div className="rounded-md bg-yellow-50 border border-yellow-200 p-3 space-y-1">
              <p className="text-xs font-medium text-yellow-800">Warnings</p>
              {r.warnings.map((w, i) => (
                <p key={i} className="text-xs text-yellow-700">• {w}</p>
              ))}
            </div>
          )}

          {r.provider && (
            <p className="text-xs text-muted-foreground">
              Provider: <span className="font-medium capitalize">{r.provider}</span>
            </p>
          )}

          {r.section && r.result && (
            <details className="group">
              <summary className="cursor-pointer text-sm font-medium text-muted-foreground flex items-center gap-1">
                View {getSectionDisplayName(r.section)} result
                <Zap className="h-3.5 w-3.5 transition-transform group-open:rotate-90" />
              </summary>
              <div className="mt-2 p-3 rounded-md bg-muted/50 text-xs font-mono max-h-60 overflow-auto">
                <pre>{JSON.stringify(r.result, null, 2)}</pre>
              </div>
            </details>
          )}

          {r.artifact && (
            <div className="rounded-md bg-primary/5 border border-primary/20 p-3 space-y-2">
              <p className="text-sm font-medium">Artifact Generated</p>
              <p className="text-xs text-muted-foreground">{r.artifact.filename}</p>
              <Button size="sm" onClick={() => window.open(r.artifact!.download_url, "_blank")}>
                <Download className="h-3.5 w-3.5" /> Download {artifactKindLabel(r.artifact.kind)}
              </Button>
            </div>
          )}

          {!r.artifact && isSuccess && engineActionId === "generate-ci-cd" && (
            <div className="rounded-md bg-primary/5 border border-primary/20 p-3 space-y-2">
              <p className="text-sm font-medium">Downloadable Artifact</p>
              <p className="text-xs text-muted-foreground">
                Generate a deterministic GitHub Actions workflow package (CI + deploy) from the blueprint stack.
              </p>
              <Button size="sm" onClick={() => void handleGenerateArtifact()} loading={artifactBusy}>
                <Download className="h-3.5 w-3.5" /> Generate CI/CD Config ZIP
              </Button>
            </div>
          )}

          {!r.artifact && isSuccess && engineActionId === "generate-test-strategy" && (
            <div className="rounded-md bg-primary/5 border border-primary/20 p-3 space-y-2">
              <p className="text-sm font-medium">Downloadable Artifact</p>
              <p className="text-xs text-muted-foreground">
                Generate a stack-appropriate test scaffolding package (pytest / Jest / Vitest / JUnit).
              </p>
              <Button size="sm" onClick={() => void handleGenerateArtifact()} loading={artifactBusy}>
                <Download className="h-3.5 w-3.5" /> Generate Test Scaffold ZIP
              </Button>
            </div>
          )}

          {r.job_id && (
            <div className="rounded-md bg-blue-50 border border-blue-200 p-3">
              <p className="text-sm font-medium text-blue-800">Long-running action queued</p>
              <p className="text-xs text-blue-700">Job ID: {r.job_id} — check the jobs panel for progress.</p>
            </div>
          )}

          <div className="flex justify-end gap-2 pt-2">
            <Button variant="outline" onClick={onClose}>Close</Button>
            {isSuccess && r.section && r.result && (
              <Button onClick={() => { window.dispatchEvent(new Event("blueprint-refresh")); onClose(); }}>
                Refresh Blueprint
              </Button>
            )}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}