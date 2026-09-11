"use client";

import { useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { type Project, type ProjectInput } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Field, Input, Select, Textarea } from "@/components/ui/input";

export function EditProjectDialog({
  open,
  onOpenChange,
  project,
  onSaved,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  project: Project;
  onSaved: (updated: Project) => void;
}) {
  const [form, setForm] = useState<ProjectInput>({
    name: project.name,
    description: project.description,
    category: project.category,
    target_users: project.target_users,
    features: project.features,
    preferred_frontend: project.preferred_frontend,
    preferred_backend: project.preferred_backend,
    database: project.database,
    auth_method: project.auth_method,
    deployment_platform: project.deployment_platform,
    language: project.language,
  });
  const [feature, setFeature] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (open) {
      setForm({
        name: project.name,
        description: project.description,
        category: project.category,
        target_users: project.target_users,
        features: project.features,
        preferred_frontend: project.preferred_frontend,
        preferred_backend: project.preferred_backend,
        database: project.database,
        auth_method: project.auth_method,
        deployment_platform: project.deployment_platform,
        language: project.language,
      });
      setError("");
    }
  }, [open, project]);

  if (!open) return null;

  const save = async () => {
    setBusy(true);
    setError("");
    try {
      const updated = await api.put<Project>(`/projects/${project.id}`, form);
      onSaved(updated);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Failed to save");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" onClick={() => onOpenChange(false)}>
      <div
        className="max-h-[90vh] w-full max-w-2xl overflow-y-auto rounded-lg border bg-card p-6 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 className="text-lg font-semibold">Edit project</h2>
        <p className="mb-4 text-sm text-muted-foreground">Changes apply when you regenerate the blueprint.</p>
        <div className="space-y-4">
          <Field label="Project name">
            <Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
          </Field>
          <Field label="Description">
            <Textarea value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />
          </Field>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Category">
              <Input value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })} />
            </Field>
            <Field label="Target users">
              <Input value={form.target_users} onChange={(e) => setForm({ ...form, target_users: e.target.value })} />
            </Field>
            <Field label="Frontend">
              <Select value={form.preferred_frontend} onChange={(e) => setForm({ ...form, preferred_frontend: e.target.value })}>
                {["Next.js", "React", "Angular", "Vue"].map((o) => <option key={o}>{o}</option>)}
              </Select>
            </Field>
            <Field label="Backend">
              <Select value={form.preferred_backend} onChange={(e) => setForm({ ...form, preferred_backend: e.target.value })}>
                {["FastAPI", "Django", "Node.js", "Spring Boot"].map((o) => <option key={o}>{o}</option>)}
              </Select>
            </Field>
            <Field label="Database">
              <Select value={form.database} onChange={(e) => setForm({ ...form, database: e.target.value })}>
                {["PostgreSQL", "MySQL", "MongoDB"].map((o) => <option key={o}>{o}</option>)}
              </Select>
            </Field>
            <Field label="Authentication">
              <Select value={form.auth_method} onChange={(e) => setForm({ ...form, auth_method: e.target.value })}>
                {["JWT", "OAuth", "Firebase"].map((o) => <option key={o}>{o}</option>)}
              </Select>
            </Field>
          </div>
          <Field label="Features">
            <div className="flex gap-2">
              <Input
                value={feature}
                onChange={(e) => setFeature(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && (e.preventDefault(), setForm({ ...form, features: [...form.features, feature.trim()] }), setFeature(""))}
                placeholder="Add feature"
              />
              <Button
                type="button"
                variant="secondary"
                onClick={() => {
                  if (feature.trim()) {
                    setForm({ ...form, features: [...form.features, feature.trim()] });
                    setFeature("");
                  }
                }}
              >
                Add
              </Button>
            </div>
            <div className="mt-2 flex flex-wrap gap-1.5">
              {form.features.map((f) => (
                <button
                  key={f}
                  type="button"
                  onClick={() => setForm({ ...form, features: form.features.filter((x) => x !== f) })}
                  className="rounded-full bg-secondary px-2.5 py-0.5 text-xs hover:bg-destructive/10 hover:text-destructive"
                >
                  {f} ×
                </button>
              ))}
            </div>
          </Field>
          {error && <p className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">{error}</p>}
          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button onClick={save} loading={busy}>
              Save changes
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
