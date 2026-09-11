"use client";

import { useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import {
  ArrowLeft,
  ArrowRight,
  Boxes,
  Check,
  Database,
  Layers,
  Lock,
  Rocket,
  Settings2,
  Users,
  Wand2,
} from "lucide-react";
import { api, ApiError } from "@/lib/api";
import {
  AUTH_OPTIONS,
  BACKEND_OPTIONS,
  CATEGORY_OPTIONS,
  DATABASE_OPTIONS,
  DEPLOYMENT_OPTIONS,
  FRONTEND_OPTIONS,
  LANGUAGE_OPTIONS,
  type ProjectInput,
} from "@/lib/types";
import { cn } from "@/lib/utils";
import { Badge, Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Field, Input, Select, Textarea } from "@/components/ui/input";

const STEPS = [
  { title: "Project details", icon: Layers },
  { title: "Features", icon: Boxes },
  { title: "Technology stack", icon: Settings2 },
];

const DEFAULT_INPUT: ProjectInput = {
  name: "",
  description: "",
  category: "General",
  target_users: "",
  features: [],
  preferred_frontend: "Next.js",
  preferred_backend: "FastAPI",
  database: "PostgreSQL",
  auth_method: "JWT",
  deployment_platform: "Docker",
  language: "TypeScript",
};

function OptionPill({
  selected,
  onClick,
  children,
}: {
  selected: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "flex items-center gap-2 rounded-lg border px-3 py-2.5 text-sm font-medium transition-colors",
        selected
          ? "border-primary bg-primary/10 text-primary ring-1 ring-primary"
          : "border-input bg-card hover:border-primary/50"
      )}
    >
      {selected && <Check className="h-3.5 w-3.5" />}
      {children}
    </button>
  );
}

function StackGroup({ title, icon: Icon, options, value, onChange }: {
  title: string;
  icon: React.ElementType;
  options: string[];
  value: string;
  onChange: (v: string) => void;
}) {
  return (
    <div className="space-y-2">
      <p className="flex items-center gap-1.5 text-sm font-medium">
        <Icon className="h-4 w-4 text-muted-foreground" /> {title}
      </p>
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-4">
        {options.map((option) => (
          <OptionPill key={option} selected={value === option} onClick={() => onChange(option)}>
            {option}
          </OptionPill>
        ))}
      </div>
    </div>
  );
}

