import type { APIRoute } from "astro"
import { PAGE_CACHE, siteUrl } from "../lib/config"

export const GET: APIRoute = () =>
  new Response(`User-agent: *\nAllow: /\nDisallow: /api/\n\nSitemap: ${siteUrl()}/sitemap.xml\n`, {
    headers: { "content-type": "text/plain; charset=utf-8", "cache-control": PAGE_CACHE },
  })
