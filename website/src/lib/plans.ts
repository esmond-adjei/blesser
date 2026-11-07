import { APP_URL } from "./site"

export interface SitePlan {
  name: string
  price: string
  period: string
  note: string
  summary: string
  featured: boolean
  features: string[]
}

export interface SiteCatalog {
  plans: SitePlan[]
  comparison: { label: string; values: (string | boolean)[] }[]
  top_up: string
  season_pass: string
  welcome: string
}

function object(value: unknown): Record<string, unknown> {
  if (typeof value !== "object" || value === null || Array.isArray(value)) throw new Error("Invalid pricing catalog")
  return Object.fromEntries(Object.entries(value))
}

function string(value: unknown): string {
  if (typeof value !== "string") throw new Error("Invalid pricing text")
  return value
}

function array(value: unknown): unknown[] {
  if (!Array.isArray(value)) throw new Error("Invalid pricing list")
  return value
}

export function parseCatalog(value: unknown): SiteCatalog {
  const data = object(value)
  const plans = array(data.plans).map((value) => {
    const p = object(value)
    if (typeof p.featured !== "boolean") throw new Error("Invalid pricing plan")
    return {
      name: string(p.name), price: string(p.price), period: string(p.period),
      note: string(p.note), summary: string(p.summary), featured: p.featured,
      features: array(p.features).map(string),
    }
  })
  if (!plans.length) throw new Error("No plans available")
  const comparison = array(data.comparison).map((value) => {
    const row = object(value)
    const values = array(row.values).map((v) => typeof v === "boolean" ? v : string(v))
    if (values.length !== plans.length) throw new Error("Invalid pricing comparison")
    return { label: string(row.label), values }
  })
  return {
    plans, comparison,
    top_up: string(data.top_up), season_pass: string(data.season_pass), welcome: string(data.welcome),
  }
}

export async function fetchCatalog(): Promise<SiteCatalog> {
  const base = (import.meta.env.PUBLIC_API_URL?.trim() || `${APP_URL}/api`).replace(/\/+$/, "")
  const response = await fetch(`${base}/billing/catalog`, { credentials: "omit", cache: "no-store", signal: AbortSignal.timeout(10000) })
  if (!response.ok) throw new Error("Pricing is unavailable")
  return parseCatalog(await response.json())
}
