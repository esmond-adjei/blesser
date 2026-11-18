import tailwindcss from "@tailwindcss/vite"
import react from "@vitejs/plugin-react"
import { defineConfig } from "vite"

const apiTarget = process.env.API_PROXY_TARGET ?? "http://localhost:8000"

export default defineConfig({
  plugins: [react(), tailwindcss()],
  // Flags stay separate files so the country picker loads only the ones on screen.
  build: { assetsInlineLimit: (file: string) => (file.includes("country-flag-icons") ? false : undefined) },
  server: {
    port: 5173,
    proxy: {
      // Local dev: forward API calls to the FastAPI backend (uvicorn :8000).
      // In production, serve the built client from the backend or set
      // VITE_API_URL to the API origin.
      "/api": { target: apiTarget, changeOrigin: true },
      "/ready": { target: apiTarget, changeOrigin: true },
    },
  },
})
