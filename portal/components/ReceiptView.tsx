"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { Receipt } from "@/lib/zirp";
import { STRINGS, fill, type Lang, type Strings } from "@/lib/i18n";
import { money, normaliseTzPhone, prettyPhone, when } from "@/lib/format";

type Flow = "idle" | "sending" | "waiting" | "success" | "failed" | "expired" | "mismatch";
type Method = "mobile" | "cash";

// ids are the backend network codes (Flutterwave needs them; ClickPesa ignores them).
const NETWORKS = [
  { id: "vodacom", label: "M-Pesa", dot: "bg-red-600" },
  { id: "tigo", label: "Mixx by Yas", dot: "bg-sky-600" },
  { id: "airtel", label: "Airtel Money", dot: "bg-rose-500" },
  { id: "halopesa", label: "HaloPesa", dot: "bg-orange-500" },
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

export default function ReceiptView({ initial, siteName, supportPhone }: { initial: Receipt; siteName: string; supportPhone: string }) {
  const [lang, setLang] = useState<Lang>("en");
  const t = STRINGS[lang];
  const [receipt, setReceipt] = useState<Receipt>(initial);
  const [flow, setFlow] = useState<Flow>(() => {
    const f = flowFromIntent(initial);
    return f === "failed" || f === "expired" ? "idle" : f;      // an old failure is not shown on reopen
  });
  const [method, setMethod] = useState<Method>("mobile");
  const [phone, setPhone] = useState("");
  const [network, setNetwork] = useState(NETWORKS[0].id);
  const [error, setError] = useState("");
  const [sentTo, setSentTo] = useState("");
  const [showDetails, setShowDetails] = useState(false);
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
    const id = window.setInterval(refresh, flow === "waiting" ? 2500 : 20000);
    return () => window.clearInterval(id);
  }, [flow, refresh, receipt.paid]);

  const normalised = useMemo(() => normaliseTzPhone(phone), [phone]);
  const testMode = ["MOCK", "SIMULATED"].includes(String(receipt.payment_mode || ""));
  const mobileReady = receipt.online_payment_available && String(receipt.pay_endpoint || "").startsWith("/api/public/");
  const noFee = receipt.paid && receipt.amount_due <= 0;
  const done = flow === "success" || receipt.paid;
  const busy = flow === "sending" || flow === "waiting";

  async function pay(e?: React.FormEvent) {
    e?.preventDefault();
    if (method !== "mobile") return;
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

  const chip = noFee
    ? { text: t.chipFree, cls: "bg-[#e3f5eb] text-[#176b4b]" }
    : receipt.paid
      ? { text: t.chipPaid, cls: "bg-[#e3f5eb] text-[#176b4b]" }
      : { text: t.chipDue, cls: "bg-[#fff3db] text-[#98610b]" };

  return (
    <div className="min-h-dvh">
      <header className="border-b border-line bg-white">
        <div className="mx-auto flex h-16 w-[min(1080px,calc(100%-32px))] items-center justify-between sm:h-[72px]">
          <div className="flex items-center gap-2.5 text-lg font-extrabold text-navy sm:text-xl">
            <img src="/zirp-logo.png" alt="" className="h-10 w-10 object-contain" />
            <span className="truncate">{siteName}</span>
          </div>
          <div className="flex items-center gap-3">
            <span className="hidden text-xs text-muted sm:inline">✓&nbsp; {t.secure}</span>
            <div className="flex rounded-full border border-line bg-surface p-0.5 text-[11px] font-bold">
              {(["en", "sw"] as Lang[]).map((code) => (
                <button key={code} onClick={() => switchLang(code)}
                  className={`rounded-full px-2.5 py-1 transition ${lang === code ? "bg-navy text-white" : "text-muted"}`}>
                  {code.toUpperCase()}
                </button>
              ))}
            </div>
          </div>
        </div>
      </header>

      <main className="mx-auto w-[min(1080px,calc(100%-32px))] pb-14 pt-7 sm:pt-9">
        <section className="mb-6 text-center">
          <div className="eyebrow">{t.eyebrow}</div>
          <h1 className="my-2 text-[clamp(26px,4vw,36px)] font-extrabold leading-tight tracking-[-.04em] text-navy">
            {done ? (noFee ? t.noFee : t.paidTitle) : t.title}
          </h1>
          {!done && <p className="m-0 text-muted">{t.subtitle}</p>}
          {testMode && (
            <div className="mx-auto mt-4 max-w-md rounded-[10px] border border-amber-200 bg-amber-50 px-3 py-2 text-xs font-semibold text-amber-800">
              {t.testMode}
            </div>
          )}
        </section>

        {done ? (
          <SuccessCard t={t} receipt={receipt} noFee={noFee} onDetails={() => setShowDetails((v) => !v)} showDetails={showDetails} />
        ) : null}

        {(!done || showDetails) && (
          <div className={`grid items-start gap-5 ${done ? "mx-auto mt-5 max-w-[620px]" : "md:grid-cols-[1.08fr_.92fr]"}`}>
            <DetailsCard t={t} receipt={receipt} chip={chip} />

            {!done && (
              <section className="card">
                <div className="card-head"><h2>{t.payTitle}</h2></div>
                <div className="px-[22px] py-5">
                  <div className="mb-4 rounded-[10px] border border-[#dce7fb] bg-[#f0f5ff] p-3 text-xs text-[#405579]">
                    <b>{t.checkFirst}</b> {t.checkFirstBody}
                  </div>

                  {flow === "failed" || flow === "expired" || flow === "mismatch" ? (
                    <div className={`mb-4 rounded-[10px] border p-3 text-xs ${flow === "mismatch" ? "border-amber-200 bg-amber-50 text-amber-900" : "border-rose-200 bg-rose-50 text-rose-900"}`}>
                      <b className="block text-[13px]">{flow === "failed" ? t.failed : flow === "expired" ? t.expired : t.mismatch}</b>
                      {flow === "failed" ? t.failedHint : flow === "expired" ? t.expiredHint : t.mismatchHint}
                    </div>
                  ) : null}

                  <form onSubmit={pay}>
                    <div className="grid gap-[9px]">
                      <MethodOption checked={method === "mobile"} onChange={() => setMethod("mobile")} disabled={busy || !mobileReady}
                        icon="M" title={t.mobile} hint={mobileReady ? t.mobileHint : t.unavailable} />
                      {receipt.kiosk_payment_available && (
                        <MethodOption checked={method === "cash"} onChange={() => setMethod("cash")} disabled={busy}
                          icon="TZS" title={t.cash} hint={t.cashHint} />
                      )}
                    </div>

                    {method === "mobile" && mobileReady ? (
                      <>
                        <div className="mt-4">
                          <div className="mb-1.5 text-xs font-bold">{t.network}</div>
                          <div className="grid grid-cols-2 gap-2">
                            {NETWORKS.map((n) => (
                              <button type="button" key={n.id} disabled={busy} onClick={() => setNetwork(n.id)}
                                className={`flex items-center gap-2 rounded-[9px] border px-3 py-2 text-left text-[13px] font-semibold transition ${
                                  network === n.id ? "border-brand-500 bg-brand-50 ring-2 ring-brand-500/10" : "border-line bg-white"}`}>
                                <span className={`h-2 w-2 rounded-full ${n.dot}`} />{n.label}
                              </button>
                            ))}
                          </div>
                        </div>
                        <div className="mt-4">
                          <label className="mb-1.5 block text-xs font-bold" htmlFor="phone">{t.phone}</label>
                          <input id="phone" className="input" type="tel" inputMode="tel" autoComplete="tel" placeholder="e.g. 07XX XXX XXX"
                            value={phone} disabled={busy} onChange={(e) => { setPhone(e.target.value); setError(""); }} />
                          <div className="mt-1.5 text-[11px] text-muted">{t.phoneHint}</div>
                        </div>
                        {error && <p className="mt-3 rounded-[9px] bg-rose-50 px-3 py-2 text-xs text-rose-700">{error}</p>}
                        <button className="btn-primary mt-[17px]" disabled={busy || !phone}>
                          {flow === "sending" ? t.sending : flow === "waiting" ? t.waiting : `${t.proceed} · ${money(receipt.amount_remaining, receipt.currency)}`}
                        </button>
                      </>
                    ) : method === "cash" ? (
                      <p className="mt-4 rounded-[10px] bg-surface p-3 text-xs text-ink">{t.cashBody}</p>
                    ) : null}
                  </form>

                  {flow === "waiting" && (
                    <div className="mt-4 rounded-[10px] bg-[#fff7e8] p-3 text-xs text-[#8b5a0a]">
                      <div className="flex items-start gap-3">
                        <span className="relative mt-0.5 grid h-7 w-7 shrink-0 place-items-center text-amber-500">
                          <span className="pulse-ring absolute inset-0 rounded-full" />
                          <span className="relative h-3 w-3 rounded-full bg-amber-500" />
                        </span>
                        <p className="m-0">{fill(t.processing, { phone: sentTo || receipt.intent?.phone || "—", amount: money(receipt.amount_remaining, receipt.currency) })}</p>
                      </div>
                      <ol className="mt-3 space-y-1.5 pl-10">
                        <Step done label={t.stepSent} />
                        <Step active label={t.stepApprove} />
                        <Step label={t.stepConfirmed} />
                      </ol>
                    </div>
                  )}

                  {receipt.qr_url && (
                    <div className="mt-[17px] flex items-center gap-[13px] rounded-[11px] border border-dashed border-[#cbd5e4] p-[13px]">
                      <img src={receipt.qr_url} alt="" className="h-[68px] w-[68px] flex-none rounded border-4 border-white outline outline-1 outline-[#d9e0eb]" />
                      <div>
                        <b className="text-xs">{t.qrTitle}</b>
                        <p className="m-0 mt-0.5 text-[11px] text-muted">{t.qrBody}</p>
                      </div>
                    </div>
                  )}
                  <p className="mt-3 text-[11px] text-muted">{t.afterHint}</p>
                </div>
              </section>
            )}
          </div>
        )}

        <footer className="pt-6 text-center text-[11px] text-[#8a94a6]">
          {t.footer}
          {supportPhone && (
            <span className="block">{t.help} <a href={`tel:${supportPhone}`} className="font-semibold text-brand-500">{supportPhone}</a></span>
          )}
        </footer>
      </main>
    </div>
  );
}

