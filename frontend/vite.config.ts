/// <reference types="vitest/config" />
import { fileURLToPath, URL } from "node:url";

import tailwindcss from "@tailwindcss/vite";
import { tanstackRouter } from "@tanstack/router-plugin/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [
    // Must run before the React plugin: it generates src/routeTree.gen.ts and
    // splits every route into its own chunk (guide 11.5).
    tanstackRouter({ target: "react", autoCodeSplitting: true }),
    react(),
    tailwindcss(),
  ],
  resolve: {
    alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) },
  },
  server: {
    host: true,
    port: 5173,
    strictPort: true,
    // In Docker the dev server is reached only through Caddy, which forwards with
    // Host: web:5173. Plain `vite` on the host still answers localhost as usual.
    allowedHosts: ["web"],
  },
  build: {
    target: "es2023",
    sourcemap: true,
    // scripts/check-bundle-size.mjs reads the manifest to find the initial chunks.
    manifest: true,
  },
  test: {
    environment: "jsdom",
    globals: false,
    setupFiles: ["./src/test/setup.ts"],
    css: false,
    restoreMocks: true,
    // Whole sign-in and project flows in jsdom take a few seconds on containers and CI
    // runners, and coverage instrumentation makes them slower again.
    testTimeout: 30_000,
    // Each file gets its own jsdom; more than a handful at once starves them all.
    maxWorkers: 4,
    coverage: {
      provider: "v8",
      include: ["src/**/*.{ts,tsx}"],
      exclude: [
        "src/routeTree.gen.ts",
        "src/api/schema.d.ts",
        "src/components/ui/**",
        "src/test/**",
        "src/main.tsx",
      ],
      thresholds: { lines: 85, functions: 85, branches: 70, statements: 85 },
    },
  },
});
