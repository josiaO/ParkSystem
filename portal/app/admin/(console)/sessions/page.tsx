import { api, type SessionRow } from "@/lib/zirp";
import { money, when } from "@/lib/format";
import { Badge, Empty, PageTitle } from "@/components/ui";

export const dynamic = "force-dynamic";

const PAGE = 200;
const STATUSES = ["ACTIVE", "WAITING_RECEIPT", "PAID", "CLOSED", "REVOKED"];

type Search = { q?: string; status?: string; view?: string; before?: string };

export default async function Sessions({ searchParams }: { searchParams: Promise<Search> }) {
  const { q = "", status = "", view = "", before = "" } = await searchParams;
  const params = new URLSearchParams({ limit: String(PAGE) });
  if (q.trim()) params.set("q", q.trim());
  if (status) params.set("status", status);
  if (view === "inside") params.set("open_only", "true");
  if (before) params.set("before_id", before);
  const rows = await api<SessionRow[]>(`/sessions?${params}`, { auth: true });
  const shown = view === "due" ? rows.filter((r) => (r.due_now ?? 0) > 0) : rows;
  const owing = rows.reduce((sum, r) => sum + (r.due_now ?? 0), 0);
  const older = rows.length === PAGE ? rows[rows.length - 1].id : null;
  const link = (extra: Partial<Search>) => {
    const next = new URLSearchParams();
    const merged = { q, status, view, ...extra };
    Object.entries(merged).forEach(([k, v]) => v && next.set(k, String(v)));
    return `?${next}`;
  };
  return (
    <>
      <PageTitle title="Sessions" subtitle={before ? `Visits before #${before}` : "Newest visits first"}>
        <form className="flex flex-wrap gap-2">
          <input name="q" defaultValue={q} placeholder="Plate" className="input w-36 py-2 text-sm" />
          <select name="view" defaultValue={view} className="input w-44 py-2 text-sm">
            <option value="">All visits</option>
            <option value="inside">Still inside</option>
            <option value="due">Inside and owing</option>
          </select>
          <select name="status" defaultValue={status} className="input w-36 py-2 text-sm">
            <option value="">Any status</option>
            {STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
          <button className="btn-ghost">Filter</button>
        </form>
      </PageTitle>
      {view && (
        <p className="mb-3 text-sm text-muted">
          {shown.length} visit{shown.length === 1 ? "" : "s"} · owing now <b className="text-ink">{money(owing, rows[0]?.currency || "TZS")}</b>
        </p>
      )}
      {shown.length === 0 ? (
        <Empty text="No sessions match." />
      ) : (
        <div className="card overflow-x-auto">
          <table className="w-full min-w-[760px] text-sm">
            <thead className="bg-slate-50 text-left text-xs uppercase tracking-wide text-muted">
              <tr>
                <th className="px-4 py-3">Plate</th><th className="px-4 py-3">Entered</th><th className="px-4 py-3">Exited</th>
                <th className="px-4 py-3">Kind</th><th className="px-4 py-3">Status</th><th className="px-4 py-3 text-right">Due now</th>
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
                  <td className={`px-4 py-2.5 text-right ${(r.due_now ?? 0) > 0 ? "font-bold text-amber-700" : ""}`}>
                    {r.due_now != null ? money(r.due_now, r.currency) : money(r.amount_due, r.currency)}
                  </td>
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
      <div className="mt-4 flex justify-between text-sm">
        {before ? <a className="btn-ghost" href={link({ before: "" })}>Newest</a> : <span />}
        {older && <a className="btn-ghost" href={link({ before: String(older) })}>Load older →</a>}
      </div>
    </>
  );
}
