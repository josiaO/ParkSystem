"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { Receipt } from "@/lib/zirp";
import { STRINGS, fill, type Lang, type Strings } from "@/lib/i18n";
import { money, normaliseTzPhone, prettyPhone, when } from "@/lib/format";

/*
 * One-screen phone page: vehicle ticket, amount and the pay form fit a phone
 * screen without scrolling. After payment the page counts down the exit grace
 * period and shows the session QR as an exit pass for the exit scanner.
 */

type Flow = "idle" | "sending" | "waiting" | "success" | "failed" | "expired" | "mismatch";

// ids are the backend network codes (Flutterwave needs them; ClickPesa ignores them).
const NETWORKS = [
  { id: "vodacom", label: "M-Pesa", sub: "Vodacom", mark: "M", tone: "bg-red-600" },
  { id: "tigo", label: "Mixx by Yas", sub: "Yas", mark: "Y", tone: "bg-sky-600" },
  { id: "airtel", label: "Airtel Money", sub: "Airtel", mark: "A", tone: "bg-rose-500" },
  { id: "halopesa", label: "HaloPesa", sub: "Halotel", mark: "H", tone: "bg-orange-500" },
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

/** T626DXW -> "T 626 DXW"; anything else is shown as read. */
function platePretty(plate: string): string {
  const m = /^(T)(\d{3})([A-Z]{2,4})$/.exec(plate || "");
  return m ? `${m[1]} ${m[2]} ${m[3]}` : plate || "—";
}

function clock(seconds: number): string {
  const s = Math.max(0, Math.floor(seconds));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const pad = (n: number) => String(n).padStart(2, "0");
  return h > 0 ? `${h}:${pad(m)}:${pad(s % 60)}` : `${pad(m)}:${pad(s % 60)}`;
}

/** Seconds left of the exit grace, corrected for the phone clock being off. */
function useGraceLeft(receipt: Receipt): number | null {
  const offset = useMemo(() => {
    const server = receipt.server_time ? Date.parse(receipt.server_time) : NaN;
    return Number.isNaN(server) ? 0 : server - Date.now();
  }, [receipt.server_time]);
  const until = receipt.exit_grace_until ? Date.parse(receipt.exit_grace_until) : NaN;
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (Number.isNaN(until)) return;
    const id = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(id);
  }, [until]);
  if (Number.isNaN(until)) return null;
  return (until - (now + offset)) / 1000;
}

