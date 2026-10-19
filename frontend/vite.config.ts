import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

const API = "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react()],
  build: {
    outDir: "../traffic_poc/web/static",
    emptyOutDir: true,
    // The Python server sends Cache-Control: no-store, so file names need no
    // content hash, and rebuilding does not churn file names in Git.
    rolldownOptions: {
      output: {
        entryFileNames: "assets/app.js",
        chunkFileNames: "assets/[name].js",
        assetFileNames: "assets/[name][extname]",
      },
    },
  },
  server: {
    proxy: {
      // The API accepts same-origin requests only, so the dev proxy presents
      // itself as the Python server's origin.
      "/api": { target: API, changeOrigin: true, headers: { origin: API } },
    },
  },
});
