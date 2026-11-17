import Link from "next/link";
import { redirect } from "next/navigation";
import { ApiError, api, siteName, type Me } from "@/lib/zirp";
import { logout } from "../actions";

export const dynamic = "force-dynamic";

const NAV = [
  { href: "/admin", label: "Overview" },
  { href: "/admin/sessions", label: "Sessions" },
  { href: "/admin/payments", label: "Payments" },
  { href: "/admin/reports", label: "Reports" },
];

export default async function ConsoleLayout({ children }: { children: React.ReactNode }) {
  let me: Me;
  try {
    me = await api<Me>("/auth/me", { auth: true });
  } catch (err) {
    if (err instanceof ApiError && (err.status === 401 || err.status === 403)) redirect("/admin/login");
    return (
      <main className="grid min-h-dvh place-items-center px-6 text-center">
        <div>
          <h1 className="text-xl font-bold">Parking server not reachable</h1>
          <p className="mt-2 text-sm text-muted">Check that the Zirp Site Service is running and ZIRP_API_URL is correct.</p>
        </div>
      </main>
    );
  }
  return (
    <div className="min-h-dvh">
      <header className="sticky top-0 z-10 border-b border-slate-200 bg-white/90 backdrop-blur">
        <div className="mx-auto flex max-w-6xl items-center gap-4 px-4 py-3">
          <Link href="/admin" className="flex items-center gap-2 font-bold">
            <img src="/zirp-logo.png" alt="" className="h-8 w-8 rounded-lg" />
            <span className="hidden sm:inline">{siteName()}</span>
          </Link>
          <nav className="flex flex-1 gap-1 overflow-x-auto text-sm">
            {NAV.map((item) => (
              <Link key={item.href} href={item.href} className="whitespace-nowrap rounded-lg px-3 py-1.5 font-medium text-slate-600 hover:bg-slate-100 hover:text-ink">
                {item.label}
              </Link>
            ))}
          </nav>
          <form action={logout} className="flex items-center gap-3">
            <span className="hidden text-xs text-muted md:inline">{me.full_name || me.username}</span>
            <button className="btn-ghost py-1.5">Sign out</button>
          </form>
        </div>
      </header>
      <main className="mx-auto max-w-6xl px-4 py-6">{children}</main>
    </div>
  );
}
