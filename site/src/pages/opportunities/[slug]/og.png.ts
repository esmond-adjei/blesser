import type { APIRoute } from "astro"
import { ApiError, api, movedSlug } from "../../../lib/api"
import { cardFromTeaser, teaserFromPublic } from "../../../lib/share/model"
import { pngResponse } from "../../../lib/share/render"
import { imageError, siteHost } from "../../../lib/share/route"

export const GET: APIRoute = async ({ params, request, redirect }) => {
  const slug = params.slug ?? ""
  try {
    const opp = await api.opportunity(slug)
    return await pngResponse(request, cardFromTeaser(teaserFromPublic(opp), siteHost()), "wide", `blesser-${opp.slug}.png`)
  } catch (err) {
    const to = err instanceof ApiError && err.moved ? movedSlug(err) : null
    if (to) return redirect(`/opportunities/${encodeURIComponent(to)}/og.png`, 301)
    return imageError(err)
  }
}
