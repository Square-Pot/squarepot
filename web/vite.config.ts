// SPDX-License-Identifier: AGPL-3.0-or-later
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  // SQUAREPOT_COMMIT is given at build time (task #185); VITE_ keeps the usual prefix.
  envPrefix: ["VITE_", "SQUAREPOT_"],
  // `npm run dev` talks to a server on this machine, as the built app does to its own.
  server: { proxy: { "/api": "http://127.0.0.1:8000" } },
  build: { sourcemap: false },
  test: { environment: "node", include: ["src/**/*.test.ts"] },
});
