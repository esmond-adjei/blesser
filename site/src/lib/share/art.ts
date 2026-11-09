import { opportunityArt, type ArtElement, type ArtShape } from "@blesser/ui"

// Light-theme token values: resvg cannot resolve CSS variables.
export const C = {
  canvas: "#f6f7f1",
  surface: "#ffffff",
  separator: "#e1e5d9",
  ink: "#14241c",
  inkSecondary: "#475a4f",
  sun: "#ffbe1a",
  sunSoft: "#fff3cc",
  sunInk: "#875c00",
  forest: "#0f4f3b",
  forestSoft: "#e1f1e8",
  link: "#13704f",
  bloom: "#ff7d66",
  onForest: "#ffffff",
}

const TOKENS: Record<string, string> = {
  "var(--forest)": C.forest,
  "var(--forest-soft)": C.forestSoft,
  "var(--on-forest)": C.onForest,
  "var(--sun)": C.sun,
  "var(--sun-soft)": C.sunSoft,
  "var(--link)": C.link,
  "var(--bloom)": C.bloom,
  "var(--surface)": C.surface,
}
// The card's motif colour per category, as OpportunityArt's light theme sets --art-motif.
const MOTIF: Record<string, string> = { startup: C.link, research: C.surface, student: C.surface }

const color = (value: string | undefined, motif: string) =>
  !value ? "none" : value === "var(--art-motif)" ? motif : (TOKENS[value] ?? value)

function draw(e: ArtElement, motif: string): string {
  if (e.t === "rect")
    return `<rect x="${e.x}" y="${e.y}" width="${e.w}" height="${e.h}" rx="${e.r}" fill="${color(e.fill, motif)}"/>`
  const stroke = e.stroke ? ` stroke="${color(e.stroke, motif)}" stroke-width="${e.sw ?? 0}"` : ""
  return `<circle cx="${e.cx}" cy="${e.cy}" r="${e.r}" fill="${color(e.fill, motif)}"${stroke}/>`
}

/** OpportunityArt's drawing as a standalone SVG data URI, cropped to fill width x height. */
export function artDataUri(seed: string, category: string, kind: string, shape: ArtShape, width: number, height: number): string {
  const art = opportunityArt(seed, { category, kind, shape })
  const motif = MOTIF[category] ?? C.surface
  const svg =
    `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${art.width} ${art.height}" preserveAspectRatio="xMidYMid slice">` +
    `<rect width="${art.width}" height="${art.height}" fill="${color(art.ground, motif)}"/>` +
    art.motif.map((e) => draw(e, motif)).join("") +
    art.path.map((e) => draw(e, motif)).join("") +
    `</svg>`
  return `data:image/svg+xml;base64,${Buffer.from(svg).toString("base64")}`
}

const STEPS = "M7.75 22.5h6.5a2.25 2.25 0 0 1 0 4.5h-6.5a2.25 2.25 0 0 1 0-4.5Zm5 -6h4.5a2.25 2.25 0 0 1 0 4.5h-4.5a2.25 2.25 0 0 1 0-4.5Z"
const TOP_STEP = "M17.75 10.5h2.5a2.25 2.25 0 0 1 0 4.5h-2.5a2.25 2.25 0 0 1 0-4.5Z"

/** The Path mark, as in Logo variant="mark". */
export function markDataUri(size: number): string {
  const svg =
    `<svg xmlns="http://www.w3.org/2000/svg" width="${size}" height="${size}" viewBox="0 0 32 32">` +
    `<rect width="32" height="32" rx="10" fill="${C.forest}"/><path d="${STEPS}" fill="#ffffff"/>` +
    `<path d="${TOP_STEP}" fill="${C.bloom}"/><circle cx="24.5" cy="7.5" r="3.25" fill="${C.sun}"/></svg>`
  return `data:image/svg+xml;base64,${Buffer.from(svg).toString("base64")}`
}
