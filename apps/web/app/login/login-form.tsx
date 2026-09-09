"use client";

import { FormEvent, useState } from "react";
import { setAuthSession, type AuthUser } from "../../lib/auth";

type AuthResponse = {
  access_token: string;
  token_type: string;
  user: AuthUser;
};

function apiBase(): string {
  const configured = (process.env.NEXT_PUBLIC_API_BASE_URL || "").trim();
  if (configured.startsWith("http://") || configured.startsWith("https://")) return configured;
  if (typeof window !== "undefined") {
    const path = configured || "/backend";
    return `${window.location.origin}${path.startsWith("/") ? path : `/${path}`}`;
  }
  return configured || "http://localhost:8000";
}

async function postAuth(path: string, body: Record<string, string>): Promise<AuthResponse> {
  const res = await fetch(`${apiBase()}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  let detail = `${res.status} ${res.statusText}`;
  let data: AuthResponse | null = null;
  try {
    const j = await res.json();
    if (!res.ok) {
      if (typeof j?.detail === "string") detail = j.detail;
      throw new Error(detail);
    }
    data = j as AuthResponse;
  } catch (err) {
    if (!res.ok) throw err instanceof Error ? err : new Error(detail);
    throw err;
  }
  if (!data?.access_token) throw new Error("No access token returned");
  return data;
}

/**
 * Two independent forms — no tab state. Sign in and Create account both always work.
 */
export default function LoginForm() {
  const [loginEmail, setLoginEmail] = useState("");
  const [loginPassword, setLoginPassword] = useState("");
  const [regName, setRegName] = useState("");
  const [regEmail, setRegEmail] = useState("");
  const [regPassword, setRegPassword] = useState("");
  const [loginError, setLoginError] = useState<string | null>(null);
  const [regError, setRegError] = useState<string | null>(null);
  const [loginBusy, setLoginBusy] = useState(false);
  const [regBusy, setRegBusy] = useState(false);

  async function onSignIn(e: FormEvent) {
    e.preventDefault();
    setLoginBusy(true);
    setLoginError(null);
    try {
      const data = await postAuth("/auth/login", {
        email: loginEmail.trim(),
        password: loginPassword,
      });
      setAuthSession(data.access_token, data.user);
      window.location.href = "/";
    } catch (err) {
      setLoginError(err instanceof Error ? err.message : "Sign in failed");
    } finally {
      setLoginBusy(false);
    }
  }

  async function onRegister(e: FormEvent) {
    e.preventDefault();
    setRegBusy(true);
    setRegError(null);
    try {
      const body: Record<string, string> = {
        email: regEmail.trim(),
        password: regPassword,
      };
      if (regName.trim()) body.name = regName.trim();
      const data = await postAuth("/auth/register", body);
      setAuthSession(data.access_token, data.user);
      window.location.href = "/";
    } catch (err) {
      setRegError(err instanceof Error ? err.message : "Create account failed");
    } finally {
      setRegBusy(false);
    }
  }

  return (
    <main className="authPage">
      <div className="authCard">
        <h1>StudyFlows</h1>
        <p className="authLead">Sign in or create an account. Each person has their own Canvas and courses.</p>

        <form className="authForm" onSubmit={onSignIn}>
          <h2 className="authSectionTitle">Sign in</h2>
          <label>
            Email
            <input
              type="email"
              required
              name="login_email"
              value={loginEmail}
              onChange={(e) => setLoginEmail(e.target.value)}
              autoComplete="username"
            />
          </label>
          <label>
            Password
            <input
              type="password"
              required
              minLength={8}
              name="login_password"
              value={loginPassword}
              onChange={(e) => setLoginPassword(e.target.value)}
              autoComplete="current-password"
            />
          </label>
          {loginError ? <div className="authError">{loginError}</div> : null}
          <button type="submit" disabled={loginBusy}>
            {loginBusy ? "Please wait…" : "Sign in"}
          </button>
        </form>

        <hr className="authDivider" />

        <form className="authForm" onSubmit={onRegister}>
          <h2 className="authSectionTitle">Create account</h2>
          <label>
            Name
            <input
              name="reg_name"
              value={regName}
              onChange={(e) => setRegName(e.target.value)}
              autoComplete="name"
            />
          </label>
          <label>
            Email
            <input
              type="email"
              required
              name="reg_email"
              value={regEmail}
              onChange={(e) => setRegEmail(e.target.value)}
              autoComplete="email"
            />
          </label>
          <label>
            Password
            <input
              type="password"
              required
              minLength={8}
              name="reg_password"
              value={regPassword}
              onChange={(e) => setRegPassword(e.target.value)}
              autoComplete="new-password"
            />
          </label>
          {regError ? <div className="authError">{regError}</div> : null}
          <button type="submit" disabled={regBusy}>
            {regBusy ? "Please wait…" : "Create account"}
          </button>
        </form>
      </div>
    </main>
  );
}
