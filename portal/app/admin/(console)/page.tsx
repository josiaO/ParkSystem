import Link from "next/link";
import { api, type Dashboard, type PaymentsHealth, type Transaction } from "@/lib/zirp";
import { money, when } from "@/lib/format";
import { Badge, PageTitle, Stat } from "@/components/ui";

export const dynamic = "force-dynamic";

export default async function Overview() {
  const [dash, health, payments] = await Promise.all([
    api<Dashboard>("/dashboard", { auth: true }),
    api<PaymentsHealth>("/payments/health", { auth: true }).catch(() => null),
    api<Transaction[]>("/payments", { auth: true }).catch(() => [] as Transaction[]),
  ]);
  const provider = health?.active_mobile_provider || "—";
  const mode = health?.providers?.[provider]?.mode || (provider === "simulated" ? "SIMULATED" : "—");
  return (
    <>
      <PageTitle title="Overview" subtitle={`Today · ${dash.timezone}`} />
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat label="Revenue today" value={dash.revenue_today_label || money(dash.revenue_today, dash.currency)} tone="good" />
        <Stat label="Vehicles inside" value={dash.vehicles_inside} hint={`${dash.subscribers_inside} subscribers`} />
        <Stat label="Entries / exits" value={`${dash.entries_today} / ${dash.exits_today}`} />
        <Stat label="Unpaid inside" value={dash.unpaid_active} tone={dash.unpaid_active ? "warn" : "good"} />
      </div>

      <div className="mt-6 grid gap-4 lg:grid-cols-3">
        <section className="card p-5 lg:col-span-2">
          <div className="flex items-center justify-between">
            <h2 className="font-bold">Lanes</h2>
            <span className="text-xs text-muted">{dash.sdk_connected}/{dash.cameras} cameras connected</span>
          </div>
          <ul className="mt-3 divide-y divide-slate-100">
            {dash.lanes.map((lane) => (
              <li key={lane.camera_id} className="flex items-center justify-between py-2.5 text-sm">
                <span className="font-medium">{lane.label}</span>
                <span className="text-muted">{lane.camera}{lane.live_video ? ` · ${lane.live_video}` : ""}</span>
              </li>
            ))}
          </ul>
          {dash.alerts?.length > 0 && (
            <div className="mt-4 rounded-2xl bg-amber-50 p-3 text-sm text-amber-900">
              {dash.alerts.map((a) => (
                <div key={a}>• {a}</div>
              ))}
            </div>
          )}
        </section>

        <section className="card p-5">
          <h2 className="font-bold">Mobile payments</h2>
          <div className="mt-3 flex items-center gap-2 text-sm">
            <span className="capitalize">{provider}</span>
            <Badge value={mode} />
          </div>
          {mode === "MOCK" && <p className="mt-2 text-xs text-amber-700">Test provider: no real money moves.</p>}
          <dl className="mt-4 grid grid-cols-2 gap-3 text-sm">
            <div><dt className="text-xs text-muted">Pending</dt><dd className="text-lg font-bold">{health?.pending_intents ?? "—"}</dd></div>
            <div><dt className="text-xs text-muted">Credited</dt><dd className="text-lg font-bold">{String(health?.stats?.credited ?? "—")}</dd></div>
            <div><dt className="text-xs text-muted">Mismatches</dt><dd className="text-lg font-bold">{String(health?.stats?.mismatches ?? "—")}</dd></div>
            <div><dt className="text-xs text-muted">Reversals</dt><dd className="text-lg font-bold">{String(health?.stats?.reversals ?? 0)}</dd></div>
          </dl>
          <Link href="/admin/payments" className="btn-ghost mt-4 w-full">Open payments</Link>
        </section>
      </div>

      <section className="card mt-6 p-5">
        <h2 className="font-bold">Latest payments</h2>
        <ul className="mt-3 divide-y divide-slate-100 text-sm">
          {payments.slice(0, 6).map((p) => (
            <li key={p.id} className="flex items-center justify-between py-2.5">
              <span>{when(p.created_at)} · {p.method.replaceAll("_", " ")}</span>
              <span className="flex items-center gap-2 font-semibold">{money(p.amount, p.currency)} <Badge value={p.status} /></span>
            </li>
          ))}
          {payments.length === 0 && <li className="py-3 text-muted">No payments yet.</li>}
        </ul>
      </section>
    </>
  );
}
