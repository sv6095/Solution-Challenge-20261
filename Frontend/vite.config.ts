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