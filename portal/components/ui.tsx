export function Stat({ label, value, hint, tone = "default" }: { label: string; value: React.ReactNode; hint?: string; tone?: "default" | "good" | "warn" | "bad" }) {
  const accent = { default: "bg-brand-500", good: "bg-emerald-500", warn: "bg-amber-500", bad: "bg-rose-500" }[tone];
  return (
    <div className="card relative overflow-hidden p-5">
      <span className={`absolute inset-y-0 left-0 w-1 ${accent}`} />
      <div className="text-xs font-medium uppercase tracking-wide text-muted">{label}</div>
      <div className="mt-1.5 text-2xl font-extrabold tracking-tight">{value}</div>
      {hint && <div className="mt-1 text-xs text-muted">{hint}</div>}
    </div>
  );
}

const TONES: Record<string, string> = {
  SUCCEEDED: "bg-emerald-100 text-emerald-800",
  PAID: "bg-emerald-100 text-emerald-800",
  CLOSED: "bg-slate-100 text-slate-700",
  ACTIVE: "bg-brand-100 text-brand-700",
  WAITING_RECEIPT: "bg-amber-100 text-amber-800",
  PENDING: "bg-amber-100 text-amber-800",
  FAILED: "bg-rose-100 text-rose-800",
  MISMATCH: "bg-rose-100 text-rose-800",
  EXPIRED: "bg-slate-200 text-slate-600",
  MOCK: "bg-amber-100 text-amber-800",
  LIVE: "bg-emerald-100 text-emerald-800",
  SIMULATED: "bg-amber-100 text-amber-800",
};

export function Badge({ value }: { value: string | null | undefined }) {
  const text = String(value || "—");
  return <span className={`pill ${TONES[text] || "bg-slate-100 text-slate-700"}`}>{text.replaceAll("_", " ")}</span>;
}

export function PageTitle({ title, subtitle, children }: { title: string; subtitle?: string; children?: React.ReactNode }) {
  return (
    <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 className="text-2xl font-extrabold tracking-tight">{title}</h1>
        {subtitle && <p className="text-sm text-muted">{subtitle}</p>}
      </div>
      {children}
    </div>
  );
}

export function Empty({ text }: { text: string }) {
  return <div className="card p-10 text-center text-sm text-muted">{text}</div>;
}
