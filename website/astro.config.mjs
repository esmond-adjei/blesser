// @ts-check
import { defineConfig } from "astro/config"
import sitemap from "@astrojs/sitemap"
import tailwindcss from "@tailwindcss/vite"
import { loadEnv } from "vite"

// The marketing site is a static build: no server, no API, no auth. It is
// deployed to GitHub Pages and is entirely separate from the app.
//
//   PUBLIC_SITE_URL - canonical origin, drives canonical links and the sitemap.
//   BASE_PATH       - only non-root for a GitHub Pages *project* site served
//                     from a subpath (e.g. /graduator). A custom domain serves
//                     from "/".
const env = loadEnv(process.env.NODE_ENV ?? "production", process.cwd(), "")

const site = env.PUBLIC_SITE_URL || "https://graduator.example"
const base = env.BASE_PATH || "/"

export default defineConfig({
  site,
  base,
  // "/pricing" and "/pricing/" both resolve to dist/pricing/index.html.
  trailingSlash: "ignore",
  build: { format: "directory" },
  integrations: [sitemap()],
  // The legal pages render Markdown kept in the app (webapp/src/legal).
  vite: { plugins: [tailwindcss()], server: { fs: { allow: [".."] } } },
})
