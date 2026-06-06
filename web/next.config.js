/** @type {import('next').NextConfig} */
const path = require("path");

const nextConfig = {
  output: "standalone",
  outputFileTracingRoot: path.join(__dirname),
  compress: true,
  experimental: {
    optimizePackageImports: ["recharts", "@tanstack/react-query", "lucide-react"],
  },
};

module.exports = nextConfig;
