import { proxy } from "@/lib/zirp";

// Public receipt helpers served by the Site Service: JSON status and the QR image.
// Entry photos stay private (the API itself decides what a driver may see).
const ALLOWED = new Set(["status", "qr.png", "snapshot.jpg", "crop.jpg"]);

export async function GET(req: Request, { params }: { params: Promise<{ token: string; asset: string }> }) {
  const { token, asset } = await params;
  if (!ALLOWED.has(asset)) return Response.json({ detail: "Not found" }, { status: 404 });
  return proxy(req, `/p/${encodeURIComponent(token)}/${asset}`);
}
