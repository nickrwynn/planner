/** @type {import('next').NextConfig} */
const isProd = process.env.NODE_ENV === "production";
// Next.js App Router ships inline bootstrap/flight scripts. Without a nonce these
// need 'unsafe-inline', otherwise the client never hydrates and no button works.
const scriptSrc = isProd ? "'self' 'unsafe-inline'" : "'self' 'unsafe-inline' 'unsafe-eval'";
// Same-origin `/backend/*` proxy (PWA/homescreen tunnels) + local API fallbacks.
const connectSrc = isProd
  ? "'self' http://localhost:8000 http://api:8000 https:"
  : "'self' http://localhost:8000 http://api:8000 https: ws://localhost:3000";

const apiProxyTarget = (
  process.env.API_INTERNAL_BASE_URL ||
  process.env.API_PROXY_TARGET ||
  "http://localhost:8000"
).replace(/\/$/, "");

const nextConfig = {
  reactStrictMode: true,
  async rewrites() {
    // Browser can call NEXT_PUBLIC_API_BASE_URL=/backend so one HTTPS tunnel
    // serves both the UI and API (required for iPad Add to Home Screen).
    return [
      {
        source: "/backend/:path*",
        destination: `${apiProxyTarget}/:path*`
      }
    ];
  },
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          {
            key: "Content-Security-Policy",
            value: `default-src 'self'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; script-src ${scriptSrc}; connect-src ${connectSrc}; worker-src 'self' blob:; child-src 'self' blob:;`
          }
        ]
      }
    ];
  }
};

export default nextConfig;

