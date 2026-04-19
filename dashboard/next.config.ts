import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  async rewrites() {
    return {
      beforeFiles: [
        {
          source: "/api/:path*",
          destination: "http://localhost:8000/api/:path*",
        },
      ],
    };
  },
  async headers() {
    return [
      {
        source: "/(.*)",
        headers: [
          {
            key: "Content-Security-Policy",
            value: [
              "default-src 'self'",
              "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://engage.aitradepulse.com/cdn-cgi/ https://static.cloudflareinsights.com https://*.cloudflareinsights.com",
              "style-src 'self' 'unsafe-inline'",
              "connect-src 'self' https://engage.aitradepulse.com https://cloudflareinsights.com https://*.cloudflareinsights.com http://localhost:8000",
              "img-src 'self' data: https://raw.githubusercontent.com",
              "font-src 'self'",
            ].join("; "),
          },
        ],
      },
    ];
  },
};

export default nextConfig;
