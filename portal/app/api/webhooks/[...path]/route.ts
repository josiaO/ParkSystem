import { proxy } from "@/lib/zirp";

// Payment provider callbacks (e.g. /api/webhooks/clickpesa). The body is passed
// through byte-for-byte: the Site Service verifies the provider's checksum.
export async function POST(req: Request, { params }: { params: Promise<{ path: string[] }> }) {
  const { path } = await params;
  return proxy(req, `/api/webhooks/${path.map(encodeURIComponent).join("/")}`);
}
