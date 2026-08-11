import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Dev server only — docker-compose.yml's nginx handles routing in
// production. Locally this lets `npm run dev` talk to a backend running
// on :8000 without the browser tripping over CORS during development.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    proxy: {
      "/api": { target: "http://localhost:8000", changeOrigin: true },
      "/ws": { target: "ws://localhost:8000", ws: true },
    },
  },
});