export default function ReceiptView({ initial, siteName, supportPhone }: { initial: Receipt; siteName: string; supportPhone: string }) {
  const [lang, setLang] = useState<Lang>("en");
  const t = STRINGS[lang];
  const [receipt, setReceipt] = useState<Receipt>(initial);
  const [flow, setFlow] = useState<Flow>(() => {
    const f = flowFromIntent(initial);
    return f === "failed" || f === "expired" ? "idle" : f;      // an old failure is not shown on reopen
  });
  const [phone, setPhone] = useState("");
  const [network, setNetwork] = useState(NETWORKS[0].id);
  const [error, setError] = useState("");
  const [sentTo, setSentTo] = useState("");
  const [showFees, setShowFees] = useState(false);
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
        if (current === "success" && !next.paid) return "idle";      // grace ran out and more is due
        if (current === "waiting") {
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
    const id = window.setInterval(refresh, flow === "waiting" ? 2500 : 20000);
    return () => window.clearInterval(id);
  }, [flow, refresh]);

  const normalised = useMemo(() => normaliseTzPhone(phone), [phone]);
  const testMode = ["MOCK", "SIMULATED"].includes(String(receipt.payment_mode || ""));
  const mobileReady = receipt.online_payment_available && String(receipt.pay_endpoint || "").startsWith("/api/public/");
  const noFee = receipt.paid && receipt.amount_due <= 0;
  const done = flow === "success" || receipt.paid;
  const busy = flow === "sending" || flow === "waiting";

  async function pay(e?: React.FormEvent) {
    e?.preventDefault();
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
    <div className="flex min-h-dvh flex-col">
      <header className="sticky top-0 z-10 bg-navy text-white shadow">
        <div className="mx-auto flex h-12 max-w-md items-center justify-between px-4">
          <div className="flex min-w-0 items-center gap-2">
            <img src="/zirp-logo.png" alt="" className="h-7 w-7 rounded-md bg-white/95 object-contain p-0.5" />
            <span className="truncate text-[15px] font-extrabold tracking-tight">{siteName}</span>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            {testMode ? (
              <span className="rounded bg-amber-400 px-1.5 py-0.5 text-[10px] font-extrabold text-navy" title={t.testMode}>TEST</span>
            ) : (
              <span className="rounded border border-white/20 bg-white/10 px-1.5 py-0.5 font-mono text-[10px]">{receipt.currency || "TZS"}</span>
            )}
            <div className="flex rounded-full bg-white/10 p-0.5 text-[10px] font-bold">
              {(["en", "sw"] as Lang[]).map((code) => (
                <button key={code} onClick={() => switchLang(code)}
                  className={`rounded-full px-2 py-0.5 transition ${lang === code ? "bg-white text-navy" : "text-white/70"}`}>
                  {code.toUpperCase()}
                </button>
              ))}
            </div>
          </div>
        </div>
      </header>

      <main className="mx-auto w-full max-w-md flex-1 space-y-2.5 px-4 py-2.5">
        <TicketCard t={t} receipt={receipt} paid={done} noFee={noFee} />

        {done ? (
          <ExitCard t={t} receipt={receipt} noFee={noFee} onRefresh={refresh} />
        ) : (
          <>
            <AmountBar t={t} receipt={receipt} open={showFees} onToggle={() => setShowFees((v) => !v)} />

            {flow === "waiting" ? (
              <WaitingCard t={t} phone={sentTo || receipt.intent?.phone || "—"} amount={money(receipt.amount_remaining, receipt.currency)} />
            ) : (
              <section className="card space-y-2.5 p-3.5">
                {(flow === "failed" || flow === "expired" || flow === "mismatch") && (
                  <div className={`rounded-lg border px-3 py-2 text-[11px] ${flow === "mismatch" ? "border-amber-200 bg-amber-50 text-amber-900" : "border-rose-200 bg-rose-50 text-rose-900"}`}>
                    <b className="block text-xs">{flow === "failed" ? t.failed : flow === "expired" ? t.expired : t.mismatch}</b>
                    {flow === "failed" ? t.failedHint : flow === "expired" ? t.expiredHint : t.mismatchHint}
                  </div>
                )}

                {mobileReady ? (
                  <form onSubmit={pay} className="space-y-2.5">
                    <div>
                      <div className="mb-1.5 text-[11px] font-bold uppercase tracking-wider text-muted">{t.payWith}</div>
                      <div className="grid grid-cols-2 gap-2">
                        {NETWORKS.map((n) => (
                          <button type="button" key={n.id} disabled={busy} onClick={() => setNetwork(n.id)}
                            className={`flex items-center gap-2 rounded-xl px-2.5 py-1.5 text-left transition ${
                              network === n.id ? "border-2 border-navy bg-brand-50" : "border border-line bg-white"}`}>
                            <span className={`grid h-6 w-6 shrink-0 place-items-center rounded text-[11px] font-bold text-white ${n.tone}`}>{n.mark}</span>
                            <span className="min-w-0">
                              <b className="block truncate text-xs leading-tight">{n.label}</b>
                              <span className="text-[9px] text-muted">{n.sub}</span>
                            </span>
                          </button>
                        ))}
                      </div>
                    </div>
                    <div>
                      <label className="mb-1 block text-[11px] font-bold text-ink" htmlFor="phone">{t.phone}</label>
                      <input id="phone" className="input py-2 font-mono font-bold" type="tel" inputMode="tel" autoComplete="tel"
                        placeholder="07XX XXX XXX" value={phone} disabled={busy}
                        onChange={(e) => { setPhone(e.target.value); setError(""); }} />
                    </div>
                    {error && <p className="rounded-lg bg-rose-50 px-3 py-1.5 text-[11px] text-rose-700">{error}</p>}
                    <button className="btn-primary py-2.5" disabled={busy || !phone}>
                      {flow === "sending" ? t.sending : `${t.proceed} · ${money(receipt.amount_remaining, receipt.currency)}`}
                    </button>
                  </form>
                ) : (
                  <p className="rounded-lg bg-surface p-3 text-xs">{t.unavailable}</p>
                )}
                {receipt.kiosk_payment_available && (
                  <p className="text-center text-[11px] text-muted">{t.orCash}</p>
                )}
              </section>
            )}
          </>
        )}
      </main>

      <footer className="px-4 pb-2 text-center text-[9px] leading-tight text-[#8a94a6]">
        {t.footer}
        {supportPhone && (
          <> · {t.help} <a href={`tel:${supportPhone}`} className="font-semibold text-brand-500">{supportPhone}</a></>
        )}
      </footer>
    </div>
  );
}

