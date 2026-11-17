import { api, type PaymentsHealth, type Transaction } from "@/lib/zirp";
import { money, when } from "@/lib/format";
import { Badge, Empty, PageTitle, Stat } from "@/components/ui";
import { reconcileNow } from "../../actions";

export const dynamic = "force-dynamic";

export default async function Payments() {
  const [rows, health] = await Promise.all([
    api<Transaction[]>("/payments", { auth: true }),
    api<PaymentsHealth>("/payments/health", { auth: true }).catch(() => null),
  ]);
  const provider = health?.active_mobile_provider || "—";
  const info = health?.providers?.[provider];
  const total = rows.filter((r) => r.status === "SUCCEEDED").reduce((sum, r) => sum + Number(r.amount || 0), 0);
  return (
    <>
      <PageTitle title="Payments" subtitle="Ledger: every credited payment">
        <div className="flex gap-2">
          <a href="/api/zirp/reports/payments.csv" className="btn-ghost">Export CSV</a>
          <form action={reconcileNow}><button className="btn-ghost">Check pending now</button></form>
        </div>
      </PageTitle>
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat label="Provider" value={<span className="flex items-center gap-2 capitalize">{provider} <Badge value={info?.mode || (provider === "simulated" ? "SIMULATED" : "")} /></span>}
          hint={info?.mode === "MOCK" ? "Test provider: no real money" : info?.reason || undefined} />
        <Stat label="Pending prompts" value={health?.pending_intents ?? "—"} tone={health?.pending_intents ? "warn" : "default"} />
        <Stat label="Mismatch / reversal" value={`${health?.stats?.mismatches ?? 0} / ${health?.stats?.reversals ?? 0}`}
          tone={Number(health?.stats?.mismatches || 0) + Number(health?.stats?.reversals || 0) ? "bad" : "good"} hint="Need an operator" />
        <Stat label="Credited (listed)" value={money(total, rows[0]?.currency || "TZS")} tone="good" />
      </div>
      <div className="mt-6">
        {rows.length === 0 ? (
          <Empty text="No payments recorded yet." />
        ) : (
          <div className="card overflow-x-auto">
            <table className="w-full min-w-[720px] text-sm">
              <thead className="bg-slate-50 text-left text-xs uppercase tracking-wide text-muted">
                <tr>
                  <th className="px-4 py-3">When</th><th className="px-4 py-3">Session</th><th className="px-4 py-3">Method</th>
                  <th className="px-4 py-3">Provider</th><th className="px-4 py-3">Reference</th><th className="px-4 py-3">Status</th>
                  <th className="px-4 py-3 text-right">Amount</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {rows.map((r) => (
                  <tr key={r.id} className="hover:bg-slate-50">
                    <td className="px-4 py-2.5">{when(r.confirmed_at || r.created_at)}</td>
                    <td className="px-4 py-2.5">#{r.session_id ?? "—"}</td>
                    <td className="px-4 py-2.5">{r.method.replaceAll("_", " ")}</td>
                    <td className="px-4 py-2.5 capitalize">{r.provider_id.replaceAll("_", " ")}</td>
                    <td className="max-w-[200px] truncate px-4 py-2.5 font-mono text-xs text-muted">{r.provider_transaction_id}</td>
                    <td className="px-4 py-2.5"><Badge value={r.status} /></td>
                    <td className="px-4 py-2.5 text-right font-semibold">{money(r.amount, r.currency)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </>
  );
}
