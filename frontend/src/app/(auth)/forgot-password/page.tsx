"use client";

import { useState } from "react";
import { MailCheck } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { AuthShell, FooterLink } from "@/components/auth-shell";
import { Button } from "@/components/ui/button";
import { Field, Input } from "@/components/ui/input";

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);
  const [devToken, setDevToken] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      const res = await api.post<{ detail: string; reset_token: string | null }>("/auth/forgot-password", { email });
      setSent(true);
      setDevToken(res.reset_token);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Something went wrong. Please try again.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <AuthShell
      title="Reset your password"
      description="Enter your email and we will send you a reset link."
      footer={
        <>
          Remembered it? <FooterLink href="/login">Log in</FooterLink>
        </>
      }
    >
      {sent ? (
        <div className="space-y-3">
          <div className="flex items-start gap-3 rounded-md bg-emerald-50 p-3 text-sm text-emerald-700">
            <MailCheck className="mt-0.5 h-4 w-4 shrink-0" />
            <p>If that email is registered, a password reset link has been sent. The link is valid for 1 hour.</p>
          </div>
          {devToken && (
            <div className="space-y-2">
              <p className="text-xs text-muted-foreground">
                Development mode (DEBUG=true, no SMTP): use this one-time token at the reset page.
              </p>
              <Input readOnly value={devToken} className="font-mono text-xs" />
              <FooterLink href={`/reset-password?token=${devToken}`}>Open reset page</FooterLink>
            </div>
          )}
        </div>
      ) : (
        <form onSubmit={submit} className="space-y-4">
          <Field label="Email">
            <Input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@example.com" />
          </Field>
          {error && <p className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">{error}</p>}
          <Button type="submit" className="w-full" loading={busy}>
            Send reset link
          </Button>
        </form>
      )}
    </AuthShell>
  );
}