function DetailsCard({ t, receipt, chip }: { t: Strings; receipt: Receipt; chip: { text: string; cls: string } }) {
  const rows: [string, string | undefined][] = [
    [t.reference, receipt.reference],
    [t.entered, when(receipt.entry_time)],
    [t.gate, receipt.entry_gate || undefined],
    [t.stay, receipt.duration_label],
    [t.free, receipt.free_label],
    [t.chargeable, receipt.chargeable_label],
    [t.rate, receipt.rate_label],
  ];
  return (
    <section className="card">
      <div className="card-head">
        <h2>{t.detailsTitle}</h2>
        <span className={`pill ${chip.cls}`}>{chip.text}</span>
      </div>
      <div className="px-[22px] py-5">
        {receipt.snapshot_url ? (
          <>
            <img src={receipt.snapshot_url} alt="" className="block h-[210px] w-full rounded-xl border border-line bg-[#e8edf5] object-cover object-[center_55%] sm:h-[230px]" />
            <div className="mb-[15px] mt-[7px] flex justify-between gap-2 text-[11px] text-muted">
              <span>{t.photoCaption}</span>
              <span className="font-bold text-ok">● {t.photoAvailable}</span>
            </div>
          </>
        ) : (
          <div className="mb-[15px] grid h-[120px] place-items-center rounded-xl border border-dashed border-line bg-surface text-xs text-muted">
            {t.photoMissing}
          </div>
        )}

        <div className="mb-[15px] flex items-center justify-between gap-3 rounded-[11px] border border-line bg-[#f6f8fc] px-3.5 py-3">
          <div className="min-w-0">
            <div className="text-[11px] text-muted">{t.plateLabel}</div>
            <div className="text-[23px] font-black tracking-[.07em] text-navy">{platePretty(receipt.plate)}</div>
          </div>
          <div className="flex flex-col items-end gap-1.5">
            {receipt.crop_url && <img src={receipt.crop_url} alt="" className="h-9 max-w-[120px] rounded border border-line object-contain" />}
            <span className="pill bg-[#e3f5eb] text-[10px] text-[#176b4b]">{t.plateTag}</span>
          </div>
        </div>

        <div className="grid">
          {rows.filter(([, v]) => v).map(([label, value]) => (
            <div key={label} className="flex justify-between gap-3 border-b border-[#edf0f5] py-2.5 last:border-0">
              <span className="text-xs text-muted">{label}</span>
              <b className="text-right text-xs">{value}</b>
            </div>
          ))}
        </div>

        <div className="mt-[13px] flex items-end justify-between border-t border-dashed border-[#d5deeb] pt-[15px]">
          <div>
            <small className="block text-xs text-muted">{t.total}</small>
            <strong className="text-[29px] font-extrabold tracking-[-.04em] text-navy">{money(receipt.amount_remaining, receipt.currency)}</strong>
          </div>
          {receipt.amount_paid > 0 && (
            <span className="text-right text-[11px] text-muted">{t.paidSoFar}<br /><b className="text-ink">{money(receipt.amount_paid, receipt.currency)}</b></span>
          )}
        </div>
      </div>
    </section>
  );
}

