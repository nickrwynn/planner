"use client";

import { Suspense } from "react";
import LoginForm from "./login-form";

export default function LoginPage() {
  return (
    <Suspense fallback={<main className="authPage"><div className="authCard">Loading…</div></main>}>
      <LoginForm />
    </Suspense>
  );
}
