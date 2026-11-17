import { redirect } from "next/navigation";
import { siteName } from "@/lib/zirp";

async function openReceipt(formData: FormData) {
  "use server";
  const raw = String(formData.get("code") || "").trim();
  // Accept a full receipt link pasted from a message, or the bare code.
  const code = raw.split("/").filter(Boolean).pop() || "";
  if (code) redirect(`/p/${encodeURIComponent(code)}`);
}

export default function Home() {
  return (
    <main className="mx-auto flex min-h-dvh max-w-md flex-col justify-center px-5">
      <div className="card overflow-hidden">
        <div className="bg-gradient-to-br from-brand-600 to-brand-900 px-6 py-8 text-white">
          <img src="/zirp-logo.png" alt="" className="mb-4 h-12 w-12 rounded-2xl bg-white p-1.5" />
          <h1 className="text-2xl font-extrabold">{siteName()}</h1>
          <p className="mt-1 text-sm text-white/80">Pay your parking with mobile money · Lipa maegesho kwa simu</p>
        </div>
        <form action={openReceipt} className="space-y-3 p-6">
          <label htmlFor="code" className="text-sm font-medium text-slate-700">
            Ticket code · Namba ya tiketi
          </label>
          <input id="code" name="code" className="input" placeholder="Scan the QR or type the code" autoComplete="off" required />
          <button className="btn-primary">Open receipt · Fungua risiti</button>
          <p className="text-center text-xs text-muted">Scan the QR code on your parking ticket to open it directly.</p>
        </form>
      </div>
      <p className="mt-6 text-center text-xs text-muted">
        Staff? <a href="/admin" className="font-semibold text-brand-600">Back office</a>
      </p>
    </main>
  );
}
