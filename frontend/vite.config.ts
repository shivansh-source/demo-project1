import react from "@vitejs/plugin-react";
import { defineConfig, loadEnv } from "vite";

// The browser talks to /api/*; the dev server forwards it to FastAPI, so no CORS setup is needed.
// Override the target with VITE_API_TARGET (e.g. in frontend/.env.local).
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, ".", "");
  const target = env.VITE_API_TARGET || "http://localhost:8000";
  return {
    plugins: [react()],
    server: {
      port: 5173,
      proxy: {
        "/api": { target, changeOrigin: true, rewrite: (path) => path.replace(/^\/api/, "") },
      },
    },
  };
});
