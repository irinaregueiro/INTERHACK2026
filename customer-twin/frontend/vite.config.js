import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Backend at localhost:8000 by default; override with API_BASE env var.
const apiTarget = process.env.API_BASE || "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": { target: apiTarget, changeOrigin: true },
    },
  },
});