function TicketCard({ t, receipt, paid, noFee }: { t: Strings; receipt: Receipt; paid: boolean; noFee: boolean }) {
  const badge = noFee
    ? { text: t.chipFree, cls: "border-emerald-200 bg-emerald-50 text-ok" }
    : paid
      ? { text: t.paidBadge, cls: "border-emerald-200 bg-emerald-50 text-ok" }
      : { text: t.chipDue, cls: "border-amber-200 bg-amber-50 text-amber-700" };
  return (
    <section className="card space-y-2 p-3">
      <div className="flex items-center justify-between border-b border-line pb-1.5">
        <span className="font-mono text-xs font-bold text-ink">{receipt.reference || "—"}</span>
        <span className={`rounded-full border px-2 py-0.5 text-[10px] font-extrabold ${badge.cls}`}>{badge.text}</span>
      </div>
      <div className="flex gap-3">
        <div className="min-w-0 flex-1">
          <span className="block text-[10px] font-medium uppercase text-muted">{t.plateLabel}</span>
          <div className="mt-0.5 inline-block rounded-md bg-gradient-to-b from-yellow-300 to-yellow-500 px-2.5 py-0.5 font-mono text-base font-extrabold tracking-wider text-black shadow-[inset_0_0_0_2px_#000]">
            {platePretty(receipt.plate)}
          </div>
          <div className="mt-1.5 space-y-0.5 text-[11px] text-ink">
            {receipt.entry_gate && <div className="truncate">⌖ {receipt.entry_gate}</div>}
            <div>◷ {when(receipt.entry_time)}</div>
          </div>
        </div>
        <div className="w-[38%] shrink-0">
          {receipt.snapshot_url ? (
            <img src={receipt.snapshot_url} alt="" className="h-[76px] w-full rounded-lg border border-line bg-slate-900 object-cover object-[center_55%]" />
          ) : (
            <div className="grid h-[76px] place-items-center rounded-lg border border-dashed border-line bg-surface px-1 text-center text-[9px] text-muted">{t.photoMissing}</div>
          )}
        </div>
      </div>
      {receipt.duration_label && (
        <div className="flex items-center justify-between rounded-lg bg-surface px-2.5 py-1.5 text-[11px]">
          <span className="text-muted">{t.stay}</span>
          <b className="font-mono">{receipt.duration_label}</b>
        </div>
      )}
    </section>
  );
}

function AmountBar({ t, receipt, open, onToggle }: { t: Strings; receipt: Receipt; open: boolean; onToggle: () => void }) {
  const rows: [string, string | undefined][] = [
    [t.free, receipt.free_label],
    [t.chargeable, receipt.chargeable_label],
    [t.rate, receipt.rate_label],
    [t.paidSoFar, receipt.amount_paid > 0 ? money(receipt.amount_paid, receipt.currency) : undefined],
  ];
  return (
    <section className="card px-4 py-2">
      <button type="button" onClick={onToggle} className="flex w-full items-baseline justify-between text-left">
        <span className="text-xs font-bold text-ink">{t.total} <span className="font-normal text-muted">{open ? "▴" : "▾"}</span></span>
        <span className="font-mono text-xl font-extrabold text-navy">{money(receipt.amount_remaining, receipt.currency)}</span>
      </button>
      {open && (
        <div className="mt-2 space-y-1 border-t border-line pt-2 font-mono text-[11px]">
          {rows.filter(([, v]) => v).map(([label, value]) => (
            <div key={label} className="flex justify-between gap-2"><span className="text-muted">{label}</span><span>{value}</span></div>
          ))}
        </div>
      )}
    </section>
  );
}

// A USSD PIN prompt closes on the phone after about a minute and the
// provider then reports a failure. Past this, the answer is late or lost.
const SLOW_ANSWER_SECONDS = 120;

