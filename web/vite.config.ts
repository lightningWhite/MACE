/// <reference types="vitest/config" />
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// The dev server proxies the API rather than pointing the client at
// http://localhost:8000, so the client's own code says `/api/...` in
// development and in a deployment where the service serves the built files
// too. One origin, no CORS to think about, no build that is wrong in one
// environment.
export default defineConfig({
  // GitHub Pages serves a project site from `/<repo>/`, so the build has to
  // know where it will live. Everything in the client resolves against
  // `import.meta.env.BASE_URL` rather than a leading slash, which is what
  // lets one build work at the root and under a subpath.
  base: process.env.BASE_PATH ?? "/",
  plugins: [react()],
  server: {
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
        ws: true,
      },
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
  },
});
