import ReceiptView from "@/components/ReceiptView";
import { ApiError, api, siteName, supportPhone, type Receipt } from "@/lib/zirp";

export const dynamic = "force-dynamic";

export default async function ReceiptPage({ params }: { params: Promise<{ token: string }> }) {
  const { token } = await params;
  let receipt: Receipt | null = null;
  let problem: "missing" | "offline" | null = null;
  try {
    receipt = await api<Receipt>(`/api/public/payment-status/${encodeURIComponent(token)}`);
  } catch (err) {
    problem = err instanceof ApiError && err.status === 404 ? "missing" : "offline";
  }
  if (!receipt) {
    return (
      <main className="mx-auto flex min-h-dvh max-w-md flex-col items-center justify-center px-6 text-center">
        <img src="/zirp-logo.png" alt="" className="mb-5 h-14 w-14 rounded-2xl bg-white p-2 shadow" />
        <h1 className="text-xl font-bold">{problem === "missing" ? "Receipt not found" : "Please try again"}</h1>
        <p className="mt-2 text-sm text-muted">
          {problem === "missing"
            ? "Check the code on your ticket, or ask the parking attendant. / Hakikisha namba ya tiketi yako."
            : "The parking server is not reachable right now. / Seva haipatikani kwa sasa."}
        </p>
        <a href="/" className="btn-ghost mt-6">
          Enter a ticket code
        </a>
      </main>
    );
  }
  return <ReceiptView initial={receipt} siteName={siteName()} supportPhone={supportPhone()} />;
}
