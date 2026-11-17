import type { Metadata, Viewport } from "next";
import "./globals.css";
import { siteName } from "@/lib/zirp";

export async function generateMetadata(): Promise<Metadata> {
  return {
    title: { default: siteName(), template: `%s · ${siteName()}` },
    description: "Parking receipts and mobile payment",
    robots: { index: false, follow: false },
    icons: { icon: "/favicon.ico" },
  };
}

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: "#1d4ed8",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="font-sans antialiased">{children}</body>
    </html>
  );
}
