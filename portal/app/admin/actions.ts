"use server";

import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { revalidatePath } from "next/cache";
import { ApiError, TOKEN_COOKIE, api, apiUrl } from "@/lib/zirp";

export type LoginState = { error?: string };

export async function login(_: LoginState, formData: FormData): Promise<LoginState> {
  const username = String(formData.get("username") || "").trim();
  const password = String(formData.get("password") || "");
  if (!username || !password) return { error: "Enter your username and password." };
  let res: Response;
  try {
    res = await fetch(`${apiUrl()}/auth/login`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ username, password }),
      cache: "no-store",
    });
  } catch {
    return { error: "The parking server is not reachable." };
  }
  const body = await res.json().catch(() => ({}));
  if (!res.ok || !body.token) {
    return { error: typeof body.detail === "string" ? body.detail : "Wrong username or password." };
  }
  (await cookies()).set(TOKEN_COOKIE, body.token, {
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.ZIRP_SECURE_COOKIES === "true",
    path: "/",
    maxAge: 12 * 60 * 60,
  });
  redirect("/admin");
}

export async function logout() {
  const jar = await cookies();
  const token = jar.get(TOKEN_COOKIE)?.value;
  if (token) {
    await fetch(`${apiUrl()}/auth/logout`, { method: "POST", headers: { authorization: `Bearer ${token}` } }).catch(() => null);
  }
  jar.delete(TOKEN_COOKIE);
  redirect("/admin/login");
}

export async function reconcileNow(): Promise<void> {
  try {
    await api("/payments/reconcile", { method: "POST", auth: true });
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) redirect("/admin/login");
  }
  revalidatePath("/admin/payments");
}
