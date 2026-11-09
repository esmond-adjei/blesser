import { createHash } from "node:crypto"
import { Resvg } from "@resvg/resvg-js"
import satori from "satori"
import { ShareImage } from "./card"
import { fonts } from "./fonts"
import { SIZES, type ShareCard, type ShareFormat } from "./model"

// Bump when the design changes so caches and ETags move on.
const DESIGN_VERSION = "1"
const IMAGE_CACHE = "public, max-age=86400"
const MAX_CACHED = 48
const cache = new Map<string, Uint8Array>()

export function etagFor(card: ShareCard, format: ShareFormat): string {
  const hash = createHash("sha256").update(JSON.stringify([DESIGN_VERSION, format, card])).digest("base64url")
  return `"${hash.slice(0, 27)}"`
}

export async function renderPng(card: ShareCard, format: ShareFormat): Promise<Uint8Array> {
  const key = etagFor(card, format)
  const hit = cache.get(key)
  if (hit) {
    cache.delete(key)
    cache.set(key, hit)
    return hit
  }
  const { width, height } = SIZES[format]
  const svg = await satori(ShareImage({ card, format }), { width, height, fonts: await fonts() })
  const png = new Resvg(svg, { fitTo: { mode: "original" }, font: { loadSystemFonts: false } }).render().asPng()
  cache.set(key, png)
  if (cache.size > MAX_CACHED) cache.delete(cache.keys().next().value!)
  return png
}

/** A PNG response with a content ETag; answers 304 when the client already has it. */
export async function pngResponse(request: Request, card: ShareCard, format: ShareFormat, filename: string): Promise<Response> {
  const etag = etagFor(card, format)
  const headers = {
    "cache-control": IMAGE_CACHE,
    "access-control-allow-origin": "*",
    etag,
    "content-disposition": `inline; filename="${filename.replace(/[^\w.-]/g, "")}"`,
  }
  if (request.headers.get("if-none-match")?.split(/\s*,\s*/).includes(etag)) return new Response(null, { status: 304, headers })
  const png = await renderPng(card, format)
  return new Response(png as BodyInit, { headers: { ...headers, "content-type": "image/png" } })
}
