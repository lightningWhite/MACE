/// <reference types="vitest/config" />
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// The dev server proxies the API rather than pointing the client at
// http://localhost:8000, so the client's own code says `/api/...` in
// development and in a deployment where the service serves the built files
// too. One origin, no CORS to think about, no build that is wrong in one
// environment.
export default defineConfig({
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
