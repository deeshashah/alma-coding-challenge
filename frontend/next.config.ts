import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  experimental: {
    serverActions: {
      // Backend caps requests at 6MB and replies with a friendly 413; keep this
      // comfortably above that so Next's own limit never fires first.
      bodySizeLimit: "8mb",
    },
  },
};

export default nextConfig;