function WaitingCard({ t, phone, amount }: { t: Strings; phone: string; amount: string }) {
  const [started] = useState(() => Date.now());
  const [slow, setSlow] = useState(false);
  useEffect(() => {
    const id = window.setTimeout(() => setSlow(true), Math.max(0, SLOW_ANSWER_SECONDS * 1000 - (Date.now() - started)));
    return () => window.clearTimeout(id);
  }, [started]);
  return (
    <section className="card space-y-3 p-4 text-center">
      <span className="relative mx-auto grid h-9 w-9 place-items-center text-amber-500">
        <span className="pulse-ring absolute inset-0 rounded-full" />
        <span className="relative h-3.5 w-3.5 rounded-full bg-amber-500" />
      </span>
      <div>
        <h3 className="text-sm font-bold text-ink">{t.waiting}</h3>
        <p className="mt-1 text-xs text-muted">{fill(t.processing, { phone, amount })}</p>
      </div>
      <ol className="mx-auto w-fit space-y-1 text-left text-[11px]">
        <Step done label={t.stepSent} />
        <Step active label={t.stepApprove} />
        <Step label={t.stepConfirmed} />
      </ol>
      {slow && <p className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-left text-[11px] text-amber-900">{t.slowAnswer}</p>}
    </section>
  );
}

function ExitCard({ t, receipt, noFee, onRefresh }: { t: Strings; receipt: Receipt; noFee: boolean; onRefresh: () => void }) {
  const left = useGraceLeft(receipt);
  const over = left !== null && left <= 0;
  const viaMobile = receipt.intent?.status === "SUCCEEDED";
  return (
    <section className="card space-y-3 border-emerald-300 p-4">
      <div className="flex items-center gap-3">
        <span className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-emerald-100 text-lg font-black text-ok">✓</span>
        <div className="min-w-0">
          <h2 className="text-[15px] font-extrabold text-ink">{noFee ? t.noFee : t.successTitle}</h2>
          <p className="text-[11px] text-muted">
            {noFee ? t.gateboxFree : `${money(receipt.amount_paid, receipt.currency)}${viaMobile && receipt.intent?.reference ? ` · ${receipt.intent.reference}` : ""}`}
          </p>
        </div>
      </div>

      {left !== null && (
        <div className={`rounded-xl border px-3 py-2 text-center ${over ? "border-rose-200 bg-rose-50" : "border-emerald-200 bg-emerald-50"}`}>
          <span className={`block text-[10px] font-bold uppercase ${over ? "text-rose-700" : "text-emerald-800"}`}>{over ? t.graceOver : t.graceTitle}</span>
          <div className={`font-mono text-3xl font-extrabold tabular-nums ${over ? "text-rose-600" : "text-emerald-700"}`}>{clock(left)}</div>
          <span className="block text-[10px] text-muted">{over ? t.graceOverBody : t.graceBody}</span>
          {over && <button type="button" onClick={onRefresh} className="btn-ghost mt-1.5 px-3 py-1 text-xs">{t.refresh}</button>}
        </div>
      )}

      {receipt.qr_url && !over && (
        <div className="flex items-center gap-3 rounded-xl border border-line bg-white p-2.5">
          <img src={receipt.qr_url} alt="" className="h-[104px] w-[104px] shrink-0 rounded border border-line" />
          <div className="min-w-0">
            <b className="block text-xs uppercase text-ink">{t.passTitle}</b>
            <p className="mt-0.5 text-[11px] leading-snug text-muted">{t.passBody}</p>
            <span className="mt-1 block font-mono text-[11px] font-bold text-ink">{receipt.reference}</span>
          </div>
        </div>
      )}
    </section>
  );
}

function Step({ label, done, active }: { label: string; done?: boolean; active?: boolean }) {
  return (
    <li className="flex items-center gap-2">
      <span className={`grid h-4 w-4 place-items-center rounded-full text-[9px] font-bold ${
        done ? "bg-ok text-white" : active ? "bg-amber-500 text-white" : "bg-amber-200/70 text-transparent"}`}>{done ? "✓" : "•"}</span>
      <span className={done || active ? "font-semibold" : "opacity-70"}>{label}</span>
    </li>
  );
}
