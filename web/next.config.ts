import type { NextConfig } from "next";

const securityHeaders = [
  {
    key: "X-DNS-Prefetch-Control",
    value: "on",
  },
  {
    key: "X-Frame-Options",
    value: "DENY",
  },
  {
    key: "X-Content-Type-Options",
    value: "nosniff",
  },
  {
    key: "Referrer-Policy",
    value: "strict-origin-when-cross-origin",
  },
  {
    key: "Permissions-Policy",
    value: "camera=(), microphone=(), geolocation=(), interest-cohort=()",
  },
  {
    key: "Strict-Transport-Security",
    value: "max-age=63072000; includeSubDomains; preload",
  },
];

const nextConfig: NextConfig = {
  images: {
    unoptimized: true, // No external images yet
  },
  async headers() {
    return [
      {
        source: "/(.*)",
        headers: securityHeaders,
      },
    ];
  },
  async redirects() {
    return [
      // Phase 2.6: collapse three council analytics pages into one tabbed surface.
      {
        source: "/council/coalitions",
        destination: "/council/analytics",
        permanent: true,
      },
      {
        source: "/council/voting-patterns",
        destination: "/council/analytics",
        permanent: true,
      },
      {
        source: "/council/stats",
        destination: "/council/analytics?tab=stats",
        permanent: true,
      },
      {
        source: "/council/patterns",
        destination: "/council/analytics?tab=patterns",
        permanent: true,
      },
    ];
  },
};

export default nextConfig;
