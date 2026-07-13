import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import path from "node:path";

export default defineConfig(({ command }) => ({
  base: command === "serve" ? "/" : "/ui/static/",
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    proxy: {
      "/ui/api": "http://127.0.0.1:5555",
      "/ui/ws": {
        target: "ws://127.0.0.1:5555",
        ws: true,
      },
      "/settings": "http://127.0.0.1:5555",
      "/douyin": "http://127.0.0.1:5555",
      "/tiktok": "http://127.0.0.1:5555",
    },
  },
  build: {
    outDir: "../src/webui/static",
    assetsDir: "assets",
    emptyOutDir: true,
  },
  publicDir: false,
}));
