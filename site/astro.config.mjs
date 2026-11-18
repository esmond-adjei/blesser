import { defineConfig } from "astro/config"
import node from "@astrojs/node"
import react from "@astrojs/react"
import tailwindcss from "@tailwindcss/vite"

// SITE_STATIC=1 builds a static snapshot (GitHub Pages); otherwise the Node server.
const staticBuild = process.env.SITE_STATIC === "1"

export default defineConfig({
  output: staticBuild ? "static" : "server",
  adapter: staticBuild ? undefined : node({ mode: "standalone" }),
  base: process.env.SITE_BASE || undefined,
  integrations: [react()],
  server: { port: 4321, host: true },
  vite: { plugins: [tailwindcss()] },
})