export default function NewProjectPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [step, setStep] = useState(0);
  const [input, setInput] = useState<ProjectInput>(DEFAULT_INPUT);
  const [feature, setFeature] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    const template = searchParams.get("template");
    if (template) {
      api
        .get<{ templates: ProjectInput[] }>("/projects/templates")
        .then((res) => {
          const found = res.templates.find((t) => t.name === template);
          if (found) setInput({ ...DEFAULT_INPUT, ...found });
        })
        .catch(() => undefined);
    }
  }, [searchParams]);

  const addFeature = () => {
    const value = feature.trim();
    if (!value) return;
    if (!input.features.includes(value)) setInput({ ...input, features: [...input.features, value] });
    setFeature("");
  };

  const removeFeature = (value: string) =>
    setInput({ ...input, features: input.features.filter((f) => f !== value) });

  const next = () => {
    setError("");
    if (step === 0 && !input.name.trim()) {
      setError("Project name is required.");
      return;
    }
    setStep((s) => Math.min(s + 1, STEPS.length - 1));
  };

  const generate = async () => {
    setBusy(true);
    setError("");
    try {
      const project = await api.post<{ id: number }>("/projects", input);
      await api.post(`/projects/${project.id}/generate`);
      router.push(`/projects/${project.id}`);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Failed to create project. Please try again.");
      setBusy(false);
    }
  };

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <div>
        <h1 className="text-2xl font-bold">New Project</h1>
        <p className="text-sm text-muted-foreground">
          Describe your idea — the multi-agent system will architect the entire project.
        </p>
      </div>

      <div className="flex items-center gap-2">
        {STEPS.map((s, i) => (
          <div key={s.title} className="flex flex-1 items-center gap-2">
            <div
              className={cn(
                "flex h-8 w-8 shrink-0 items-center justify-center rounded-full border text-xs font-semibold",
                i < step ? "border-accent bg-accent text-accent-foreground" : i === step ? "border-primary bg-primary text-primary-foreground" : "border-input text-muted-foreground"
              )}
            >
              {i < step ? <Check className="h-4 w-4" /> : i + 1}
            </div>
            <span className={cn("hidden text-xs font-medium sm:block", i === step ? "text-foreground" : "text-muted-foreground")}>
              {s.title}
            </span>
            {i < STEPS.length - 1 && <div className="h-px flex-1 bg-border" />}
          </div>
        ))}
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            {(() => {
              const StepIcon = STEPS[step].icon;
              return <StepIcon className="h-5 w-5 text-primary" />;
            })()}
            {STEPS[step].title}
          </CardTitle>
          <CardDescription>
            {step === 0 && "Tell us what you want to build. A clear description produces a better blueprint."}
            {step === 1 && "List the key capabilities the application must provide."}
            {step === 2 && "Choose the technology preferences. The AI will work within these choices."}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-5">
          {step === 0 && (
            <>
              <Field label="Project name" error={error || undefined}>
                <Input value={input.name} onChange={(e) => setInput({ ...input, name: e.target.value })} placeholder="e.g. Hospital Management System" />
              </Field>
              <Field label="Description" hint="What problem does it solve? Who uses it? What should it do?">
                <Textarea value={input.description} onChange={(e) => setInput({ ...input, description: e.target.value })} placeholder="Describe your project idea in detail..." />
              </Field>
              <div className="grid gap-4 sm:grid-cols-2">
                <Field label="Category">
                  <Select value={input.category} onChange={(e) => setInput({ ...input, category: e.target.value })}>
                    {CATEGORY_OPTIONS.map((c) => (
                      <option key={c}>{c}</option>
                    ))}
                  </Select>
                </Field>
                <Field label="Target users" hint="Comma separated">
                  <Input value={input.target_users} onChange={(e) => setInput({ ...input, target_users: e.target.value })} placeholder="Admins, doctors, patients" />
                </Field>
              </div>
            </>
          )}

          {step === 1 && (
            <>
              <div className="flex gap-2">
                <Input
                  value={feature}
                  onChange={(e) => setFeature(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && (e.preventDefault(), addFeature())}
                  placeholder="Add a feature, e.g. Appointment scheduling"
                />
                <Button type="button" variant="secondary" onClick={addFeature}>
                  Add
                </Button>
              </div>
              {input.features.length > 0 ? (
                <div className="flex flex-wrap gap-2">
                  {input.features.map((f) => (
                    <Badge key={f} className="cursor-pointer py-1.5 text-sm" onClick={() => removeFeature(f)}>
                      {f} ×
                    </Badge>
                  ))}
                </div>
              ) : (
                <p className="flex items-center gap-2 rounded-md bg-secondary/50 p-3 text-sm text-muted-foreground">
                  <Wand2 className="h-4 w-4" />
                  No features added — the AI will suggest core features automatically.
                </p>
              )}
            </>
          )}

          {step === 2 && (
            <div className="space-y-6">
              <StackGroup title="Frontend framework" icon={Layers} options={FRONTEND_OPTIONS} value={input.preferred_frontend} onChange={(v) => setInput({ ...input, preferred_frontend: v })} />
              <StackGroup title="Backend framework" icon={Settings2} options={BACKEND_OPTIONS} value={input.preferred_backend} onChange={(v) => setInput({ ...input, preferred_backend: v })} />
              <StackGroup title="Database" icon={Database} options={DATABASE_OPTIONS} value={input.database} onChange={(v) => setInput({ ...input, database: v })} />
              <StackGroup title="Authentication" icon={Lock} options={AUTH_OPTIONS} value={input.auth_method} onChange={(v) => setInput({ ...input, auth_method: v })} />
              <StackGroup title="Deployment platform" icon={Rocket} options={DEPLOYMENT_OPTIONS} value={input.deployment_platform} onChange={(v) => setInput({ ...input, deployment_platform: v })} />
              <StackGroup title="Primary language" icon={Users} options={LANGUAGE_OPTIONS} value={input.language} onChange={(v) => setInput({ ...input, language: v })} />
            </div>
          )}

          {error && step === 0 && <p className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">{error}</p>}

          <div className="flex items-center justify-between pt-2">
            <Button type="button" variant="ghost" onClick={() => setStep((s) => Math.max(0, s - 1))} disabled={step === 0}>
              <ArrowLeft className="h-4 w-4" /> Back
            </Button>
            {step < STEPS.length - 1 ? (
              <Button type="button" onClick={next}>
                Continue <ArrowRight className="h-4 w-4" />
              </Button>
            ) : (
              <Button type="button" onClick={generate} loading={busy}>
                <Wand2 className="h-4 w-4" /> Generate Blueprint
              </Button>
            )}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
