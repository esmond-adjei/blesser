import { ApiError } from "../api"
import { siteUrl } from "../config"

export const siteHost = () => new URL(siteUrl()).host

export function imageError(err: unknown): Response {
  if (!(err instanceof ApiError)) throw err
  return new Response(err.notFound ? "Not found" : "Image unavailable", {
    status: err.notFound ? 404 : 503,
    headers: { "content-type": "text/plain; charset=utf-8", "cache-control": err.notFound ? "public, s-maxage=60" : "no-store" },
  })
}
