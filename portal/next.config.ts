import type { NextConfig } from "next";

// The Zirp API address is read at request time (lib/zirp.ts), not here, so
// changing ZIRP_API_URL only needs a restart, never a rebuild.
const nextConfig: NextConfig = {
  output: "standalone",
  // Release builds use their own folder so building an installer never
  // replaces the .next of a portal that is running on the build machine.
  distDir: process.env.ZIRP_PORTAL_DIST_DIR || ".next",
  poweredByHeader: false,
  reactStrictMode: true,
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "Referrer-Policy", value: "no-referrer" },
          { key: "X-Frame-Options", value: "DENY" },
        ],
      },
    ];
  },
};

export default nextConfig;
