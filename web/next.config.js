/** @type {import('next').NextConfig} */
const internalApiUrl = process.env.INTERNAL_API_URL || "http://localhost:8000";

const nextConfig = {
  output: "standalone",
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${internalApiUrl}/api/:path*`,
      },
    ];
  },
};

module.exports = nextConfig;
