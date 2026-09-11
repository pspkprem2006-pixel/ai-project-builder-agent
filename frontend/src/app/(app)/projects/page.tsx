"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Copy, FileText, FolderKanban, Search, Trash2 } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { STATUS_LABEL, type ProjectListItem } from "@/lib/types";
import { formatDate } from "@/lib/utils";
import { Badge, Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { EmptyState, Spinner } from "@/components/ui/feedback";

export default function ProjectsPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [items, setItems] = useState<ProjectListItem[]>([]);
  const [total, setTotal] = useState(0);
  const [query, setQuery] = useState(searchParams.get("q") || "");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(
    async (q: string) => {
      setLoading(true);
      setError("");
      try {
        const data = await api.get<{ items: ProjectListItem[]; total: number }>(`/projects?q=${encodeURIComponent(q)}`);
        setItems(data.items);
        setTotal(data.total);
      } catch (err) {
        setError(err instanceof ApiError ? err.detail : "Failed to load projects");
      } finally {
        setLoading(false);
      }
    },
    []
  );

  useEffect(() => {
    load(query);
  }, [load, query]);

  const remove = async (id: number) => {
    if (!confirm("Delete this project and its blueprint?")) return;
    await api.del(`/projects/${id}`);
    load(query);
  };

  const duplicate = async (id: number) => {
    const copy = await api.post<{ id: number }>(`/projects/${id}/duplicate`);
    router.push(`/projects/${copy.id}`);
  };

  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
        <div>
          <h1 className="text-2xl font-bold">My Projects</h1>
          <p className="text-sm text-muted-foreground">{total} project{total === 1 ? "" : "s"}</p>
        </div>
        <Link href="/new-project">
          <Button>New Project</Button>
        </Link>
      </div>

      <div className="relative max-w-md">
        <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search by name, description or category..."
          className="h-10 w-full rounded-md border border-input bg-card pl-9 pr-3 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        />
      </div>

      {error && <p className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">{error}</p>}

      {loading ? (
        <Spinner label="Loading projects..." />
      ) : items.length === 0 ? (
        <EmptyState
          title={query ? "No matching projects" : "No projects yet"}
          description={query ? "Try a different search term." : "Create a project and generate its blueprint."}
          action={
            <Link href="/new-project">
              <Button>Create project</Button>
            </Link>
          }
        />
      ) : (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {items.map((project) => (
            <Card key={project.id} className="flex flex-col">
              <CardHeader>
                <div className="flex items-start justify-between gap-2">
                  <CardTitle className="line-clamp-1">{project.name}</CardTitle>
                  <Badge
                    tone={
                      project.status === "complete"
                        ? "success"
                        : project.status === "processing"
                          ? "warning"
                          : project.status === "failed"
                            ? "danger"
                            : "default"
                    }
                  >
                    {STATUS_LABEL[project.status]}
                  </Badge>
                </div>
                <p className="line-clamp-2 text-sm text-muted-foreground">
                  {project.description || "No description provided."}
                </p>
              </CardHeader>
              <CardContent className="flex flex-1 flex-col gap-3">
                <div className="flex flex-wrap gap-1.5">
                  <Badge tone="info">{project.category}</Badge>
                  <Badge>{project.preferred_backend}</Badge>
                  <Badge>{project.preferred_frontend}</Badge>
                  <Badge>{project.database}</Badge>
                </div>
                <p className="text-xs text-muted-foreground">Created {formatDate(project.created_at)}</p>
                <div className="mt-auto flex items-center gap-2 pt-2">
                  <Link href={`/projects/${project.id}`} className="flex-1">
                    <Button size="sm" className="w-full">
                      <FileText className="h-3.5 w-3.5" /> Open
                    </Button>
                  </Link>
                  <Button size="sm" variant="outline" onClick={() => duplicate(project.id)} title="Duplicate">
                    <Copy className="h-3.5 w-3.5" />
                  </Button>
                  <Button size="sm" variant="outline" onClick={() => remove(project.id)} title="Delete" className="text-destructive hover:text-destructive">
                    <Trash2 className="h-3.5 w-3.5" />
                  </Button>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {!loading && items.length > 0 && (
        <p className="flex items-center justify-center gap-2 text-sm text-muted-foreground">
          <FolderKanban className="h-4 w-4" /> Showing {items.length} of {total} projects
        </p>
      )}
    </div>
  );
}
