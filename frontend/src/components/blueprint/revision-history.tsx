"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ArrowLeftRight,
  CheckCircle2,
  FileClock,
  GitCompareArrows,
  History,
  Loader2,
  RotateCcw,
  X,
} from "lucide-react";
import { ApiError } from "@/lib/api";
import {
  compareRevisions,
  fetchRevisionDetail,
  fetchRevisionHistory,
  restoreRevision,
  diffPathLabel,
  sourceActionLabel,
  type DiffItem,
  type RevisionCompare,
  type RevisionDetail,
  type RevisionSummary,
} from "@/lib/revisions";
import { getSectionDisplayName } from "@/components/blueprint/ai-actions";
import { Badge, Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";

interface RevisionHistoryPanelProps {
  projectId: number;
}

function shortValue(value: unknown, max = 160): string {
  if (value === undefined) return "undefined";
  let text = JSON.stringify(value);
  if (text === undefined) return String(value);
  if (text.length > max) text = `${text.slice(0, max)}…`;
  return text;
}

function DiffList({ changed }: { changed: DiffItem[] }) {
  const groups = useMemo(() => {
    const g: Record<DiffItem["op"], DiffItem[]> = { add: [], remove: [], change: [] };
    for (const item of changed) g[item.op].push(item);
    return g;
  }, [changed]);

  if (changed.length === 0) {
    return <p className="text-sm text-muted-foreground">No differences.</p>;
  }

  return (
    <div className="space-y-3">
      {groups.add.length > 0 && (
        <div>
          <p className="mb-1 text-xs font-semibold text-green-700">
            Added ({groups.add.length})
          </p>
          <ul className="space-y-1">
            {groups.add.map((item, i) => (
              <li key={i} className="rounded-md bg-green-50 px-3 py-1.5 text-xs">
                <span className="font-medium text-green-800">
                  + {diffPathLabel(item.path)}
                </span>
                <span className="text-green-700">: {shortValue(item.after)}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
      {groups.remove.length > 0 && (
        <div>
          <p className="mb-1 text-xs font-semibold text-red-700">
            Removed ({groups.remove.length})
          </p>
          <ul className="space-y-1">
            {groups.remove.map((item, i) => (
              <li key={i} className="rounded-md bg-red-50 px-3 py-1.5 text-xs">
                <span className="font-medium text-red-800">
                  − {diffPathLabel(item.path)}
                </span>
                <span className="text-red-700">: {shortValue(item.before)}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
      {groups.change.length > 0 && (
        <div>
          <p className="mb-1 text-xs font-semibold text-amber-700">
            Modified ({groups.change.length})
          </p>
          <ul className="space-y-1">
            {groups.change.map((item, i) => (
              <li key={i} className="rounded-md bg-amber-50 px-3 py-1.5 text-xs">
                <span className="font-medium text-amber-800">{diffPathLabel(item.path)}</span>
                <span className="text-amber-700">
                  : {shortValue(item.before)} → {shortValue(item.after)}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

export function RevisionDetailDialog({
  projectId,
  revision,
  open,
  onClose,
  title,
}: {
  projectId: number;
  revision: number;
  open: boolean;
  onClose: () => void;
  title?: string;
}) {
  const [detail, setDetail] = useState<RevisionDetail | null>(null);
  const [error, setError] = useState("");
  const [showRaw, setShowRaw] = useState(false);

  useEffect(() => {
    if (!open) return;
    setDetail(null);
    setError("");
    setShowRaw(false);
    fetchRevisionDetail(projectId, revision)
      .then(setDetail)
      .catch((err) =>
        setError(err instanceof ApiError ? err.detail : "Failed to load revision")
      );
  }, [projectId, revision, open]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      onClick={onClose}
    >
      <Card className="w-full max-w-2xl" onClick={(e) => e.stopPropagation()}>
        <CardContent className="space-y-4 py-6">
          <div className="flex items-start justify-between gap-4">
            <div className="flex items-center gap-3">
              <FileClock className="h-5 w-5 text-primary" />
              <div>
                <p className="text-lg font-semibold">
                  {title ?? `Revision ${revision}`}
                </p>
                {detail && (
                  <p className="text-sm text-muted-foreground">
                    {sourceActionLabel(detail.source_action)} ·{" "}
                    {getSectionDisplayName(detail.section)} ·{" "}
                    {new Date(detail.created_at).toLocaleString()}
                  </p>
                )}
              </div>
            </div>
            <Button variant="ghost" size="icon" onClick={onClose}>
              <X className="h-4 w-4" />
            </Button>
          </div>

          {error ? (
            <p className="text-sm text-destructive">{error}</p>
          ) : !detail ? (
            <p className="flex items-center gap-2 py-6 text-sm text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" /> Loading revision…
            </p>
          ) : (
            <>
              <div className="flex flex-wrap items-center gap-2">
                <Badge>Revision {detail.revision}</Badge>
                <Badge tone="info">{getSectionDisplayName(detail.section)}</Badge>
                {detail.applied_by !== null && <Badge>Applied by user #{detail.applied_by}</Badge>}
                {detail.action_result_id !== null && (
                  <Badge>Linked action result #{detail.action_result_id}</Badge>
                )}
              </div>

              {detail.summary.length > 0 && (
                <div className="rounded-md border border-border/60 bg-muted/30 p-3">
                  <p className="text-xs font-medium text-muted-foreground">What changed</p>
                  <ul className="mt-1 space-y-0.5 text-sm">
                    {detail.summary.map((line, i) => (
                      <li key={i}>{line}</li>
                    ))}
                  </ul>
                </div>
              )}

              <DiffList changed={detail.changed} />

              <div className="flex flex-wrap items-center justify-end gap-2 pt-2">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setShowRaw((v) => !v)}
                >
                  {showRaw ? "Hide raw JSON" : "View Raw JSON"}
                </Button>
                <Button variant="ghost" onClick={onClose}>
                  Close
                </Button>
              </div>

              {showRaw && (
                <div className="grid max-h-60 grid-cols-2 gap-3 overflow-auto">
                  <div className="rounded-md bg-muted/50 p-3 font-mono text-xs">
                    <p className="mb-1 font-sans font-medium text-muted-foreground">
                      Before (previous_section)
                    </p>
                    <pre>{JSON.stringify(detail.previous_section ?? {}, null, 2)}</pre>
                  </div>
                  <div className="rounded-md bg-muted/50 p-3 font-mono text-xs">
                    <p className="mb-1 font-sans font-medium text-muted-foreground">
                      After (current_section)
                    </p>
                    <pre>{JSON.stringify(detail.current_section ?? {}, null, 2)}</pre>
                  </div>
                </div>
              )}
            </>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function CompareDialog({
  projectId,
  revisions,
  initialFrom,
  initialTo,
  onClose,
}: {
  projectId: number;
  revisions: RevisionSummary[];
  initialFrom: number;
  initialTo: number;
  onClose: () => void;
}) {
  const [fromRev, setFromRev] = useState(initialFrom);
  const [toRev, setToRev] = useState(initialTo);
  const [compare, setCompare] = useState<RevisionCompare | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    setLoading(true);
    setError("");
    setCompare(null);
    compareRevisions(projectId, fromRev, toRev)
      .then(setCompare)
      .catch((err) =>
        setError(err instanceof ApiError ? err.detail : "Compare failed")
      )
      .finally(() => setLoading(false));
  }, [projectId, fromRev, toRev]);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      onClick={onClose}
    >
      <Card className="w-full max-w-3xl" onClick={(e) => e.stopPropagation()}>
        <CardContent className="space-y-4 py-6">
          <div className="flex items-start justify-between gap-4">
            <div className="flex items-center gap-3">
              <GitCompareArrows className="h-5 w-5 text-primary" />
              <div>
                <p className="text-lg font-semibold">Compare Revisions</p>
                <p className="text-sm text-muted-foreground">
                  See what changed between two points in the blueprint history.
                </p>
              </div>
            </div>
            <Button variant="ghost" size="icon" onClick={onClose}>
              <X className="h-4 w-4" />
            </Button>
          </div>

          <div className="flex flex-wrap items-center gap-3">
            <label className="flex items-center gap-2 text-sm">
              <span className="text-muted-foreground">From</span>
              <select
                value={fromRev}
                onChange={(e) => setFromRev(Number(e.target.value))}
                className="h-9 rounded-md border border-input bg-card px-2 text-sm"
              >
                {revisions.map((r) => (
                  <option key={r.revision} value={r.revision}>
                    Revision {r.revision} — {sourceActionLabel(r.source_action)}
                  </option>
                ))}
              </select>
            </label>
            <ArrowLeftRight className="h-4 w-4 text-muted-foreground" />
            <label className="flex items-center gap-2 text-sm">
              <span className="text-muted-foreground">To</span>
              <select
                value={toRev}
                onChange={(e) => setToRev(Number(e.target.value))}
                className="h-9 rounded-md border border-input bg-card px-2 text-sm"
              >
                {revisions.map((r) => (
                  <option key={r.revision} value={r.revision}>
                    Revision {r.revision} — {sourceActionLabel(r.source_action)}
                  </option>
                ))}
              </select>
            </label>
          </div>

          {error ? (
            <p className="text-sm text-destructive">{error}</p>
          ) : loading || !compare ? (
            <p className="flex items-center gap-2 py-6 text-sm text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" /> Comparing…
            </p>
          ) : (
            <div className="space-y-4">
              {compare.combined && (
                <div className="rounded-md border border-border/60 p-3">
                  <p className="mb-1 text-sm font-medium">
                    Net change from Revision {compare.from_revision.revision} to{" "}
                    {compare.to_revision.revision} (
                    {getSectionDisplayName(compare.combined.section)})
                  </p>
                  {compare.combined.summary.length > 0 ? (
                    <ul className="mb-2 space-y-0.5 text-sm">
                      {compare.combined.summary.map((line, i) => (
                        <li key={i}>{line}</li>
                      ))}
                    </ul>
                  ) : (
                    <p className="mb-2 text-sm text-muted-foreground">
                      No differences between these revisions.
                    </p>
                  )}
                  <DiffList changed={compare.combined.changed} />
                </div>
              )}

              <div className="grid gap-3 md:grid-cols-2">
                {[compare.from_revision, compare.to_revision].map((entry, i) => (
                  <div key={i} className="rounded-md border border-border/60 p-3">
                    <p className="mb-1 text-sm font-medium">
                      Revision {entry.revision} — {sourceActionLabel(entry.source_action)}
                      <span className="ml-1 text-xs font-normal text-muted-foreground">
                        ({getSectionDisplayName(entry.section)})
                      </span>
                    </p>
                    {entry.summary.length > 0 ? (
                      <ul className="mb-2 space-y-0.5 text-xs text-muted-foreground">
                        {entry.summary.map((line, j) => (
                          <li key={j}>{line}</li>
                        ))}
                      </ul>
                    ) : (
                      <p className="mb-2 text-xs text-muted-foreground">
                        This revision did not change its section.
                      </p>
                    )}
                    <DiffList changed={entry.changed} />
                  </div>
                ))}
              </div>
            </div>
          )}

          <div className="flex justify-end">
            <Button variant="ghost" onClick={onClose}>
              Close
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

function RestoreDialog({
  projectId,
  revision,
  currentRevision,
  onClose,
}: {
  projectId: number;
  revision: RevisionSummary;
  currentRevision: number;
  onClose: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [done, setDone] = useState<{ message: string; revision: number } | null>(null);

  const handleRestore = async () => {
    setBusy(true);
    setError("");
    try {
      const result = await restoreRevision(projectId, revision.revision, currentRevision);
      setDone({ message: result.message, revision: result.revision });
      window.dispatchEvent(new Event("blueprint-refresh"));
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Restore failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      onClick={onClose}
    >
      <Card className="w-full max-w-md" onClick={(e) => e.stopPropagation()}>
        <CardContent className="space-y-4 py-6">
          <div className="flex items-start justify-between gap-4">
            <div className="flex items-center gap-3">
              <RotateCcw className="h-5 w-5 text-primary" />
              <div>
                <p className="text-lg font-semibold">Restore Revision {revision.revision}</p>
                <p className="text-sm text-muted-foreground">
                  {sourceActionLabel(revision.source_action)} ·{" "}
                  {getSectionDisplayName(revision.section)}
                </p>
              </div>
            </div>
            <Button variant="ghost" size="icon" onClick={onClose}>
              <X className="h-4 w-4" />
            </Button>
          </div>

          {done ? (
            <>
              <div className="flex items-start gap-2 rounded-md border border-green-200 bg-green-50 p-3">
                <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-green-600" />
                <div>
                  <p className="text-sm font-medium text-green-800">Restored</p>
                  <p className="text-xs text-green-700">{done.message}</p>
                </div>
              </div>
              <div className="flex justify-end">
                <Button onClick={onClose}>Done</Button>
              </div>
            </>
          ) : (
            <>
              <p className="text-sm text-muted-foreground">
                This replaces the current{" "}
                <span className="font-medium">{getSectionDisplayName(revision.section)}</span>{" "}
                section with its state from Revision {revision.revision}. A new revision will be
                created on top of Revision {currentRevision} — nothing in the history is
                deleted.
              </p>
              {error && <p className="text-sm text-destructive">{error}</p>}
              <div className="flex justify-end gap-2">
                <Button variant="ghost" onClick={onClose}>
                  Cancel
                </Button>
                <Button onClick={() => void handleRestore()} loading={busy}>
                  <RotateCcw className="h-4 w-4" /> Restore Section
                </Button>
              </div>
            </>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

export function RevisionHistoryPanel({ projectId }: RevisionHistoryPanelProps) {
  const [items, setItems] = useState<RevisionSummary[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [detail, setDetail] = useState<RevisionSummary | null>(null);
  const [compare, setCompare] = useState<{ from: number; to: number } | null>(null);
  const [restore, setRestore] = useState<RevisionSummary | null>(null);

  const load = useCallback(async () => {
    try {
      const history = await fetchRevisionHistory(projectId, 50);
      setItems(history.items);
      setTotal(history.total);
    } catch {
      // Revision history is non-critical; fail silently on the panel.
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

  const openCompare = (item: RevisionSummary) => {
    const latest = items.length > 0 ? items[0].revision : item.revision;
    setCompare({ from: item.revision, to: latest });
  };

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2 text-base">
          <History className="h-4 w-4 text-primary" />
          Blueprint Revision History
          <Badge tone="info" className="ml-1">{total}</Badge>
        </CardTitle>
      </CardHeader>
      <CardContent className="pt-0">
        {loading ? (
          <p className="flex items-center gap-2 py-6 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" /> Loading revision history…
          </p>
        ) : items.length === 0 ? (
          <p className="py-6 text-sm text-muted-foreground">
            No revisions yet. Applying an action result to the blueprint creates one — with a
            safe snapshot you can view, compare and restore later.
          </p>
        ) : (
          <ul className="max-h-72 space-y-1.5 overflow-auto pr-1">
            {items.map((item) => (
              <li
                key={item.revision}
                className="flex flex-wrap items-center gap-2 rounded-md border border-border/60 bg-muted/30 px-3 py-2"
              >
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium">
                    Revision {item.revision} — {sourceActionLabel(item.source_action)}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    {new Date(item.created_at).toLocaleString()} ·{" "}
                    {getSectionDisplayName(item.section)}
                  </p>
                  {item.summary.length > 0 && (
                    <p className="mt-0.5 truncate text-xs text-muted-foreground">
                      {item.summary[0]}
                    </p>
                  )}
                </div>
                <Button size="sm" variant="outline" onClick={() => setDetail(item)}>
                  <FileClock className="h-3.5 w-3.5" /> View
                </Button>
                <Button size="sm" variant="outline" onClick={() => openCompare(item)}>
                  <GitCompareArrows className="h-3.5 w-3.5" /> Compare
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => setRestore(item)}
                  disabled={item.revision === items[0]?.revision}
                  title={
                    item.revision === items[0]?.revision
                      ? "The latest revision is already in effect"
                      : "Restore this revision's section"
                  }
                >
                  <RotateCcw className="h-3.5 w-3.5" /> Restore
                </Button>
              </li>
            ))}
          </ul>
        )}
      </CardContent>

      {detail && (
        <RevisionDetailDialog
          projectId={projectId}
          revision={detail.revision}
          open
          onClose={() => setDetail(null)}
        />
      )}
      {compare && (
        <CompareDialog
          projectId={projectId}
          revisions={items}
          initialFrom={compare.from}
          initialTo={compare.to}
          onClose={() => setCompare(null)}
        />
      )}
      {restore && (
        <RestoreDialog
          projectId={projectId}
          revision={restore}
          currentRevision={items[0]?.revision ?? restore.revision}
          onClose={() => setRestore(null)}
        />
      )}
    </Card>
  );
}