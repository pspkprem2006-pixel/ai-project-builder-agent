"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  ArrowRight,
  BarChart3,
  Clock,
  FileCheck2,
  FolderKanban,
  Layers,
  Lightbulb,
  Search,
  Sparkles,
  SquarePlus,
} from "lucide-react";
import { api, ApiError } from "@/lib/api";
import type { AISuggestion, ProjectListItem, ProjectStatistics } from "@/lib/types";
import { timeAgo } from "@/lib/utils";
import { Badge, Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { EmptyState, Spinner } from "@/components/ui/feedback";
import { STATUS_LABEL } from "@/lib/types";

export default function DashboardPage() {
  const [stats, setStats] = useState<ProjectStatistics | null>(null);
  const [recent, setRecent] = useState<ProjectListItem[]>([]);
  const [suggestions, setSuggestions] = useState<AISuggestion[]>([]);
  const [query, setQuery] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    Promise.all([
      api.get<ProjectStatistics>("/projects/statistics"),
      api.get<{ items: ProjectListItem[] }>("/projects?page=1&page_size=5"),
      api.get<AISuggestion[]>("/projects/suggestions"),
    ])
      .then(([stats, list, suggestions]) => {
        setStats(stats);
        setRecent(list.items);
        setSuggestions(suggestions);
      })
      .catch((err) => setError(err instanceof ApiError ? err.detail : "Failed to load dashboard"));
  }, []);

  const search = () => {
    window.location.href = `/projects?q=${encodeURIComponent(query)}`;
  };

  const kpis = stats
    ? [
        { label: "Total projects", value: stats.total_projects, icon: Layers },
        { label: "Blueprints ready", value: stats.completed, icon: FileCheck2 },
        { label: "Generating", value: stats.in_progress, icon: Clock },
        { label: "Drafts", value: stats.drafts, icon: BarChart3 },
      ]
    : [];

  return (
    <div className="mx-auto max-w-6xl space-y-8">
      <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
        <div>
          <h1 className="text-2xl font-bold">Dashboard</h1>
          <p className="text-sm text-muted-foreground">
            Plan, generate and manage professional software blueprints.
          </p>
        </div>
        <Link href="/new-project">
          <Button>
            <SquarePlus className="h-4 w-4" /> New Project
          </Button>
        </Link>
      </div>

      <div className="relative max-w-md">
        <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && search()}
          placeholder="Search projects..."
          className="h-10 w-full rounded-md border border-input bg-card pl-9 pr-3 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        />
      </div>

      {error && <p className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">{error}</p>}

      {!stats ? (
        <Spinner label="Loading dashboard..." />
      ) : (
        <>
          <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
            {kpis.map((kpi) => (
              <Card key={kpi.label}>
                <CardContent className="flex items-center gap-3 pt-6">
                  <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary/10 text-primary">
                    <kpi.icon className="h-5 w-5" />
                  </div>
                  <div>
                    <p className="text-2xl font-bold leading-none">{kpi.value}</p>
                    <p className="mt-1 text-xs text-muted-foreground">{kpi.label}</p>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>

          <div className="grid gap-6 lg:grid-cols-3">
            <div className="space-y-4 lg:col-span-2">
              <Card>
                <CardHeader className="flex-row items-center justify-between space-y-0">
                  <CardTitle>Recent projects</CardTitle>
                  <Link href="/projects" className="flex items-center gap-1 text-sm text-primary hover:underline">
                    View all <ArrowRight className="h-3.5 w-3.5" />
                  </Link>
                </CardHeader>
                <CardContent>
                  {recent.length === 0 ? (
                    <EmptyState
                      title="No projects yet"
                      description="Create your first project and let the AI agents build the blueprint."
                      action={
                        <Link href="/new-project">
                          <Button size="sm">Create your first project</Button>
                        </Link>
                      }
                    />
                  ) : (
                    <ul className="divide-y">
                      {recent.map((project) => (
                        <li key={project.id}>
                          <Link
                            href={`/projects/${project.id}`}
                            className="flex items-center justify-between gap-4 py-3 hover:bg-secondary/40"
                          >
                            <div className="min-w-0">
                              <p className="truncate font-medium">{project.name}</p>
                              <p className="truncate text-xs text-muted-foreground">
                                {project.preferred_backend} + {project.preferred_frontend} · {project.database}
                              </p>
                            </div>
                            <div className="flex shrink-0 items-center gap-2">
                              <span className="text-xs text-muted-foreground">{timeAgo(project.updated_at)}</span>
                              <Badge tone={project.status === "complete" ? "success" : project.status === "processing" ? "warning" : project.status === "failed" ? "danger" : "default"}>
                                {STATUS_LABEL[project.status]}
                              </Badge>
                            </div>
                          </Link>
                        </li>
                      ))}
                    </ul>
                  )}
                </CardContent>
              </Card>

              {stats.by_category && Object.keys(stats.by_category).length > 0 && (
                <Card>
                  <CardHeader>
                    <CardTitle>Projects by category</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="space-y-2">
                      {Object.entries(stats.by_category)
                        .slice(0, 5)
                        .map(([category, count]) => {
                          const max = Math.max(...Object.values(stats.by_category));
                          return (
                            <div key={category} className="flex items-center gap-3">
                              <span className="w-36 truncate text-sm">{category}</span>
                              <div className="h-2 flex-1 overflow-hidden rounded-full bg-secondary">
                                <div
                                  className="h-full rounded-full bg-primary"
                                  style={{ width: `${(count / max) * 100}%` }}
                                />
                              </div>
                              <span className="w-6 text-right text-sm font-medium">{count}</span>
                            </div>
                          );
                        })}
                    </div>
                  </CardContent>
                </Card>
              )}
            </div>

            <div className="space-y-4">
              <Card>
                <CardHeader className="flex-row items-center gap-2 space-y-0">
                  <Sparkles className="h-4 w-4 text-accent" />
                  <CardTitle className="text-base">AI Suggestions</CardTitle>
                </CardHeader>
                <CardContent className="space-y-3">
                  {suggestions.map((suggestion) => (
                    <div key={suggestion.title} className="rounded-lg border bg-secondary/40 p-3">
                      <p className="flex items-center gap-1.5 text-sm font-medium">
                        <Lightbulb className="h-3.5 w-3.5 text-amber-500" />
                        {suggestion.title}
                      </p>
                      <p className="mt-1 text-xs text-muted-foreground">{suggestion.detail}</p>
                    </div>
                  ))}
                </CardContent>
              </Card>

              {stats.by_stack && Object.keys(stats.by_stack).length > 0 && (
                <Card>
                  <CardHeader>
                    <CardTitle className="text-base">Preferred stacks</CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-2">
                    {Object.entries(stats.by_stack)
                      .slice(0, 5)
                      .map(([stack, count]) => (
                        <div key={stack} className="flex items-center justify-between text-sm">
                          <span className="flex items-center gap-2">
                            <FolderKanban className="h-3.5 w-3.5 text-muted-foreground" />
                            {stack}
                          </span>
                          <Badge>{count}</Badge>
                        </div>
                      ))}
                  </CardContent>
                </Card>
              )}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
