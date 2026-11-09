const DEV_SITE_URL = "http://localhost:4321"

/** The public site's origin from VITE_SITE_URL; unset means the dev site, empty means none (null). */
export function resolveSiteUrl(raw: string | undefined): string | null {
  if (raw === undefined) return DEV_SITE_URL
  const value = raw.trim().replace(/\/+$/, "")
  return value || null
}

export const SITE_URL = resolveSiteUrl(import.meta.env.VITE_SITE_URL as string | undefined)
