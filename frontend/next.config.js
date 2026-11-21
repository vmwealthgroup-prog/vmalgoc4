const { PHASE_DEVELOPMENT_SERVER } = require("next/constants");

// For hosted deployments, default to the Render API. Local/Docker deployments
// can still override this through API_INTERNAL_URL or NEXT_PUBLIC_API_URL.
const backend = (
  process.env.API_INTERNAL_URL?.trim() ||
  process.env.NEXT_PUBLIC_API_URL?.trim() ||
  "https://vmalgoc4-api.onrender.com"
).replace(/\/$/, "");

module.exports = (phase) => ({
  distDir: phase === PHASE_DEVELOPMENT_SERVER ? ".next-dev" : ".next",
  output: "standalone",
  reactStrictMode: true,
  poweredByHeader: false,
  eslint: { ignoreDuringBuilds: true },
  async rewrites() {
    return [
      { source: "/api/:path((?!auth(?:/|$)).*)", destination: `${backend}/api/:path*` },
      { source: "/health", destination: `${backend}/health` },
    ];
  },
});
