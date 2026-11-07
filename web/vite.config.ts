import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  resolve: { alias: { "@": "/src" } },
  server: { port: 5173, proxy: { "/v1": "http://127.0.0.1:8000" } },
  test: { environment: "node" },
} as Parameters<typeof defineConfig>[0]);
