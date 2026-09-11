"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { ArrowRight, Sparkles } from "lucide-react";
import { api } from "@/lib/api";
import type { ProjectInput } from "@/lib/types";
import { Badge, Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/feedback";

export default function TemplatesPage() {
  const [templates, setTemplates] = useState<ProjectInput[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api
      .get<{ templates: ProjectInput[] }>("/projects/templates")
      .then((res) => setTemplates(res.templates))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <Spinner label="Loading templates..." />;

  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Templates</h1>
        <p className="text-sm text-muted-foreground">
          Kick off from a proven starting point — every template goes through the full multi-agent pipeline.
        </p>
      </div>

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {templates.map((template) => (
          <Card key={template.name} className="flex flex-col">
            <CardHeader>
              <div className="flex items-start justify-between gap-2">
                <CardTitle>{template.name}</CardTitle>
                <Badge tone="info">{template.category}</Badge>
              </div>
              <CardDescription className="line-clamp-3">{template.description}</CardDescription>
            </CardHeader>
            <CardContent className="flex flex-1 flex-col gap-3">
              <div className="flex flex-wrap gap-1.5">
                <Badge>{template.preferred_backend}</Badge>
                <Badge>{template.preferred_frontend}</Badge>
                <Badge>{template.database}</Badge>
                <Badge>{template.auth_method}</Badge>
              </div>
              <div className="mt-auto">
                <Link href={`/new-project?template=${encodeURIComponent(template.name)}`}>
                  <Button className="w-full" variant="accent">
                    <Sparkles className="h-4 w-4" /> Use template <ArrowRight className="h-3.5 w-3.5" />
                  </Button>
                </Link>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
