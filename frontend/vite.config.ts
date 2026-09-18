import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    // The API and uploaded media are proxied so the browser sees one origin in
    // development — no CORS, and relative URLs from the API just work.
    proxy: {
      "/api": { target: "http://localhost:18000", changeOrigin: true },
      "/media": { target: "http://localhost:18000", changeOrigin: true },
    },
  },
  build: { outDir: "dist", sourcemap: true },
});
