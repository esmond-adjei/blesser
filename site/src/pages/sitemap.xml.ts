import type { APIRoute } from "astro"
import { api } from "../lib/api"
import { PAGE_CACHE, STATIC_BUILD, siteUrl } from "../lib/config"
import { LANDINGS } from "../lib/landings"

const esc = (s: string) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")

export const GET: APIRoute = async () => {
  const site = siteUrl()
  let data
  try {
    data = await api.sitemap()
  } catch {
    if (STATIC_BUILD) data = { opportunities: [], collections: [] }
    else return new Response("Sitemap unavailable", { status: 503, headers: { "cache-control": "no-store" } })
  }
  const urls: { loc: string; lastmod?: string }[] = [
    ...["/", "/opportunities", "/about", "/privacy", "/terms"].map((p) => ({ loc: p })),
    ...LANDINGS.map((l) => ({ loc: `/${l.slug}` })),
    ...data.collections.map((c) => ({ loc: `/collections/${encodeURIComponent(c.slug)}` })),
    ...data.opportunities.map((o) => ({ loc: `/opportunities/${encodeURIComponent(o.slug)}`, lastmod: o.updated_at })),
  ]
  const body =
    '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' +
    urls
      .map((u) => `  <url><loc>${esc(site + u.loc)}</loc>${u.lastmod ? `<lastmod>${esc(u.lastmod)}</lastmod>` : ""}</url>`)
      .join("\n") +
    "\n</urlset>\n"
  return new Response(body, { headers: { "content-type": "application/xml; charset=utf-8", "cache-control": PAGE_CACHE } })
}
