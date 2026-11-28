import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// The build is served by the Python app itself, so an office runs one program and nothing is loaded from outside.
export default defineConfig({
  plugins: [react()],
  build: { outDir: "../src/reviewpulse/app/web", emptyOutDir: true },
  server: { proxy: { "/api": "http://127.0.0.1:8000" } },
});
