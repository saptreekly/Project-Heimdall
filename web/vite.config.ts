import { defineConfig } from "vite";

const base = process.env.VITE_BASE || "/";

export default defineConfig({
  base,
  server: {
    port: 5173,
  },
  build: {
    outDir: "dist",
    emptyOutDir: true,
  },
});
