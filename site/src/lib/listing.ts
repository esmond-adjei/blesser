import type { OpportunityQuery } from "./api"
import { CATEGORY_LABELS, CLOSING_WITHIN, KIND_LABELS } from "./format"

export const PAGE_SIZE = 24

export type Filters = {
  q: string
  category: string
  kind: string
  closing_within: string
  sort: "deadline" | "new"
  page: number
}

/** Unknown values are dropped rather than forwarded, so the API never sees a 422. */
export function readFilters(params: URLSearchParams): Filters {
  const pick = (key: string, allowed: string[]) => {
    const v = params.get(key) ?? ""
    return allowed.includes(v) ? v : ""
  }
  const page = Number.parseInt(params.get("page") ?? "1", 10)
  return {
    q: (params.get("q") ?? "").trim().slice(0, 200),
    category: pick("category", Object.keys(CATEGORY_LABELS)),
    kind: pick("kind", Object.keys(KIND_LABELS)),
    closing_within: pick("closing_within", CLOSING_WITHIN.map(String)),
    sort: params.get("sort") === "new" ? "new" : "deadline",
    page: Number.isFinite(page) && page > 0 ? Math.min(page, 1000) : 1,
  }
}

export function toQuery(f: Filters): OpportunityQuery {
  return {
    q: f.q || undefined,
    category: f.category || undefined,
    kind: f.kind || undefined,
    closing_within: f.closing_within ? Number(f.closing_within) : undefined,
    sort: f.sort === "new" ? "new" : undefined,
    limit: PAGE_SIZE,
    offset: (f.page - 1) * PAGE_SIZE,
  }
}

export const isFiltered = (f: Filters) => !!(f.q || f.category || f.kind || f.closing_within)

/** How many of n cards fill whole rows of cols, at most two rows; fewer than one row shows them all. */
export function wholeRows(n: number, cols: number): number {
  return n < cols ? n : Math.min(2 * cols, n - (n % cols))
}
