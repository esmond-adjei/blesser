import type { APIRoute } from "astro"
import { ApiError, allOpportunities, api, movedSlug, settle } from "../../../../../lib/api"
import { PAGE_CACHE } from "../../../../../lib/config"

// Production nginx sends /api to the API directly; this keeps the same-origin link working in dev and behind a bare site container.
export async function getStaticPaths() {
  const all = await settle(allOpportunities())
  return all instanceof ApiError ? [] : all.items.filter((o) => o.deadline_date).map((o) => ({ params: { slug: o.slug } }))
}

export const GET: APIRoute = async ({ params, redirect }) => {
  const slug = params.slug ?? ""
  try {
    const upstream = await api.calendar(slug)
    return new Response(await upstream.text(), {
      headers: {
        "content-type": "text/calendar; charset=utf-8",
        "content-disposition": `attachment; filename="${slug.replace(/[^\w-]/g, "")}.ics"`,
        "cache-control": PAGE_CACHE,
      },
    })
  } catch (err) {
    if (!(err instanceof ApiError)) throw err
    const to = err.moved ? movedSlug(err) : null
    if (to) return redirect(`/api/public/opportunities/${encodeURIComponent(to)}/calendar.ics`, 301)
    return new Response(err.notFound ? "Not found" : "Calendar unavailable", {
      status: err.notFound ? 404 : 503,
      headers: { "content-type": "text/plain; charset=utf-8" },
    })
  }
}