function SuccessCard({ t, receipt, noFee, onDetails, showDetails }: { t: Strings; receipt: Receipt; noFee: boolean; onDetails: () => void; showDetails: boolean }) {
  const viaMobile = receipt.intent?.status === "SUCCEEDED";
  const cells: [string, React.ReactNode][] = [
    [t.vehicleReg, platePretty(receipt.plate)],
    [t.amountPaid, money(receipt.amount_paid, receipt.currency)],
    [t.method, noFee ? "—" : viaMobile ? t.mobile : t.cash],
    [t.reference, receipt.reference || "—"],
    [t.txnRef, viaMobile ? receipt.intent?.reference || "—" : "—"],
    [t.status, <span key="s" className="text-ok">{noFee ? t.chipFree : t.statusPaid}</span>],
  ];
  return (
    <section className="card mx-auto max-w-[720px] p-6 text-center sm:p-8">
      <div className="mx-auto mb-3.5 grid h-[76px] w-[76px] place-items-center rounded-full bg-[#e1f5e9] text-[42px] font-black text-ok">✓</div>
      <h2 className="my-1 text-[29px] font-extrabold text-ok">{noFee ? t.noFee : t.successTitle}</h2>
      <p className="mx-0 mb-5 mt-1.5 text-muted">{noFee ? t.noFeeBody : t.successBody}</p>
      <div className="my-[18px] rounded-[11px] border border-[#ccebd8] bg-[#eaf7ef] p-3.5 font-bold text-[#176b45]">✓ &nbsp;{noFee ? t.gateboxFree : t.gatebox}</div>
      <div className="grid gap-2.5 rounded-[11px] border border-line bg-[#f6f8fc] p-[15px] text-left sm:grid-cols-3">
        {cells.map(([label, value]) => (
          <div key={label}>
            <span className="block text-[11px] text-muted">{label}</span>
            <b className="text-xs [overflow-wrap:anywhere]">{value}</b>
          </div>
        ))}
      </div>
      <p className="mt-[18px] text-sm text-muted">{t.exitNote}</p>
      <button className="btn-primary mt-2" onClick={onDetails}>{showDetails ? "✓" : t.details}</button>
    </section>
  );
}

function MethodOption({ checked, onChange, disabled, icon, title, hint }: {
  checked: boolean; onChange: () => void; disabled?: boolean; icon: string; title: string; hint: string;
}) {
  return (
    <label className={`flex cursor-pointer items-center gap-[11px] rounded-[11px] border p-3 transition ${
      checked ? "border-brand-500 bg-brand-50 shadow-[0_0_0_2px_rgba(36,84,166,.06)]" : "border-line"} ${disabled ? "cursor-not-allowed opacity-60" : ""}`}>
      <input type="radio" name="method" checked={checked} onChange={onChange} disabled={disabled} className="accent-brand-500" />
      <span className="grid h-[34px] w-[34px] shrink-0 place-items-center rounded-[9px] bg-[#edf2fa] text-[11px] font-black text-navy">{icon}</span>
      <span>
        <b className="block text-[13px]">{title}</b>
        <small className="block text-[11px] text-muted">{hint}</small>
      </span>
    </label>
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
