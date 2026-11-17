import { proxy } from "@/lib/zirp";

// The narrow public payment API: create a payment intent, read payment status.
type Ctx = { params: Promise<{ path: string[] }> };

async function forward(req: Request, { params }: Ctx) {
  const { path } = await params;
  return proxy(req, `/api/public/${path.map(encodeURIComponent).join("/")}`);
}

export { forward as GET, forward as POST };
