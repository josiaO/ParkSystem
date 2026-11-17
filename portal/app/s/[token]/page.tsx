import { redirect } from "next/navigation";

// Receipt QR codes print the short link /s/<token>; the page lives at /p/<token>.
export default async function ShortLink({ params }: { params: Promise<{ token: string }> }) {
  const { token } = await params;
  redirect(`/p/${encodeURIComponent(token)}`);
}
