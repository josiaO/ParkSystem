"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { Receipt } from "@/lib/zirp";
import { STRINGS, fill, type Lang } from "@/lib/i18n";
import { money, normaliseTzPhone, prettyPhone, when } from "@/lib/format";

type Flow = "idle" | "sending" | "waiting" | "success" | "failed" | "expired" | "mismatch";

// ids are the backend network codes (Flutterwave needs them; ClickPesa ignores them).
const NETWORKS = [
  { id: "vodacom", label: "M-Pesa", color: "bg-red-600" },
  { id: "tigo", label: "Mixx by Yas", color: "bg-sky-600" },
  { id: "airtel", label: "Airtel Money", color: "bg-rose-500" },
  { id: "halopesa", label: "HaloPesa", color: "bg-orange-500" },
];

function flowFromIntent(r: Receipt): Flow {
  if (r.paid && r.amount_remaining <= 0) return "success";
  switch (r.intent?.status) {
    case "PENDING":
    case "CREATED":
      return "waiting";
    case "FAILED":
    case "BLOCKED":
      return "failed";
    case "EXPIRED":
      return "expired";
    case "MISMATCH":
      return "mismatch";
    default:
      return "idle";
  }
}

export default function ReceiptView({
  initial,
  siteName,
  supportPhone,
}: {
  initial: Receipt;
  siteName: string;
  supportPhone: string;
}) {
  const [lang, setLang] = useState<Lang>("en");
  const t = STRINGS[lang];
  const [receipt, setReceipt] = useState<Receipt>(initial);
  const [flow, setFlow] = useState<Flow>(() => {
    const f = flowFromIntent(initial);
    return f === "failed" || f === "expired" ? "idle" : f;   // a past failure is not shown on reopen
  });
  const [phone, setPhone] = useState("");
  const [network, setNetwork] = useState(NETWORKS[0].id);
  const [error, setError] = useState("");
  const [sentTo, setSentTo] = useState("");
  const startedIntent = useRef<number | null>(null);

  useEffect(() => {
    const saved = window.localStorage.getItem("zirp-lang") as Lang | null;
    if (saved === "en" || saved === "sw") setLang(saved);
    else if (navigator.language?.toLowerCase().startsWith("sw")) setLang("sw");
    const savedPhone = window.localStorage.getItem("zirp-phone");
    if (savedPhone) setPhone(savedPhone);
  }, []);

  const switchLang = (next: Lang) => {
    setLang(next);
    window.localStorage.setItem("zirp-lang", next);
  };

  const refresh = useCallback(async () => {
    try {
      const res = await fetch(`/api/public/payment-status/${encodeURIComponent(receipt.token)}`, { cache: "no-store" });
      if (!res.ok) return;
      const next = (await res.json()) as Receipt;
      setReceipt(next);
      const f = flowFromIntent(next);
      setFlow((current) => {
        if (current === "sending") return current;
        if (f === "success") return "success";
        if (current === "waiting") {
          // Only report an outcome for the request this page sent.
          if (startedIntent.current !== null && next.intent?.id !== startedIntent.current) return current;
          return f === "idle" ? current : f;
        }
        return current === "idle" && f === "waiting" ? "waiting" : current;
      });
    } catch {
      /* offline for a moment: keep polling */
    }
  }, [receipt.token]);

  useEffect(() => {
    if (flow === "success" && receipt.paid) return;
    const every = flow === "waiting" ? 2500 : 20000;
    const id = window.setInterval(refresh, every);
    return () => window.clearInterval(id);
  }, [flow, refresh, receipt.paid]);

  const normalised = useMemo(() => normaliseTzPhone(phone), [phone]);
  const testMode = ["MOCK", "SIMULATED"].includes(String(receipt.payment_mode || ""));
  const mobileReady =
    receipt.online_payment_available && String(receipt.pay_endpoint || "").startsWith("/api/public/");
  const noFee = receipt.paid && receipt.amount_due <= 0;

  async function pay() {
    if (!normalised) {
      setError(t.phoneInvalid);
      return;
    }
    setError("");
    setFlow("sending");
    window.localStorage.setItem("zirp-phone", phone);
    try {
      const res = await fetch("/api/public/payment-intents", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ token: receipt.token, phone: normalised, network }),
      });
      const body = await res.json().catch(() => ({}));
      if (res.status === 429) {
        setFlow("idle");
        setError(fill(t.tooMany, { s: String(body.retry_after_seconds ?? 60) }));
        return;
      }
      if (!res.ok || body.ok === false) {
        setFlow("idle");
        setError(typeof body.detail === "string" ? body.detail : body.error || t.unavailable);
        return;
      }
      if (body.already_paid) {
        await refresh();
        setFlow("success");
        return;
      }
      startedIntent.current = body.intent?.id ?? null;
      setSentTo(prettyPhone(phone));
      setFlow("waiting");
    } catch {
      setFlow("idle");
      setError(t.offline);
    }
  }

  return (
    <div className="mx-auto flex min-h-dvh w-full max-w-md flex-col px-4 pb-10 pt-4">
      <header className="mb-4 flex items-center justify-between">
        <div className="flex items-center gap-2.5">
          <img src="/zirp-logo.png" alt="" className="h-9 w-9 rounded-xl bg-white object-contain p-1 shadow-sm" />
          <div className="leading-tight">
            <div className="text-[15px] font-bold">{siteName}</div>
            <div className="text-xs text-muted">{t.receipt}</div>
          </div>
        </div>
        <div className="flex rounded-full bg-white p-1 text-xs font-semibold shadow-sm">
          {(["en", "sw"] as Lang[]).map((code) => (
            <button
              key={code}
              onClick={() => switchLang(code)}
              className={`rounded-full px-3 py-1 transition ${lang === code ? "bg-brand-600 text-white" : "text-slate-500"}`}
            >
              {code === "en" ? "EN" : "SW"}
            </button>
          ))}
        </div>
      </header>

      {testMode && (
        <div className="mb-3 rounded-2xl border border-amber-300 bg-amber-50 px-4 py-2.5 text-sm font-medium text-amber-800">
          {t.testMode}
        </div>
      )}

      <section className="card overflow-hidden">
        <div className="bg-gradient-to-br from-brand-600 to-brand-900 px-5 pb-6 pt-5 text-white">
          <div className="flex items-start justify-between">
            <div>
              <div className="text-xs uppercase tracking-wider text-white/70">{t.plate}</div>
              <div className="mt-1 inline-block rounded-lg border-2 border-black/70 bg-amber-300 px-3 py-1 font-mono text-2xl font-extrabold tracking-[.12em] text-black shadow">
                {receipt.plate || "—"}
              </div>
            </div>
            <span className={`pill ${receipt.still_inside ? "bg-white/15 text-white" : "bg-emerald-400/20 text-emerald-100"}`}>
              {receipt.still_inside ? t.stillInside : t.visitDone}
            </span>
          </div>
          <div className="mt-5 text-xs uppercase tracking-wider text-white/70">
            {receipt.paid ? t.paid : t.remaining}
          </div>
          <div className="text-4xl font-extrabold tracking-tight">
            {money(receipt.paid ? receipt.amount_paid || receipt.amount_due : receipt.amount_remaining, receipt.currency)}
          </div>
        </div>
        <dl className="grid grid-cols-2 gap-px bg-slate-100 text-sm">
          {[
            [t.entered, when(receipt.entry_time)],
            [t.stay, receipt.duration_label || "—"],
            [t.gate, receipt.entry_gate || "—"],
            [t.due, money(receipt.amount_due, receipt.currency)],
          ].map(([label, value]) => (
            <div key={label} className="bg-white px-5 py-3.5">
              <dt className="text-xs text-muted">{label}</dt>
              <dd className="mt-0.5 font-semibold">{value}</dd>
            </div>
          ))}
        </dl>
      </section>

      <section className="mt-4">
        {flow === "success" || noFee ? (
          <Outcome
            tone="ok"
            title={noFee ? t.noFee : t.successTitle}
            body={noFee ? t.noFeeHint : fill(t.successHint, { plate: receipt.plate })}
          />
        ) : flow === "waiting" || flow === "sending" ? (
          <div className="card p-5">
            <div className="flex items-center gap-4">
              <div className="relative grid h-12 w-12 shrink-0 place-items-center text-brand-500">
                <span className="pulse-ring absolute inset-0 rounded-full" />
                <span className="relative grid h-12 w-12 place-items-center rounded-full bg-brand-600 text-white">
                  <PhoneIcon />
                </span>
              </div>
              <div>
                <div className="text-lg font-bold">{flow === "sending" ? t.sending : t.checkPhone}</div>
                {flow === "waiting" && (
                  <p className="text-sm text-muted">
                    {fill(t.checkPhoneHint, { phone: sentTo || "—", amount: money(receipt.amount_remaining, receipt.currency) })}
                  </p>
                )}
              </div>
            </div>
            <ol className="mt-5 space-y-3 text-sm">
              <Step done label={t.stepSent} />
              <Step active={flow === "waiting"} label={t.stepApprove} />
              <Step label={t.stepConfirmed} />
            </ol>
          </div>
        ) : mobileReady && receipt.payable ? (
          <div className="card p-5">
            {flow !== "idle" && (
              <Outcome
                tone={flow === "mismatch" ? "warn" : "bad"}
                title={flow === "failed" ? t.failed : flow === "expired" ? t.expired : t.mismatch}
                body={flow === "failed" ? t.failedHint : flow === "expired" ? t.expiredHint : t.mismatchHint}
                compact
              />
            )}
            <h2 className="text-lg font-bold">{t.payNow}</h2>
            <div className="mt-3 grid grid-cols-2 gap-2">
              {NETWORKS.map((n) => (
                <button
                  key={n.id}
                  onClick={() => setNetwork(n.id)}
                  className={`flex items-center gap-2 rounded-xl border px-3 py-2.5 text-left text-sm font-semibold transition ${
                    network === n.id ? "border-brand-500 bg-brand-50 ring-2 ring-brand-100" : "border-slate-200 bg-white"
                  }`}
                >
                  <span className={`h-2.5 w-2.5 rounded-full ${n.color}`} />
                  {n.label}
                </button>
              ))}
            </div>
            <label className="mt-4 block text-sm font-medium text-slate-700" htmlFor="phone">
              {t.phone}
            </label>
            <input
              id="phone"
              className="input mt-1.5"
              type="tel"
              inputMode="tel"
              autoComplete="tel"
              placeholder="0712 345 678"
              value={phone}
              onChange={(e) => {
                setPhone(e.target.value);
                setError("");
              }}
              onKeyDown={(e) => e.key === "Enter" && pay()}
            />
            <p className="mt-1.5 text-xs text-muted">{t.phoneHint}</p>
            {error && <p className="mt-3 rounded-xl bg-rose-50 px-3 py-2 text-sm text-rose-700">{error}</p>}
            <button className="btn-primary mt-4" onClick={pay} disabled={!phone}>
              {flow === "idle" ? `${t.pay} ${money(receipt.amount_remaining, receipt.currency)}` : t.tryAgain}
            </button>
            {receipt.kiosk_payment_available && <p className="mt-3 text-center text-xs text-muted">{t.payAtKiosk}</p>}
          </div>
        ) : (
          <Outcome tone="warn" title={t.unavailable} body={receipt.pay_blocked_reason || t.payAtKiosk} />
        )}
      </section>

      <footer className="mt-auto pt-8 text-center text-xs text-muted">
        <p>{t.photoNote}</p>
        {supportPhone && (
          <p className="mt-1">
            {t.help}{" "}
            <a className="font-semibold text-brand-600" href={`tel:${supportPhone}`}>
              {supportPhone}
            </a>
          </p>
        )}
      </footer>
    </div>
  );
}

