import { cn } from "../lib"

export type ArtShape = "banner" | "square"

export interface OpportunityArtProps {
  /** Opportunity id or slug; the same seed always draws the same picture. */
  seed: string
  category?: string
  kind?: string
  shape?: ArtShape
  className?: string
}

export type ArtElement =
  | { t: "rect"; x: number; y: number; w: number; h: number; r: number; fill: string }
  | { t: "circle"; cx: number; cy: number; r: number; fill?: string; stroke?: string; sw?: number }

export interface ArtSpec {
  width: number
  height: number
  ground: string
  motif: ArtElement[]
  path: ArtElement[]
  motifClass: string
}

type Motif = "arc" | "rings" | "half" | "stripes" | "dots"

// Motif colours go through --art-motif so each theme can pick its own.
const PALETTES: Record<string, { ground: string; steps: string; sun: string; motifClass: string }> = {
  startup: { ground: "var(--forest)", steps: "var(--on-forest)", sun: "var(--sun)", motifClass: "[--art-motif:var(--link)] dark:opacity-40" },
  research: { ground: "var(--forest-soft)", steps: "var(--link)", sun: "var(--sun)", motifClass: "[--art-motif:var(--surface)] dark:[--art-motif:var(--canvas)]" },
  student: { ground: "var(--sun-soft)", steps: "var(--forest)", sun: "var(--sun)", motifClass: "[--art-motif:var(--surface)] dark:[--art-motif:var(--canvas)]" },
}
const MOTIF = "var(--art-motif)"

const MOTIFS: Record<string, Motif> = {
  grant: "arc",
  incubator: "arc",
  fellowship: "rings",
  call_for_proposals: "rings",
  scholarship: "half",
  conference: "half",
  accelerator: "stripes",
  internship: "stripes",
  job: "stripes",
  competition: "dots",
  training: "dots",
}
const MOTIF_LIST: Motif[] = ["arc", "rings", "half", "stripes", "dots"]

function hash(text: string): number {
  let h = 0x811c9dc5
  for (let i = 0; i < text.length; i++) {
    h ^= text.charCodeAt(i)
    h = Math.imul(h, 0x01000193)
  }
  return h >>> 0
}

