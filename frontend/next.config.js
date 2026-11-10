const { PHASE_DEVELOPMENT_SERVER } = require("next/constants");

// Where the Next.js server finds the API (FastAPI). Local default: http://127.0.0.1:8000. In Docker it is http://backend:8000.
const backend = (process.env.API_INTERNAL_URL || "http://127.0.0.1:8000").replace(/\/$/, "");

/** Dev and production builds get SEPARATE output folders, so building while `npm run dev` runs cannot corrupt the dev server. */
module.exports = (phase) => ({
  distDir: phase === PHASE_DEVELOPMENT_SERVER ? ".next-dev" : ".next",
  output: "standalone",
  reactStrictMode: true,
  poweredByHeader: false,
  eslint: { ignoreDuringBuilds: true },
  // The browser talks to ONE origin. Every /api/* call except NextAuth's own /api/auth/* is forwarded to the API, so no CORS setup, no
  // NEXT_PUBLIC_API_URL and no reverse proxy are needed for local development. (In Docker, Caddy routes these before they reach Next.)
  async rewrites() {
    return [
      { source: "/api/:path((?!auth(?:/|$)).*)", destination: `${backend}/api/:path*` },
      { source: "/health", destination: `${backend}/health` },
    ];
  },
});
