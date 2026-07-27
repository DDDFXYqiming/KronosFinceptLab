/** @type {import('next').NextConfig} */
const path = require("path");

const nextConfig = {
  outputFileTracingRoot: path.join(__dirname),
  compress: true,
  experimental: {
    optimizePackageImports: ["recharts", "@tanstack/react-query", "lucide-react"],
  },
};

module.exports = nextConfig;
