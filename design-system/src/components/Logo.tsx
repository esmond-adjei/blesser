import { useId } from "react"
import { cn } from "../lib"

export type LogoVariant = "mark" | "color" | "symbol" | "symbol-white"
/** "sunrise" plays once on mount; "climb" loops, for loads over 400ms. Both draw the colour logo. */
export type LogoMotion = "sunrise" | "climb"

export interface LogoProps {
  /** "color" is the plain mark; "mark" adds the green tile, for icons and favicons. */
  variant?: LogoVariant
  className?: string
  /** Accessible name; pass "" when a visible wordmark sits beside it. */
  title?: string
  /** Animate the colour logo. Pair "sunrise" with <Wordmark motion="sunrise" /> in a lockup. */
  motion?: LogoMotion
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
export function Logo({ variant = "color", className, title = "Blesser", motion }: LogoProps) {
  const label = title ? { role: "img", "aria-label": title } : { "aria-hidden": true }
  if (motion) return <MovingLogo motion={motion} className={className} label={label} />
  return (
    <svg
      viewBox="0 0 32 32"
      className={cn("size-8 shrink-0", className)}
      {...label}
      dangerouslySetInnerHTML={{ __html: logoBody(variant, `var(--logo-ink, ${LOGO.forest})`) }}
    />
  )
}

// The steps as three tiers so they can move one at a time. Each upper tier overlaps the
// one below by 0.2 units so no seam shows between them at rest. The sun is clipped at
// the middle step's top edge (y 18), the horizon it rises over.
function MovingLogo({ motion, className, label }: { motion: LogoMotion; className?: string; label: object }) {
  const horizon = `bl-horizon-${useId().replace(/:/g, "")}`
  return (
    <svg viewBox="0 0 32 32" className={cn("size-8 shrink-0", `bl-logo-${motion}`, className)} {...label}>
      <defs>
        <clipPath id={horizon}>
          <rect width="32" height="18" />
        </clipPath>
      </defs>
      <g transform={LOGO.fill}>
        <g clipPath={`url(#${horizon})`}>
          <path className="bl-logo-sun" d={LOGO.sun_full} fill={LOGO.sun} />
        </g>
        <g fill={`var(--logo-ink, ${LOGO.forest})`}>
          <rect className="bl-logo-step bl-logo-step-1" x="6" y="21" width="20" height="3" />
          <rect className="bl-logo-step bl-logo-step-2" x="9" y="18" width="14" height="3.2" />
          <rect className="bl-logo-step bl-logo-step-3" x="12" y="15" width="8" height="3.2" />
        </g>
      </g>
    </svg>
  )
}
