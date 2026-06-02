import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Cursor's embedded browser sends `browser-logs` HMR messages; Next 15.3 throws
  // "unrecognized HMR message" without this (added in 15.4 for AI/debug workflows).
  experimental: {
    browserDebugInfoInTerminal: true,
  },
};

export default nextConfig;
