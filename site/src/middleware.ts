import { defineMiddleware } from "astro:middleware"
import { PAGE_CACHE } from "./lib/config"

export const onRequest = defineMiddleware(async (context, next) => {
  const response = await next()
  if (!["GET", "HEAD"].includes(context.request.method) || response.headers.has("cache-control")) return response
  const value =
    response.status === 200 || response.status === 301
      ? PAGE_CACHE
      : response.status === 404
        ? "public, s-maxage=60"
        : "no-store"
  try {
    response.headers.set("cache-control", value)
    return response
  } catch {
    // Some responses (redirects, fetched bodies) carry immutable headers.
    const copy = new Response(response.body, response)
    copy.headers.set("cache-control", value)
    return copy
  }
})
