import type { APIRoute } from "astro"
import { ApiError, allOpportunities, api, movedSlug, settle, type PublicOpportunity } from "../../../lib/api"
import { STATIC_BUILD } from "../../../lib/config"
import { cardFromTeaser, teaserFromPublic } from "../../../lib/share/model"
import { pngResponse } from "../../../lib/share/render"
import { imageError, siteHost } from "../../../lib/share/route"

export async function getStaticPaths() {
  const all = await settle(allOpportunities({ include_closed: true }))
  return all instanceof ApiError ? [] : all.items.map((opp) => ({ params: { slug: opp.slug }, props: { opp } }))
}

export const GET: APIRoute = async ({ params, props, request, redirect }) => {
  const slug = params.slug ?? ""
  try {
    const opp = (props as { opp?: PublicOpportunity }).opp ?? (await api.opportunity(slug))
    // Prerendering has no real request headers to read.
    return await pngResponse(STATIC_BUILD ? new Request("http://build/") : request, cardFromTeaser(teaserFromPublic(opp), siteHost()), "wide", `blesser-${opp.slug}.png`)
  } catch (err) {
    const to = err instanceof ApiError && err.moved ? movedSlug(err) : null
    if (to) return redirect(`/opportunities/${encodeURIComponent(to)}/og.png`, 301)
    return imageError(err)
  }
}
