"use client";

import { useActionState } from "react";
import { login, type LoginState } from "../actions";

export default function LoginPage() {
  const [state, action, pending] = useActionState<LoginState, FormData>(login, {});
  return (
    <main className="flex min-h-dvh items-center justify-center bg-gradient-to-br from-brand-900 via-brand-700 to-brand-500 px-5">
      <form action={action} className="card w-full max-w-sm space-y-4 p-7">
        <div className="flex items-center gap-3">
          <img src="/zirp-logo.png" alt="" className="h-10 w-10 rounded-xl bg-white p-1 shadow" />
          <div>
            <h1 className="text-lg font-bold">Back office</h1>
            <p className="text-xs text-muted">Sign in with your Zirp account</p>
          </div>
        </div>
        <div>
          <label className="text-sm font-medium text-slate-700" htmlFor="username">Username</label>
          <input id="username" name="username" className="input mt-1 py-3 text-base" autoComplete="username" required />
        </div>
        <div>
          <label className="text-sm font-medium text-slate-700" htmlFor="password">Password</label>
          <input id="password" name="password" type="password" className="input mt-1 py-3 text-base" autoComplete="current-password" required />
        </div>
        {state.error && <p className="rounded-xl bg-rose-50 px-3 py-2 text-sm text-rose-700">{state.error}</p>}
        <button className="btn-primary" disabled={pending}>{pending ? "Signing in…" : "Sign in"}</button>
      </form>
    </main>
  );
}
