"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { FileText, FileJson, FileArchive, FileDown } from "lucide-react";
import { api } from "@/lib/api";
import { downloadProject } from "@/lib/api";
import type { ProjectListItem } from "@/lib/types";
import { Badge, Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { EmptyState, Spinner } from "@/components/ui/feedback";

const EXPORTS = [
  { format: "markdown", label: "Markdown", description: "Single .md file with the full blueprint — perfect for docs and wikis.", icon: FileText },
  { format: "pdf", label: "PDF", description: "Print-ready professional document for stakeholders.", icon: FileDown },
  { format: "docx", label: "DOCX", description: "Editable Word document you can adapt and annotate.", icon: FileText },
  { format: "json", label: "JSON", description: "Machine-readable blueprint for tooling and pipelines.", icon: FileJson },
  { format: "zip", label: "ZIP starter kit", description: "Starter repository: docs, SQL schema, seed data, Docker assets and CI workflow.", icon: FileArchive },
];

export default function DocumentsPage() {
  const [projects, setProjects] = useState<ProjectListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<number | null>(null);

  useEffect(() => {
    api
      .get<{ items: ProjectListItem[] }>("/projects?page=1&page_size=50")
      .then((res) => setProjects(res.items))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <Spinner label="Loading documents..." />;

  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Documents & Exports</h1>
        <p className="text-sm text-muted-foreground">
          Export any generated blueprint in professional formats.
        </p>
      </div>

      {projects.length === 0 ? (
        <EmptyState
          title="Nothing to export yet"
          description="Generate a blueprint first, then export it in any format."
          action={
            <Link href="/new-project">
              <Button>Create a project</Button>
            </Link>
          }
        />
      ) : (
        <>
          <Card>
            <CardHeader>
              <CardTitle>1 · Choose a project</CardTitle>
              <CardDescription>Only projects with a generated blueprint can be exported.</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="grid gap-2 sm:grid-cols-2">
                {projects.map((project) => (
                  <button
                    key={project.id}
                    onClick={() => setSelected(project.id)}
                    className={`flex items-center justify-between gap-2 rounded-md border p-3 text-left text-sm transition-colors ${
                      selected === project.id ? "border-primary bg-primary/10 ring-1 ring-primary" : "hover:bg-secondary/60"
                    }`}
                  >
                    <span className="min-w-0">
                      <span className="block truncate font-medium">{project.name}</span>
                      <span className="block truncate text-xs text-muted-foreground">{project.preferred_backend} · {project.preferred_frontend}</span>
                    </span>
                    {project.status === "complete" ? (
                      <Badge tone="success">Ready</Badge>
                    ) : (
                      <Badge tone={project.status === "processing" ? "warning" : "default"}>
                        {project.status === "processing" ? "Generating..." : "No blueprint"}
                      </Badge>
                    )}
                  </button>
                ))}
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>2 · Choose a format</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                {EXPORTS.map((exp) => (
                  <button
                    key={exp.format}
                    disabled={!selected}
                    onClick={() => selected && downloadProject(selected, exp.format, "blueprint")}
                    className="group flex flex-col gap-2 rounded-lg border p-4 text-left transition-colors hover:border-primary/50 hover:bg-secondary/40 disabled:cursor-not-allowed disabled:opacity-40"
                  >
                    <exp.icon className="h-6 w-6 text-primary" />
                    <p className="font-medium">{exp.label}</p>
                    <p className="text-xs text-muted-foreground">{exp.description}</p>
                  </button>
                ))}
              </div>
              {!selected && <p className="mt-3 text-xs text-muted-foreground">Select a project to enable exports.</p>}
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}
