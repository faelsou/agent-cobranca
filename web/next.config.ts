import path from "path";
import type { NextConfig } from "next";

// Quando a imagem é buildada com API_UPSTREAM, o browser usa a mesma origem
// do painel e o Next encaminha estes prefixos para o gateway. Assim o login
// não depende de uma porta livre no host (no Minikube, a 8000 pode estar ocupada).
const upstream = process.env.API_UPSTREAM?.replace(/\/$/, "");
const apiPrefixes = [
  "auth",
  "me",
  "health",
  "payments",
  "exceptions",
  "invoices",
  "conversations",
  "approvals",
  "settings",
  "metrics",
  "admin",
  "webhooks",
  "docs",
  "openapi.json",
];

const nextConfig: NextConfig = {
  output: "standalone",
  outputFileTracingRoot: path.join(__dirname),
  async rewrites() {
    if (!upstream) return [];
    return apiPrefixes.flatMap((prefix) => [
      { source: `/${prefix}`, destination: `${upstream}/${prefix}` },
      { source: `/${prefix}/:path*`, destination: `${upstream}/${prefix}/:path*` },
    ]);
  },
};

export default nextConfig;
