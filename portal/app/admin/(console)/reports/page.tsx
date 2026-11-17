import { api, type ReportSummary } from "@/lib/zirp";
import { money } from "@/lib/format";
import { PageTitle, Stat } from "@/components/ui";

export const dynamic = "force-dynamic";

function isoDay(d: Date) {
  return d.toISOString().slice(0, 10);
}

export default async function Reports({ searchParams }: { searchParams: Promise<{ start?: string; end?: string }> }) {
  const sp = await searchParams;
  const today = new Date();
  const start = sp.start || isoDay(new Date(today.getTime() - 6 * 86400_000));
  const end = sp.end || isoDay(today);
  const query = new URLSearchParams({ start: `${start}T00:00:00+03:00`, end: `${end}T23:59:59+03:00` });
  const report = await api<ReportSummary>(`/reports/summary?${query}`, { auth: true });
  const hours = Math.floor((report.average_stay_seconds || 0) / 3600);
  const minutes = Math.round(((report.average_stay_seconds || 0) % 3600) / 60);
  return (
    <>
      <PageTitle title="Reports" subtitle={`${start} to ${end} (East Africa Time)`}>
        <form className="flex flex-wrap items-center gap-2">
          <input type="date" name="start" defaultValue={start} className="input w-40 py-2 text-sm" />
          <input type="date" name="end" defaultValue={end} className="input w-40 py-2 text-sm" />
          <button className="btn-ghost">Show</button>
          <a className="btn-ghost" href={`/api/zirp/reports/export.csv?${query}`}>CSV</a>
        </form>
      </PageTitle>
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat label="Collected" value={report.collected_label || money(report.collected, report.currency)} tone="good" />
        <Stat label="Entries / exits" value={`${report.entries} / ${report.exits}`} />
        <Stat label="Unpaid casual" value={report.unpaid_casual} tone={report.unpaid_casual ? "warn" : "good"} />
        <Stat label="Average stay" value={`${hours} h ${minutes} min`} />
      </div>
      <div className="mt-6 grid gap-4 md:grid-cols-2">
        {report.by_method?.length > 0 && (
          <section className="card p-5">
            <h2 className="font-bold">By payment method</h2>
            <ul className="mt-3 divide-y divide-slate-100 text-sm">
              {report.by_method.map((m) => (
                <li key={m.method} className="flex justify-between py-2">
                  <span>{m.label || m.method.replaceAll("_", " ")} · {m.count}</span>
                  <span className="font-semibold">{money(m.amount, report.currency)}</span>
                </li>
              ))}
            </ul>
          </section>
        )}
        {report.sections?.map((section) => (
          <section key={section.title} className="card p-5">
            <h2 className="font-bold">{section.title}</h2>
            <ul className="mt-3 divide-y divide-slate-100 text-sm">
              {section.rows.map((row) => (
                <li key={row.label} className="flex justify-between py-2">
                  <span className="text-muted">{row.label}</span>
                  <span className="font-semibold">{row.value}</span>
                </li>
              ))}
            </ul>
          </section>
        ))}
      </div>
    </>
  );
}
