// SPDX-License-Identifier: AGPL-3.0-or-later
import react from "@vitejs/plugin-react";
import { defineConfig, loadEnv } from "vitest/config";

export default defineConfig(({ mode }) => ({
  plugins: [react()],
  // Only SQUAREPOT_COMMIT reaches the client, through `define` (task #185):
  // an `envPrefix` of `SQUAREPOT_` would expose the server's secrets
  // (SQUAREPOT_API_TOKEN) to client code, while loadEnv's empty prefix here
  // stays inside this config file.
  define: {
    "import.meta.env.SQUAREPOT_COMMIT": JSON.stringify(loadEnv(mode, ".", "").SQUAREPOT_COMMIT ?? ""),
  },
  // `npm run dev` talks to a server on this machine, as the built app does to its own.
  server: { proxy: { "/api": "http://127.0.0.1:8000" } },
  build: { sourcemap: false },
  test: { environment: "node", include: ["src/**/*.test.ts"] },
}));
