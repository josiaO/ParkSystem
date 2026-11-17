import { api, type SessionRow } from "@/lib/zirp";
import { money, when } from "@/lib/format";
import { Badge, Empty, PageTitle } from "@/components/ui";

export const dynamic = "force-dynamic";

export default async function Sessions({ searchParams }: { searchParams: Promise<{ q?: string; status?: string }> }) {
  const { q = "", status = "" } = await searchParams;
  const rows = await api<SessionRow[]>("/sessions", { auth: true });
  const needle = q.trim().toUpperCase().replace(/[^A-Z0-9]/g, "");
  const shown = rows.filter(
    (r) => (!needle || r.plate.toUpperCase().includes(needle)) && (!status || r.status === status),
  );
  const statuses = Array.from(new Set(rows.map((r) => r.status))).sort();
  return (
    <>
      <PageTitle title="Sessions" subtitle="The latest 100 visits">
        <form className="flex gap-2">
          <input name="q" defaultValue={q} placeholder="Plate" className="input w-36 py-2 text-sm" />
          <select name="status" defaultValue={status} className="input w-44 py-2 text-sm">
            <option value="">All statuses</option>
            {statuses.map((s) => <option key={s} value={s}>{s.replaceAll("_", " ")}</option>)}
          </select>
          <button className="btn-ghost">Filter</button>
        </form>
      </PageTitle>
      {shown.length === 0 ? (
        <Empty text="No sessions match." />
      ) : (
        <div className="card overflow-x-auto">
          <table className="w-full min-w-[720px] text-sm">
            <thead className="bg-slate-50 text-left text-xs uppercase tracking-wide text-muted">
              <tr>
                <th className="px-4 py-3">Plate</th><th className="px-4 py-3">Entered</th><th className="px-4 py-3">Exited</th>
                <th className="px-4 py-3">Kind</th><th className="px-4 py-3">Status</th><th className="px-4 py-3 text-right">Due</th>
                <th className="px-4 py-3 text-right">Paid</th><th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {shown.map((r) => (
                <tr key={r.id} className="hover:bg-slate-50">
                  <td className="px-4 py-2.5 font-mono font-bold">{r.plate}</td>
                  <td className="px-4 py-2.5">{when(r.entry_time)}</td>
                  <td className="px-4 py-2.5">{when(r.exit_time)}</td>
                  <td className="px-4 py-2.5 text-muted">{r.parker_kind}</td>
                  <td className="px-4 py-2.5"><Badge value={r.status} /></td>
                  <td className="px-4 py-2.5 text-right">{money(r.amount_due, r.currency)}</td>
                  <td className="px-4 py-2.5 text-right">{money(r.amount_paid, r.currency)}</td>
                  <td className="px-4 py-2.5 text-right">
                    {r.public_token && <a className="font-semibold text-brand-600" href={`/p/${r.public_token}`} target="_blank">Receipt</a>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
