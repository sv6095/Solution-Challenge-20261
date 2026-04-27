import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "path";

// https://vitejs.dev/config/
export default defineConfig(({ mode }) => ({
  server: {
    host: "::",
    port: 8080,
    hmr: {
      overlay: false,
    },
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
      "/osrm": {
        target: "https://router.project-osrm.org",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/osrm/, ""),
      },
    },
  },
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
      "@mapcn/logistics-network": path.resolve(__dirname, "./src/mapcn/logistics-network.tsx"),
      "@mapcn/heatmap": path.resolve(__dirname, "./src/mapcn/heatmap.tsx"),
      "@mapcn/delivery-tracker": path.resolve(__dirname, "./src/mapcn/delivery-tracker.tsx"),
    },
  },
}));
