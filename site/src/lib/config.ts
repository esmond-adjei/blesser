// Read at request time so one built image serves any environment.
const env = (name: string, fallback: string) => (process.env[name] || fallback).replace(/\/+$/, "")

export const apiUrl = () => env("API_INTERNAL_URL", "http://localhost:8000")
export const appUrl = () => env("PUBLIC_APP_URL", "http://localhost:5173")
export const siteUrl = () => env("SITE_URL", "http://localhost:4321")
export const contactEmail = () => process.env.CONTACT_EMAIL || ""

export const STATIC_BUILD = process.env.SITE_STATIC === "1"

const BASE = import.meta.env.BASE_URL.replace(/\/+$/, "")
/** Prefixes a root-relative path with the deploy base (e.g. /blesser on GitHub Pages). */
export const withBase = (path: string) => `${BASE}${path}`
export const stripBase = (path: string) => (BASE && (path === BASE || path.startsWith(`${BASE}/`)) ? path.slice(BASE.length) || "/" : path)

export const registerUrl = (track?: string) =>
  `${appUrl()}/register${track ? `?track=${encodeURIComponent(track)}` : ""}`
export const loginUrl = () => `${appUrl()}/login`

export const PAGE_CACHE = "public, s-maxage=300, stale-while-revalidate=3600"
