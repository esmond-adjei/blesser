// Read at request time so one built image serves any environment.
const env = (name: string, fallback: string) => (process.env[name] || fallback).replace(/\/+$/, "")

export const apiUrl = () => env("API_INTERNAL_URL", "http://localhost:8000")
export const appUrl = () => env("PUBLIC_APP_URL", "http://localhost:5173")
export const siteUrl = () => env("SITE_URL", "http://localhost:4321")
export const contactEmail = () => process.env.CONTACT_EMAIL || ""

export const registerUrl = (track?: string) =>
  `${appUrl()}/register${track ? `?track=${encodeURIComponent(track)}` : ""}`
export const loginUrl = () => `${appUrl()}/login`

export const PAGE_CACHE = "public, s-maxage=300, stale-while-revalidate=3600"
