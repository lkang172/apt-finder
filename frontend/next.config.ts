import type { NextConfig } from "next";
import { backendUrl } from "./src/lib/backend-url";

const nextConfig: NextConfig = {
  agentRules: false,
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${backendUrl()}/api/:path*` }];
  },
};

export default nextConfig;
