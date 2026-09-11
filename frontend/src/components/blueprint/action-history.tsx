"use client";

import { useCallback, useEffect, useState } from "react";
import { CheckCircle2, Download, Eye, History, Loader2, X } from "lucide-react";
import { ApiError } from "@/lib/api";
import {
  applyActionResult,
  fetchActionHistory,
  fetchActionResultDetail,
  generateActionArtifact,
  qualityLabel,
  type ActionDetail,
  type ActionHistoryItem,
} from "@/lib/actions";
import { getSectionDisplayName } from "@/components/blueprint/ai-actions";
import { RevisionDetailDialog } from "@/components/blueprint/revision-history";
import { Badge, Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";

interface ActionHistoryPanelProps {
  projectId: number;
}

const APPLYABLE_ACTIONS = new Set([
  "improve-requirements",
  "generate-architecture",
  "generate-database-design",
  "generate-project-roadmap",
  "generate-test-strategy",
  "generate-risk-register",
  "generate-ci-cd",
]);

function statusTone(status: string): "success" | "warning" | "danger" | "info" | "default" {
  switch (status) {
    case "success":
      return "success";
    case "fallback":
    case "accepted":
      return "warning";
    case "error":
    case "validation_failed":
      return "danger";
    default:
      return "default";
  }
}

function qualityTone(quality: ActionHistoryItem["quality"]): "success" | "warning" | "danger" | "default" {
  switch (quality) {
    case "valid":
      return "success";
    case "partial":
      return "warning";
    case "invalid":
      return "danger";
    default:
      return "default";
  }
}

export function ActionHistoryPanel({ projectId }: ActionHistoryPanelProps) {
  const [items, setItems] = useState<ActionHistoryItem[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<ActionDetail | null>(null);
  const [detailOpen, setDetailOpen] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [appliedRevision, setAppliedRevision] = useState<{
    revision: number;
    message: string;
  } | null>(null);

  const load = useCallback(async () => {
    try {
      const history = await fetchActionHistory(projectId, 50);
      setItems(history.items);
      setTotal(history.total);
    } catch {
      // History is non-critical; fail silently on the panel.
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    const onRefresh = () => void load();
    window.addEventListener("blueprint-refresh", onRefresh);
    return () => window.removeEventListener("blueprint-refresh", onRefresh);
  }, [load]);

  const openDetail = async (item: ActionHistoryItem) => {
    try {
      const detail = await fetchActionResultDetail(projectId, item.id);
      setSelected(detail);
      setDetailOpen(true);
    } catch (err) {
      alert(err instanceof ApiError ? err.detail : "Failed to load action detail");
    }
  };

  const handleApply = async (detail: ActionDetail) => {
    if (!window.confirm("Apply this action result to the blueprint? This records a new blueprint revision.")) {
      return;
    }
    setBusy(`apply-${detail.id}`);
    try {
      const result = await applyActionResult(projectId, detail.id, true);
      setDetailOpen(false);
      setAppliedRevision({
        revision: result.revision,
        message: `Blueprint updated — Revision ${result.revision} created.`,
      });
      window.dispatchEvent(new Event("blueprint-refresh"));
      await load();
    } catch (err) {
      alert(err instanceof ApiError ? err.detail : "Apply failed");
    } finally {
      setBusy(null);
    }
  };

  const handleGenerateArtifact = async (detail: ActionDetail) => {
    setBusy(`artifact-${detail.id}`);
    try {
      const result = await generateActionArtifact(projectId, detail.action_id);
      if (result.artifact) {
        window.open(result.artifact.download_url, "_blank");
      }
      await load();
    } catch (err) {
      alert(err instanceof ApiError ? err.detail : "Artifact generation failed");
    } finally {
      setBusy(null);
    }
  };

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2 text-base">
          <History className="h-4 w-4 text-primary" />
          Action History
          <Badge tone="info" className="ml-1">{total}</Badge>
        </CardTitle>
      </CardHeader>
      <CardContent className="pt-0">
        {loading ? (
          <p className="flex items-center gap-2 py-6 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" /> Loading action history…
          </p>
        ) : items.length === 0 ? (
          <p className="py-6 text-sm text-muted-foreground">
            No AI actions have been run yet. Run an action above to see its results here — then apply them to the
            blueprint with a new revision.
          </p>
        ) : (
          <ul className="max-h-72 space-y-1.5 overflow-auto pr-1">
            {items.map((item) => (
              <li
                key={item.id}
                className="flex flex-wrap items-center gap-2 rounded-md border border-border/60 bg-muted/30 px-3 py-2"
              >
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium">{item.action_name}</p>
                  <p className="text-xs text-muted-foreground">
                    {new Date(item.created_at).toLocaleString()}
                    {item.section ? ` · ${getSectionDisplayName(item.section)}` : ""}
                  </p>
                </div>
                <Badge tone={statusTone(item.status)}>{item.status}</Badge>
                <Badge tone={qualityTone(item.quality)}>{qualityLabel(item.quality)}</Badge>
                {item.applied ? (
                  <Badge tone="success">Applied</Badge>
                ) : (
                  APPLYABLE_ACTIONS.has(item.action_id) && <Badge tone="info">Apply-ready</Badge>
                )}
                <Button size="sm" variant="outline" onClick={() => void openDetail(item)}>
                  <Eye className="h-3.5 w-3.5" /> View
                </Button>
              </li>
            ))}
          </ul>
        )}
      </CardContent>

      {detailOpen && selected && (
        <ActionHistoryDetail
          detail={selected}
          busy={busy}
          onClose={() => setDetailOpen(false)}
          onApply={() => void handleApply(selected)}
          onGenerateArtifact={() => void handleGenerateArtifact(selected)}
        />
      )}

      {appliedRevision && (
        <RevisionDetailDialog
          projectId={projectId}
          revision={appliedRevision.revision}
          open
          onClose={() => setAppliedRevision(null)}
          title={appliedRevision.message}
        />
      )}
    </Card>
  );
}

function ActionHistoryDetail({
  detail,
  busy,
  onClose,
  onApply,
  onGenerateArtifact,
}: {
  detail: ActionDetail;
  busy: string | null;
  onClose: () => void;
  onApply: () => void;
  onGenerateArtifact: () => void;
}) {
  const canApply = APPLYABLE_ACTIONS.has(detail.action_id) && !detail.applied;
  const canGenerateArtifact = detail.artifact_available;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4" onClick={onClose}>
      <Card className="w-full max-w-2xl" onClick={(e) => e.stopPropagation()}>
        <CardContent className="space-y-4 py-6">
          <div className="flex items-start justify-between gap-4">
            <div className="flex items-center gap-3">
              {detail.applied && <CheckCircle2 className="h-5 w-5 text-green-500" />}
              <div>
                <p className="text-lg font-semibold">{detail.action_name}</p>
                <p className="text-sm text-muted-foreground">
                  {new Date(detail.created_at).toLocaleString()}
                  {detail.section ? ` · ${getSectionDisplayName(detail.section)}` : ""}
                </p>
              </div>
            </div>
            <Button variant="ghost" size="icon" onClick={onClose}>
              <X className="h-4 w-4" />
            </Button>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <Badge tone={statusTone(detail.status)}>{detail.status}</Badge>
            <Badge tone={qualityTone(detail.quality)}>{qualityLabel(detail.quality)}</Badge>
            {detail.completeness !== null && <Badge>Completeness: {detail.completeness}%</Badge>}
            <Badge>Revision {detail.blueprint_revision}</Badge>
            {detail.provider && <Badge>{detail.provider}</Badge>}
            {detail.applied && <Badge tone="success">Applied to blueprint</Badge>}
          </div>

          {detail.warnings.length > 0 && (
            <div className="rounded-md border border-yellow-200 bg-yellow-50 p-3">
              <p className="text-xs font-medium text-yellow-800">Warnings</p>
              {detail.warnings.map((w, i) => (
                <p key={i} className="text-xs text-yellow-700">• {w}</p>
              ))}
            </div>
          )}

          {detail.result && (
            <details className="group">
              <summary className="cursor-pointer text-sm font-medium text-muted-foreground">
                View result payload
              </summary>
              <div className="mt-2 max-h-60 overflow-auto rounded-md bg-muted/50 p-3 font-mono text-xs">
                <pre>{JSON.stringify(detail.result, null, 2)}</pre>
              </div>
            </details>
          )}

          <div className="flex flex-wrap items-center justify-end gap-2 pt-2">
            {canApply && (
              <Button onClick={onApply} loading={busy === `apply-${detail.id}`}>
                <CheckCircle2 className="h-4 w-4" /> Apply to Blueprint
              </Button>
            )}
            {canGenerateArtifact && (
              <Button variant="outline" onClick={onGenerateArtifact} loading={busy === `artifact-${detail.id}`}>
                <Download className="h-4 w-4" />
                {detail.action_id === "generate-ci-cd"
                  ? "Generate CI/CD Config ZIP"
                  : "Generate Test Scaffold ZIP"}
              </Button>
            )}
            <Button variant="ghost" onClick={onClose}>
              Close
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
