/** Tracking an opportunity picked on the public site, carried through sign-up or sign-in as ?track=<slug>. */
import * as api from "./api"

const SLUG_MAX = 300

/** The ?track= slug, or null when absent or implausible. */
export function trackParam(params: URLSearchParams): string | null {
  const value = params.get("track")?.trim() ?? ""
  if (!value || value.length > SLUG_MAX || value.includes("/")) return null
  return value
}

/** `path` with `next` and `track` carried as query params. */
export function authHref(path: string, { next, track }: { next?: string | null; track?: string | null }): string {
  const params = new URLSearchParams()
  if (next) params.set("next", next)
  if (track) params.set("track", track)
  const query = params.toString()
  return query ? `${path}?${query}` : path
}

export function trackedMessage(title: string | null | undefined): string {
  return title ? `Tracked ${title}` : "Tracked"
}

interface TrackDeps {
  getOpportunity: (idOrSlug: string) => Promise<{ id: string; title: string }>
  trackOpportunity: (id: string) => Promise<unknown>
}

const defaultDeps: TrackDeps = { getOpportunity: api.getOpportunity, trackOpportunity: api.trackOpportunity }

/** Resolves the slug and tracks it for the signed-in member; returns the title. */
export async function trackAfterAuth(slug: string, deps: TrackDeps = defaultDeps): Promise<string> {
  const opp = await deps.getOpportunity(slug)
  await deps.trackOpportunity(opp.id)
  return opp.title
}

/** Title for the toast after sign-up (the backend already tracked it); null when the lookup fails. */
export async function trackedTitle(slug: string, deps: Pick<TrackDeps, "getOpportunity"> = defaultDeps): Promise<string | null> {
  try {
    return (await deps.getOpportunity(slug)).title
  } catch {
    return null
  }
}
