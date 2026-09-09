"use client";

import { FormEvent, useMemo, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { toErrorMessage } from "../../lib/api";
import { setAuthSession, type AuthUser } from "../../lib/auth";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

type Mode = "login" | "register";

type AuthResponse = {
  access_token: string;
  token_type: string;
  user: AuthUser;
};

export default function LoginForm() {
  const router = useRouter();
  const params = useSearchParams();
  const nextPath = useMemo(() => {
    const n = params.get("next") || "/";
    return n.startsWith("/") ? n : "/";
  }, [params]);

  const [mode, setMode] = useState<Mode>("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const path = mode === "login" ? "/auth/login" : "/auth/register";
      const body: Record<string, string> = { email: email.trim(), password };
      if (mode === "register" && name.trim()) body.name = name.trim();
      const res = await fetch(`${API_BASE}${path}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!res.ok) {
        let detail = `${res.status} ${res.statusText}`;
        try {
          const j = (await res.json()) as { detail?: string };
          if (j.detail) detail = j.detail;
        } catch {
          // ignore
        }
        throw new Error(detail);
      }
      const data = (await res.json()) as AuthResponse;
      setAuthSession(data.access_token, data.user);
      router.replace(nextPath);
    } catch (err) {
      setError(toErrorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="authPage">
      <div className="authCard">
        <h1>StudyFlows</h1>
        <p className="authLead">
          {mode === "login"
            ? "Sign in to your account. Each person has their own Canvas and courses."
            : "Create an account. New testers start empty — connect your own Canvas after sign-up."}
        </p>
        <div className="authTabs" role="tablist">
          <button
            type="button"
            className={mode === "login" ? "isActive" : undefined}
            onClick={() => setMode("login")}
          >
            Sign in
          </button>
          <button
            type="button"
            className={mode === "register" ? "isActive" : undefined}
            onClick={() => setMode("register")}
          >
            Create account
          </button>
        </div>
        <form className="authForm" onSubmit={onSubmit}>
          {mode === "register" ? (
            <label>
              Name
              <input value={name} onChange={(e) => setName(e.target.value)} autoComplete="name" />
            </label>
          ) : null}
          <label>
            Email
            <input
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              autoComplete="email"
            />
          </label>
          <label>
            Password
            <input
              type="password"
              required
              minLength={8}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete={mode === "login" ? "current-password" : "new-password"}
            />
          </label>
          {error ? <div className="authError">{error}</div> : null}
          <button type="submit" disabled={busy}>
            {busy ? "Please wait…" : mode === "login" ? "Sign in" : "Create account"}
          </button>
        </form>
        {mode === "register" ? (
          <p className="authHint">
            Already the original beta owner? Create account with <code>dev@example.com</code> once to claim
            your existing Canvas data, then sign in.
          </p>
        ) : null}
      </div>
    </main>
  );
}
