"use client";

import { useEffect, useState } from "react";
import { KeyRound, Save, UserRound } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { Badge, Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Field, Input } from "@/components/ui/input";

export default function SettingsPage() {
  const { user, refreshUser } = useAuth();
  const [fullName, setFullName] = useState(user?.full_name || "");
  const [email, setEmail] = useState(user?.email || "");
  const [newPassword, setNewPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    if (user) {
      setFullName(user.full_name);
      setEmail(user.email);
    }
  }, [user]);

  const saveProfile = async () => {
    setBusy(true);
    setMessage("");
    setError("");
    try {
      await api.put("/auth/me", { full_name: fullName });
      await refreshUser();
      setMessage("Profile updated.");
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Failed to update profile");
    } finally {
      setBusy(false);
    }
  };

  const changePassword = async () => {
    if (newPassword.length < 8) {
      setError("New password must be at least 8 characters.");
      return;
    }
    setBusy(true);
    setMessage("");
    setError("");
    try {
      await api.put("/auth/me", { password: newPassword });
      setNewPassword("");
      setMessage("Password updated.");
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Failed to update password");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Settings</h1>
        <p className="text-sm text-muted-foreground">Manage your profile and account security.</p>
      </div>

      {message && <p className="rounded-md bg-emerald-50 px-3 py-2 text-sm text-emerald-700">{message}</p>}
      {error && <p className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">{error}</p>}

      <Card>
        <CardHeader className="flex-row items-center justify-between space-y-0">
          <div>
            <CardTitle className="flex items-center gap-2">
              <UserRound className="h-4 w-4 text-primary" /> Profile
            </CardTitle>
            <CardDescription>Update your name and contact email.</CardDescription>
          </div>
          {user && <Badge tone="info">Member</Badge>}
        </CardHeader>
        <CardContent className="space-y-4">
          <Field label="Full name">
            <Input value={fullName} onChange={(e) => setFullName(e.target.value)} />
          </Field>
          <Field label="Email">
            <Input type="email" value={email} onChange={(e) => setEmail(e.target.value)} disabled />
          </Field>
          <Button onClick={saveProfile} loading={busy}>
            <Save className="h-4 w-4" /> Save profile
          </Button>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <KeyRound className="h-4 w-4 text-primary" /> Change password
          </CardTitle>
          <CardDescription>Use at least 8 characters with a mix of letters and numbers.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <Field label="New password">
            <Input type="password" value={newPassword} onChange={(e) => setNewPassword(e.target.value)} placeholder="••••••••" />
          </Field>
          <Button onClick={changePassword} loading={busy} variant="secondary">
            Update password
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}