function random(seed: number): () => number {
  let a = seed
  return () => {
    a = (a + 0x6d2b79f5) | 0
    let t = Math.imul(a ^ (a >>> 15), 1 | a)
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

// Two decimals keep server and client markup identical.
const round = (n: number) => Math.round(n * 100) / 100

/** The geometry behind OpportunityArt: a pure function of seed, category, kind and shape. */
export function opportunityArt(seed: string, { category = "", kind = "", shape = "banner" }: Omit<OpportunityArtProps, "seed" | "className"> = {}): ArtSpec {
  const rnd = random(hash(`${seed}|${category}|${kind}`))
  const pick = <T,>(items: T[]) => items[Math.floor(rnd() * items.length)]
  const between = (a: number, b: number) => a + rnd() * (b - a)
  const u = 10
  const [W, H] = shape === "banner" ? [160, 70] : [70, 70]
  const palette = PALETTES[category] ?? PALETTES.research
  const motif = MOTIFS[kind] ?? pick(MOTIF_LIST)
  const elements: ArtElement[] = []
  const path: ArtElement[] = []

  // The Path: pills climbing right to a sun disc, in the logo's proportions.
  const h = (shape === "banner" ? between(1, 1.15) : between(0.9, 1)) * u
  const gap = h / 3
  const dx = h * 1.11
  const widths = [h * 2.44, h * 2, h * 1.56]
  const sunR = h * 0.72
  const pathW = h * 4.94
  const pathH = h * 5.06
  const left = rnd() < 0.5
  const x0 =
    shape === "banner"
      ? left
        ? between(1.5 * u, 3 * u)
        : between(W - pathW - 3 * u, W - pathW - 1.5 * u)
      : (W - pathW) / 2 + between(-0.3, 0.3) * u
  const floor = shape === "banner" ? H - between(0.5, 0.9) * u : (H + pathH) / 2 + between(-0.2, 0.2) * u
  const y0 = floor - h
  const topFill = rnd() < 0.15 ? "var(--bloom)" : palette.steps

  const banner = shape === "banner"
  // The motif sits on the side or corner the path leaves empty.
  const corner = banner ? { cx: left ? W : 0, cy: rnd() < 0.5 ? 0 : H } : rnd() < 0.5 ? { cx: 0, cy: 0 } : { cx: W, cy: H }
  const s = banner ? 1 : 0.6
  switch (motif) {
    case "arc":
      elements.push({ t: "circle", ...corner, r: (banner ? between(4.5, 6) : between(2.4, 3)) * u, fill: MOTIF })
      break
    case "rings":
      for (let i = 0; i < 3; i++)
        elements.push({ t: "circle", ...corner, r: (2.2 + i * 1.8) * u * s, stroke: MOTIF, sw: 0.6 * u * s })
      break
    case "half":
      elements.push(
        banner
          ? { t: "circle", cx: (left ? between(0.72, 0.82) : between(0.18, 0.28)) * W, cy: H, r: between(2.6, 3.4) * u, fill: MOTIF }
          : { t: "circle", cx: between(0.2, 0.35) * W, cy: 0, r: 1.8 * u, fill: MOTIF },
      )
      break
    case "stripes": {
      const edge = between(1.5, 2.5) * u
      const top = banner ? between(1.2, 2) * u : 0.7 * u
      for (let i = 0; i < (banner ? 4 : 2); i++) {
        const w = (banner ? between(2.5, 4) : between(1.5, 2.5)) * u
        const x = !banner ? 0.7 * u : left ? W - edge - w : edge
        elements.push({ t: "rect", x, y: top + i * 1.3 * u * s, w, h: 0.55 * u * s, r: 0.275 * u * s, fill: MOTIF })
      }
      break
    }
    case "dots": {
      const [cols, rows] = banner ? [4, 3] : [3, 2]
      const step = (banner ? 1.2 : 0.8) * u
      const ox = !banner ? 0.7 * u : left ? W - between(1.5, 2.5) * u - (cols - 1) * step : between(1.5, 2.5) * u
      const oy = banner ? between(1.4, 2.4) * u : 0.7 * u
      for (let c = 0; c < cols; c++)
        for (let r = 0; r < rows; r++)
          elements.push({ t: "circle", cx: ox + c * step, cy: oy + r * step, r: 0.32 * u * s, fill: MOTIF })
      break
    }
  }

  for (let i = 0; i < 3; i++)
    path.push({ t: "rect", x: x0 + i * dx, y: y0 - i * (h + gap), w: widths[i], h, r: h / 2, fill: i === 2 ? topFill : palette.steps })
  const top = { x: x0 + 2 * dx + widths[2], y: y0 - 2 * (h + gap) }
  path.push({ t: "circle", cx: top.x + h * 0.44, cy: top.y - h * 0.67, r: sunR, fill: palette.sun })

  const fix = (e: ArtElement): ArtElement =>
    e.t === "rect"
      ? { ...e, x: round(e.x), y: round(e.y), w: round(e.w), h: round(e.h), r: round(e.r) }
      : { ...e, cx: round(e.cx), cy: round(e.cy), r: round(e.r), ...(e.sw ? { sw: round(e.sw) } : {}) }
  return { width: W, height: H, ground: palette.ground, motif: elements.map(fix), path: path.map(fix), motifClass: palette.motifClass }
}

// Inline styles rather than presentation attributes, which not every browser resolves var() in.
function draw(e: ArtElement, i: number) {
  return e.t === "rect" ? (
    <rect key={i} x={e.x} y={e.y} width={e.w} height={e.h} rx={e.r} style={{ fill: e.fill }} />
  ) : (
    <circle key={i} cx={e.cx} cy={e.cy} r={e.r} style={{ fill: e.fill ?? "none", stroke: e.stroke, strokeWidth: e.sw }} />
  )
}

/** Deterministic geometric artwork for an opportunity, drawn from brand tokens. */
export function OpportunityArt({ seed, category, kind, shape = "banner", className }: OpportunityArtProps) {
  const art = opportunityArt(seed, { category, kind, shape })
  return (
    <svg
      viewBox={`0 0 ${art.width} ${art.height}`}
      preserveAspectRatio="xMidYMid slice"
      aria-hidden="true"
      focusable="false"
      className={cn("block overflow-hidden", shape === "banner" ? "aspect-[16/7] w-full" : "aspect-square", className)}
    >
      <rect width={art.width} height={art.height} style={{ fill: art.ground }} />
      <g className={art.motifClass}>{art.motif.map(draw)}</g>
      {art.path.map(draw)}
    </svg>
  )
}
