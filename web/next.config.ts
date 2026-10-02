import type { NextConfig } from "next";

// The browser talks to /api/*; Next forwards it to the FastAPI service (finintel serve).
// Playwright intercepts /api/* in the browser, so the e2e suite needs no backend.
const api = process.env.FININTEL_API_URL ?? "http://127.0.0.1:8000";

const config: NextConfig = {
  // Rewrites are fixed at build time, so the live e2e run builds into its own directory.
  distDir: process.env.NEXT_DIST_DIR ?? ".next",
  reactStrictMode: true,
  poweredByHeader: false,
  experimental: {
    // The API refuses uploads over 50 MB with its own 413 (ingest.MAX_UPLOAD_BYTES); let the
    // proxy pass a little more so that refusal, not a proxy error, is what the person sees.
    proxyClientMaxBodySize: "51mb",
  },
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${api}/:path*` }];
  },
};

export default config;