function Step({ label, done, active }: { label: string; done?: boolean; active?: boolean }) {
  return (
    <li className="flex items-center gap-3">
      <span
        className={`grid h-6 w-6 place-items-center rounded-full text-xs font-bold ${
          done ? "bg-emerald-500 text-white" : active ? "bg-brand-600 text-white" : "bg-slate-200 text-slate-500"
        }`}
      >
        {done ? "✓" : active ? "…" : ""}
      </span>
      <span className={done || active ? "font-semibold" : "text-muted"}>{label}</span>
    </li>
  );
}

function Outcome({ tone, title, body, compact }: { tone: "ok" | "bad" | "warn"; title: string; body: string; compact?: boolean }) {
  const styles = {
    ok: "bg-emerald-50 text-emerald-900 border-emerald-200",
    bad: "bg-rose-50 text-rose-900 border-rose-200",
    warn: "bg-amber-50 text-amber-900 border-amber-200",
  }[tone];
  const icon = { ok: "✓", bad: "!", warn: "i" }[tone];
  const iconBg = { ok: "bg-emerald-500", bad: "bg-rose-500", warn: "bg-amber-500" }[tone];
  return (
    <div className={`${compact ? "mb-4 rounded-2xl p-3.5" : "card p-6"} border ${styles}`}>
      <div className="flex items-start gap-3">
        <span className={`grid ${compact ? "h-7 w-7" : "h-10 w-10 text-lg"} shrink-0 place-items-center rounded-full font-bold text-white ${iconBg}`}>
          {icon}
        </span>
        <div>
          <div className={`${compact ? "text-sm" : "text-lg"} font-bold`}>{title}</div>
          <p className={`${compact ? "text-xs" : "text-sm"} mt-0.5 opacity-80`}>{body}</p>
        </div>
      </div>
    </div>
  );
}

function PhoneIcon() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <rect x="6" y="2" width="12" height="20" rx="2.5" />
      <path d="M11 18h2" />
    </svg>
  );
}
