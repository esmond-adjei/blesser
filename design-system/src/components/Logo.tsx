import { cn } from "../lib"

export type LogoVariant = "mark" | "color" | "symbol" | "symbol-white"

export interface LogoProps {
  /** "color" is the plain mark; "mark" adds the green tile, for icons and favicons. */
  variant?: LogoVariant
  className?: string
  /** Accessible name; pass "" when a visible wordmark sits beside it. */
  title?: string
}

/** Sunrise: a half sun behind three steps, mirror-symmetric on the 32-unit grid. */
export const LOGO = {
  forest: "#0f4f3b",
  sun: "#ffbe1a",
  steps: "M6 24h20v-3h-3v-3h-3v-3h-8v3h-3v3H6Z",
  sun_full: "M9 18a7 7 0 0 1 14 0Z",
  // One-colour versions need a gap between sun and steps, or the shapes merge.
  sun_cut: "M9.072 17A7 7 0 0 1 22.928 17H21v-3H11v3Z",
  // Fills the tile-less canvas: content spans x 6-26, y 11-24.
  fill: "translate(-6.4 -8.5) scale(1.4)",
} as const

export function logoSvg(variant: LogoVariant = "mark", size?: number): string {
  const dims = size ? ` width="${size}" height="${size}"` : ""
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32"${dims}>${logoBody(variant)}</svg>`
}

// In the app, --logo-ink turns the steps white on dark surfaces; files keep the brand green.
function logoBody(variant: LogoVariant, steps: string = LOGO.forest): string {
  if (variant === "mark")
    return `<rect width="32" height="32" rx="10" fill="${LOGO.forest}"/><g transform="translate(16 16) scale(1.2) translate(-16 -17.5)"><path d="${LOGO.sun_full}" fill="${LOGO.sun}"/><path d="${LOGO.steps}" fill="#ffffff"/></g>`
  if (variant === "color")
    return `<g transform="${LOGO.fill}"><path d="${LOGO.sun_full}" fill="${LOGO.sun}"/><path d="${LOGO.steps}" fill="${steps}"/></g>`
  const fill = variant === "symbol-white" ? "#ffffff" : LOGO.forest
  return `<g transform="${LOGO.fill}" fill="${fill}"><path d="${LOGO.sun_cut}"/><path d="${LOGO.steps}"/></g>`
}

/** Brand colours are fixed, not themed. */
export function Logo({ variant = "color", className, title = "Blesser" }: LogoProps) {
  const label = title ? { role: "img", "aria-label": title } : { "aria-hidden": true }
  return (
    <svg
      viewBox="0 0 32 32"
      className={cn("size-8 shrink-0", className)}
      {...label}
      dangerouslySetInnerHTML={{ __html: logoBody(variant, `var(--logo-ink, ${LOGO.forest})`) }}
    />
  )
}
