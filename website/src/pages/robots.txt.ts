import type { APIRoute } from "astro"
import { BASE, SITE_URL } from "../lib/site"

/** Static robots.txt: everything is public, and the sitemap is one click away. */
export const GET: APIRoute = () =>
  new Response(`User-agent: *\nAllow: /\n\nSitemap: ${SITE_URL}${BASE}/sitemap-index.xml\n`, {
    headers: { "Content-Type": "text/plain; charset=utf-8" },
  })
