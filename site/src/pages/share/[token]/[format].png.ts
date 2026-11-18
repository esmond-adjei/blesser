import type { APIRoute } from "astro"
import { api } from "../../../lib/api"
import { cardFromTeaser, isFormat } from "../../../lib/share/model"
import { pngResponse } from "../../../lib/share/render"
import { imageError, siteHost } from "../../../lib/share/route"

export const getStaticPaths = () => [] as { params: { token: string; format: string } }[]

export const GET: APIRoute = async ({ params, request }) => {
  const { token = "", format } = params
  if (!isFormat(format)) return new Response("Not found", { status: 404 })
  try {
    const teaser = await api.shared(token)
    return await pngResponse(request, cardFromTeaser(teaser, siteHost()), format, `blesser-${teaser.slug}-${format}.png`)
  } catch (err) {
    return imageError(err)
  }
}
