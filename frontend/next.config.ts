import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Standalone output keeps the container image small.
  output: "standalone",
};

export default nextConfig;
