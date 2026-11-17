import { proxy } from "@/lib/zirp";

// Signed-in back-office calls from the browser (images, CSV exports). The
// operator's API token stays in an httpOnly cookie and is added here.
const READ_ONLY = /^(media\/|reports\/(export|payments)\.csv$|payments$|payments\/health$|sessions(\/|$)|dashboard$)/;

export async function GET(req: Request, { params }: { params: Promise<{ path: string[] }> }) {
  const { path } = await params;
  const target = path.map(encodeURIComponent).join("/");
  if (!READ_ONLY.test(target)) return Response.json({ detail: "Not available through the portal" }, { status: 404 });
  return proxy(req, `/${target}`, { auth: true });
}
