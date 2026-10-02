import type { NextConfig } from "next";

// The browser talks to /api/*; Next forwards it to the FastAPI service (finintel serve).
// Playwright intercepts /api/* in the browser, so the e2e suite needs no backend.
const api = process.env.FININTEL_API_URL ?? "http://127.0.0.1:8000";

const config: NextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${api}/:path*` }];
  },
};

export default config;
