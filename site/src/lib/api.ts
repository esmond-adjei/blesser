import { STATIC_BUILD, apiUrl } from "./config"

export type PublicOpportunity = {
  id: string
  slug: string
  title: string
  organization: string
  category: string
  kind: string
  summary: string
  eligibility: string
  benefits: string
  location: string
  countries: string[]
  requirements: string[]
  tags: string[]
  deadline: string
  deadline_date: string | null
  rolling: boolean
  link: string
  source_url: string
  verified_at: string | null
  published_at: string | null
  is_open: boolean
  days_left: number | null
  closed: boolean
}

export type Page<T> = { items: T[]; total: number }

export type ShareFormat = "square" | "wide" | "story"
export type ShareKit = {
  share_url: string
  images: Record<ShareFormat, string>
  captions: { short: string; standard: string; hashtags: string }
  disclaimer: string
}

export type SharedTeaser = {
  slug: string
  audience: "public" | "members"
  status: "published" | "archived"
  title: string
  organization: string
  category: string
  kind: string
  benefits: string
  deadline: string
  deadline_date: string | null
  rolling: boolean
  seed: string
}

export type Collection = {
  id: string
  slug: string
  title: string
  intro: string
  audience: "public" | "members"
  filter: Record<string, unknown> | null
  item_ids: string[]
  position: number
  published: boolean
}
export type PublicCollection = Collection & { items: PublicOpportunity[] }

export type Announcement = { text: string; link: string; starts_on: string | null; ends_on: string | null }
export type SiteContent = { hero_title: string; hero_subtitle: string; announcement: Announcement | null }
export type PublicSite = { content: SiteContent; featured: PublicOpportunity[]; closing_soon: PublicOpportunity[] }

export type FacetCount = { key: string; count: number }
export type Facets = { categories: FacetCount[]; kinds: FacetCount[]; total: number; closing_soon: number }

export type Sitemap = { opportunities: { slug: string; updated_at: string }[]; collections: { slug: string }[] }

export type OpportunityQuery = {
  q?: string
  category?: string
  kind?: string
  country?: string
  closing_within?: number
  include_closed?: boolean
  sort?: "deadline" | "new"
  limit?: number
  offset?: number
}

/** status 0 means the API could not be reached. */
export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly location: string | null = null,
  ) {
    super(status ? `API answered ${status}` : "API unreachable")
  }
  get notFound() {
    return this.status === 404
  }
  get moved() {
    return this.status === 301 || this.status === 308
  }
}

async function request(path: string): Promise<Response> {
  let res: Response
  try {
    res = await fetch(`${apiUrl()}/api/public${path}`, {
      headers: { accept: "application/json" },
      redirect: "manual",
      signal: AbortSignal.timeout(8000),
    })
  } catch {
    throw new ApiError(0)
  }
  if (!res.ok) throw new ApiError(res.status, res.headers.get("location"))
  return res
}

async function fetchJson<T>(path: string): Promise<T> {
  const res = await request(path)
  try {
    return (await res.json()) as T
  } catch {
    throw new ApiError(502)
  }
}

// A static build renders every page in one process; share responses instead of refetching per page.
const memo = new Map<string, Promise<unknown>>()
function get<T>(path: string): Promise<T> {
  if (!STATIC_BUILD) return fetchJson<T>(path)
  if (!memo.has(path)) memo.set(path, fetchJson<T>(path))
  return memo.get(path) as Promise<T>
}

function query(params: Record<string, string | number | boolean | undefined>): string {
  const qs = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== "" && value !== false) qs.set(key, String(value))
  }
  const s = qs.toString()
  return s ? `?${s}` : ""
}

const slugPath = (slug: string) => `/opportunities/${encodeURIComponent(slug)}`

export const api = {
  opportunities: (q: OpportunityQuery = {}) => get<Page<PublicOpportunity>>(`/opportunities${query(q)}`),
  opportunity: (slug: string) => get<PublicOpportunity>(slugPath(slug)),
  calendar: (slug: string) => request(`${slugPath(slug)}/calendar.ics`),
  shareKit: (slug: string) => get<ShareKit>(`${slugPath(slug)}/share`),
  shared: (token: string) => get<SharedTeaser>(`/shared/${encodeURIComponent(token)}`),
  facets: () => get<Facets>("/facets"),
  collections: () => get<PublicCollection[]>("/collections"),
  collection: (slug: string) => get<PublicCollection>(`/collections/${encodeURIComponent(slug)}`),
  site: () => get<PublicSite>("/site"),
  sitemap: () => get<Sitemap>("/sitemap"),
}

const MAX_PAGE = 100

/** Every page of a listing, for static builds. */
export async function allOpportunities(q: OpportunityQuery = {}): Promise<Page<PublicOpportunity>> {
  const items: PublicOpportunity[] = []
  for (let offset = 0; ; offset += MAX_PAGE) {
    const page = await api.opportunities({ ...q, limit: MAX_PAGE, offset })
    items.push(...page.items)
    if (page.items.length < MAX_PAGE || items.length >= page.total) return { items, total: items.length }
  }
}

/** The slug a 301 from /api/public/opportunities/{slug}[/suffix] points at. */
export function movedSlug(err: ApiError): string | null {
  const match = err.location?.match(/\/opportunities\/([^/?#]+)/)
  return match ? decodeURIComponent(match[1]!) : null
}

export const settle = async <T,>(p: Promise<T>): Promise<T | ApiError> => {
  try {
    return await p
  } catch (err) {
    if (err instanceof ApiError) return err
    throw err
  }
}
