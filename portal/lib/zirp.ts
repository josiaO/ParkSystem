import "server-only";
import { cookies } from "next/headers";

/** Server-side access to the Zirp Site Service API. Never imported by client code. */

export const TOKEN_COOKIE = "zirp_token";

export function apiUrl(): string {
  return (process.env.ZIRP_API_URL || "http://127.0.0.1:8760").replace(/\/+$/, "");
}

export function siteName(): string {
  return process.env.ZIRP_SITE_NAME || "Zirp Parking";
}

export function supportPhone(): string {
  return process.env.ZIRP_SUPPORT_PHONE || "";
}

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

async function detail(res: Response): Promise<string> {
  try {
    const body = await res.json();
    return typeof body?.detail === "string" ? body.detail : JSON.stringify(body?.detail ?? body);
  } catch {
    return res.statusText || `HTTP ${res.status}`;
  }
}

/** GET/POST JSON from the API, optionally as the signed-in operator. */
export async function api<T>(path: string, init: RequestInit & { auth?: boolean } = {}): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("accept", "application/json");
  if (init.auth) {
    const token = (await cookies()).get(TOKEN_COOKIE)?.value;
    if (!token) throw new ApiError(401, "Not signed in");
    headers.set("authorization", `Bearer ${token}`);
  }
  let res: Response;
  try {
    res = await fetch(apiUrl() + path, { ...init, headers, cache: "no-store" });
  } catch {
    throw new ApiError(503, "The parking server is not reachable right now.");
  }
  if (!res.ok) throw new ApiError(res.status, await detail(res));
  return (await res.json()) as T;
}

const HOP_BY_HOP = new Set([
  "connection", "keep-alive", "transfer-encoding", "te", "trailer", "upgrade", "host", "content-length",
  "proxy-authorization", "proxy-authenticate",
]);

/**
 * Pass a request through to the API unchanged (method, raw body bytes, query).
 * Raw bytes matter: provider webhooks are verified with a checksum over the body.
 */
export async function proxy(req: Request, path: string, opts: { auth?: boolean } = {}): Promise<Response> {
  const url = new URL(req.url);
  const headers = new Headers();
  req.headers.forEach((value, key) => {
    if (!HOP_BY_HOP.has(key.toLowerCase()) && key.toLowerCase() !== "cookie") headers.set(key, value);
  });
  const forwardedFor = req.headers.get("x-forwarded-for");
  headers.set("x-forwarded-for", forwardedFor || "portal");
  headers.set("x-forwarded-host", url.host);
  headers.set("x-forwarded-proto", url.protocol.replace(":", ""));
  if (opts.auth) {
    const token = (await cookies()).get(TOKEN_COOKIE)?.value;
    if (!token) return Response.json({ detail: "Not signed in" }, { status: 401 });
    headers.set("authorization", `Bearer ${token}`);
  }
  const body = ["GET", "HEAD"].includes(req.method) ? undefined : await req.arrayBuffer();
  let upstream: Response;
  try {
    upstream = await fetch(apiUrl() + path + url.search, {
      method: req.method,
      headers,
      body,
      cache: "no-store",
      redirect: "manual",
    });
  } catch {
    return Response.json({ detail: "The parking server is not reachable right now." }, { status: 503 });
  }
  const out = new Headers();
  upstream.headers.forEach((value, key) => {
    if (!HOP_BY_HOP.has(key.toLowerCase()) && key.toLowerCase() !== "content-encoding") out.set(key, value);
  });
  return new Response(upstream.body, { status: upstream.status, headers: out });
}

// ---------------------------------------------------------------------------
// API shapes (the subset the portal uses)
// ---------------------------------------------------------------------------

export type PaymentIntent = {
  id: number;
  status: "CREATED" | "PENDING" | "SUCCEEDED" | "FAILED" | "EXPIRED" | "MISMATCH" | "BLOCKED" | string;
  amount: number;
  currency: string;
  phone?: string;
  provider_id?: string;
  error?: string;
  message?: string;
  created_at?: string;
  reference?: string;
  method?: string;
};

export type Receipt = {
  ok: boolean;
  token: string;
  plate: string;
  entry_gate: string | null;
  entry_time: string | null;
  exit_time: string | null;
  currency: string;
  amount_due: number;
  amount_paid: number;
  amount_remaining: number;
  payment_status: string;
  status: string;
  paid: boolean;
  payment_stage: string;
  online_payment_available: boolean;
  kiosk_payment_available: boolean;
  payable: boolean;
  can_exit: boolean;
  pay_blocked_reason?: string;
  qr_url?: string;
  image_note?: string;
  snapshot_url?: string | null;
  crop_url?: string | null;
  duration_label?: string;
  still_inside?: boolean;
  reference?: string;
  free_label?: string;
  chargeable_label?: string;
  rate_label?: string;
  paid_at?: string | null;
  exit_grace_until?: string | null;
  server_time?: string;
  mobile_provider?: string;
  payment_mode?: "MOCK" | "LIVE" | "LIVE_DISABLED" | "UNCONFIGURED" | "SIMULATED" | string;
  pay_endpoint?: string;
  intent?: PaymentIntent | null;
};

export type Dashboard = {
  cameras: number;
  sdk_connected: number;
  vehicles_inside: number;
  registered_plates: number;
  entries_today: number;
  exits_today: number;
  revenue_today: number;
  revenue_today_label: string;
  unpaid_active: number;
  subscribers_inside: number;
  alerts: string[];
  currency: string;
  timezone: string;
  lanes: { camera_id: number; label: string; lane: string; side: string; camera: string; live_video?: string }[];
};

export type SessionRow = {
  id: number;
  plate: string;
  gate_id: number | null;
  lane_direction: string;
  status: string;
  parker_kind: string;
  public_token: string;
  entry_time: string | null;
  exit_time: string | null;
  currency: string;
  amount_due: number;
  amount_paid: number;
  snapshot_url?: string | null;
  plate_confidence?: number | null;
};

export type Transaction = {
  id: number;
  intent_id: number | null;
  session_id: number | null;
  provider_id: string;
  method: string;
  amount: number;
  currency: string;
  status: string;
  provider_transaction_id: string;
  confirmed_at: string | null;
  created_at: string;
};

export type PaymentsHealth = {
  active_mobile_provider: string;
  reconcile_seconds: number;
  providers: Record<string, { mode?: string; available?: boolean; reason?: string; real_money?: boolean; base_url?: string }>;
  stats: Record<string, number | string | null>;
  pending_intents: number;
};

export type ReportSummary = {
  currency: string;
  start: string;
  end: string;
  entries: number;
  exits: number;
  still_inside: number;
  unpaid_casual: number;
  average_stay_seconds: number;
  collected: number;
  collected_label: string;
  by_method: { method: string; amount: number; count: number; label?: string }[];
  sections: { title: string; rows: { label: string; value: string }[] }[];
};

export type Me = { id: number; username: string; full_name: string; permissions: string[] };
