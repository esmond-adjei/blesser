/**
 * Build-time configuration for the marketing site.
 *
 * Everything here is baked into the static HTML at build time, so it is
 * public by definition. The defaults are placeholders: set PUBLIC_APP_URL
 * (and PUBLIC_SITE_URL) in the environment when the real domains are live.
 */

const trimSlash = (value: string) => value.replace(/\/+$/, "")

/** The app this site sends people to. */
export const APP_URL = trimSlash(
  import.meta.env.PUBLIC_APP_URL?.trim() || "https://app.graduator.example",
)

/** This site's own origin, used for canonical links and the sitemap. */
export const SITE_URL = trimSlash(
  import.meta.env.PUBLIC_SITE_URL?.trim() || "https://graduator.example",
)

/**
 * The path the site is served from. Empty at a domain root, "/graduator" on
 * a GitHub Pages project site.
 */
export const BASE = (import.meta.env.BASE_URL ?? "/").replace(/\/+$/, "")

/**
 * An internal link or asset path, prefixed with the base path. Astro
 * rewrites the paths it generates (stylesheets, scripts, the canonical
 * link); the ones written by hand have to carry the base themselves.
 */
export function path(to: string): string {
  if (!to.startsWith("/") || to.startsWith("//")) return to
  // Already prefixed (e.g. WAITLIST_URL passed through path() again).
  if (BASE && (to === BASE || to.startsWith(`${BASE}/`))) return to
  return `${BASE}${to}`
}

/** Operator contact for privacy and removal requests. */
export const CONTACT_EMAIL = import.meta.env.PUBLIC_CONTACT_EMAIL?.trim() || ""

/** An absolute link into the app. */
export function appUrl(path = "/"): string {
  return `${APP_URL}${path.startsWith("/") ? path : `/${path}`}`
}

/** Where every call to action points. */
/**
 * Waitlist mode. While the app is closed to new sign-ups, every call to
 * action collects an email on /waitlist instead of sending people to
 * registration, and pricing is hidden. On unless PUBLIC_WAITLIST_MODE=off.
 */
export const WAITLIST_MODE =
  (import.meta.env.PUBLIC_WAITLIST_MODE?.trim().toLowerCase() || "on") !== "off"

/**
 * Where waitlist sign-ups are posted: Web3Forms, which emails each sign-up
 * to the owner and keeps a copy in its dashboard. The access key is meant
 * to be public (it only allows submitting to this one inbox).
 */
export const WAITLIST_ENDPOINT =
  import.meta.env.PUBLIC_WAITLIST_ENDPOINT?.trim() || "https://api.web3forms.com/submit"
export const WAITLIST_ACCESS_KEY =
  import.meta.env.PUBLIC_WAITLIST_ACCESS_KEY?.trim() || "d8ff5879-9ab5-4fdd-8067-fa8c8b442bb8"

export const WAITLIST_URL = path("/waitlist")

export const REGISTER_URL = WAITLIST_MODE ? WAITLIST_URL : appUrl("/register")
export const LOGIN_URL = appUrl("/login")

/** The contact link, or a plain sentence when no address is configured. */
export const CONTACT_HREF = CONTACT_EMAIL ? `mailto:${CONTACT_EMAIL}` : ""
