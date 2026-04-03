/** @type {import('next').NextConfig} */
const isProd = process.env.NODE_ENV === "production";
const scriptSrc = isProd ? "'self'" : "'self' 'unsafe-inline' 'unsafe-eval'";
const connectSrc = isProd
  ? "'self' http://localhost:8000 http://api:8000"
  : "'self' http://localhost:8000 http://api:8000 ws://localhost:3000";

const nextConfig = {
  reactStrictMode: true,
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          {
            key: "Content-Security-Policy",
            value: `default-src 'self'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; script-src ${scriptSrc}; connect-src ${connectSrc};`
          }
        ]
      }
    ];
  }
};

export default nextConfig;

