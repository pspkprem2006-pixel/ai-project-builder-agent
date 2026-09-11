"use client";

import { useEffect, useState } from "react";
import { Download, Package, X } from "lucide-react";
import { api, ApiError, downloadFile } from "@/lib/api";
import { Badge } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/feedback";

interface WorkspaceItem {
  id: string;
  label: string;
  href: string;
  filename: string;
  format: string;
  description?: string;
  category?: string;
}

interface WorkspaceGroup {
  id: string;
  label: string;
  description: string;
  items: WorkspaceItem[];
}

interface WorkspaceCatalog {
  project_id: number;
  project_name: string;
  zip_href: string;
  groups: WorkspaceGroup[];
}

const FORMAT_BADGES: Record<string, string> = {
  md: "markdown",
  json: "json",
  zip: "zip",
  pdf: "pdf",
  docx: "docx",
  mmd: "mermaid",
  csv: "csv",
};

export function DownloadCenterDialog({
  open,
  onOpenChange,
  projectId,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  projectId: number;
}) {
  const [catalog, setCatalog] = useState<WorkspaceCatalog | null>(null);
  const [error, setError] = useState("");
  const [busyId, setBusyId] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setCatalog(null);
    setError("");
    api
      .get<WorkspaceCatalog>(`/projects/${projectId}/workspace/artifacts`)
      .then(setCatalog)
      .catch((err) => setError(err instanceof ApiError ? err.detail : "Failed to load the download center"));
  }, [open, projectId]);

  if (!open) return null;

  const download = (item: WorkspaceItem) => {
    setBusyId(item.id);
    downloadFile(item.href, item.filename);
    setBusyId(null);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" onClick={() => onOpenChange(false)}>
      <div
        className="max-h-[90vh] w-full max-w-3xl overflow-y-auto rounded-lg border bg-card p-6 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-1 flex items-start justify-between gap-4">
          <div>
            <h2 className="flex items-center gap-2 text-lg font-semibold">
              <Package className="h-5 w-5" /> Download Center
            </h2>
            <p className="text-sm text-muted-foreground">
              Every generated asset for {catalog?.project_name ?? "this project"} — export them individually or as one ZIP.
            </p>
          </div>
          <Button variant="ghost" size="icon" onClick={() => onOpenChange(false)}>
            <X className="h-4 w-4" />
          </Button>
        </div>

        {error && <p className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">{error}</p>}

        {!catalog && !error && (
          <div className="py-10">
            <Spinner label="Loading assets..." />
          </div>
        )}

        {catalog && (
          <>
            <div className="my-4 flex flex-wrap items-center gap-3 rounded-lg bg-primary/5 px-4 py-3">
              <div className="min-w-0 flex-1">
                <p className="font-medium">Project ZIP — everything included</p>
                <p className="text-sm text-muted-foreground">
                  Blueprint, docs, diagrams, sprint board, database scripts, API collections and generated code, in one archive.
                </p>
              </div>
              <Button
                onClick={() =>
                  download({
                    id: "assets-zip",
                    label: "Project ZIP",
                    href: catalog.zip_href,
                    filename: `${slugify(catalog.project_name)}-assets.zip`,
                    format: "zip",
                  })
                }
                loading={busyId === "assets-zip"}
              >
                <Download className="h-4 w-4" /> Download ZIP
              </Button>
            </div>

            <div className="space-y-5">
              {catalog.groups.map((group) => (
                <section key={group.id}>
                  <h3 className="text-sm font-semibold">{group.label}</h3>
                  <p className="text-xs text-muted-foreground">{group.description}</p>
                  <div className="mt-2 grid gap-2 sm:grid-cols-2">
                    {group.items.map((item) => (
                      <div key={item.id} className="flex items-center justify-between gap-2 rounded-md border px-3 py-2">
                        <div className="min-w-0">
                          <p className="truncate text-sm font-medium">{item.label}</p>
                          {item.description && <p className="truncate text-xs text-muted-foreground">{item.description}</p>}
                        </div>
                        <div className="flex shrink-0 items-center gap-2">
                          <Badge>{FORMAT_BADGES[item.format] ?? item.format}</Badge>
                          <Button size="sm" variant="outline" onClick={() => download(item)} loading={busyId === item.id} title={`Download ${item.label}`}>
                            <Download className="h-3.5 w-3.5" />
                          </Button>
                        </div>
                      </div>
                    ))}
                  </div>
                </section>
              ))}
            </div>
          </>
        )}
      </div>
    </div>
  );
}

function slugify(name: string) {
  return name.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "") || "project";
}
