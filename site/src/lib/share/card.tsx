import type { CSSProperties, ReactNode } from "react"
import { C, artDataUri, markDataUri } from "./art"
import { SIZES, type ShareCard, type ShareFormat } from "./model"

const DISPLAY = "Bricolage Grotesque"
const TEXT = "Figtree"

/** Biggest size from `steps` whose length bound fits; the last one is the floor. */
const fit = (length: number, steps: [number, number][]) => (steps.find(([max]) => length <= max) ?? steps[steps.length - 1]!)[1]

const clamp = (lines: number): CSSProperties => ({ display: "block", lineClamp: lines, overflow: "hidden" })

type Layout = {
  pad: number
  gap: number
  eyebrow: number
  title: number
  titleLines: number
  offer: number
  offerLines: number
  org: number
  orgLines: number
  pill: number
  footer: number
  mark: number
  brand: number
  hostSize: number
}

function layout(format: ShareFormat, card: ShareCard): Layout {
  const t = card.title.length
  if (format === "wide")
    return {
      pad: 56,
      gap: 18,
      eyebrow: 22,
      title: fit(t, [[34, 58], [60, 50], [90, 42], [999, 38]]),
      titleLines: 3,
      offer: 26,
      offerLines: card.offer.length > 70 ? 2 : 1,
      org: 23,
      orgLines: 1,
      pill: 22,
      footer: 88,
      mark: 44,
      brand: 26,
      hostSize: 22,
    }
  if (format === "story")
    return {
      pad: 88,
      gap: 30,
      eyebrow: 34,
      title: fit(t, [[30, 100], [60, 86], [90, 74], [999, 64]]),
      titleLines: 5,
      offer: 42,
      offerLines: 4,
      org: 36,
      orgLines: 2,
      pill: 34,
      footer: 168,
      mark: 76,
      brand: 42,
      hostSize: 32,
    }
  return {
    pad: 64,
    gap: 20,
    eyebrow: 26,
    title: fit(t, [[30, 74], [56, 64], [84, 56], [999, 50]]),
    titleLines: 3,
    offer: 32,
    offerLines: 2,
    org: 28,
    orgLines: 1,
    pill: 26,
    footer: 120,
    mark: 60,
    brand: 32,
    hostSize: 26,
  }
}

/** Rough wrapped height of the text block, so the art can take what is left. */
function textHeight(card: ShareCard, l: Layout, width: number): number {
  const lines = (text: string, size: number, em: number, max: number) =>
    text ? Math.min(max, Math.ceil((text.length * size * em) / (width * 0.9))) : 0
  const title = lines(card.title, l.title, 0.56, l.titleLines) * l.title * 1.04
  const offer = lines(card.offer, l.offer, 0.52, l.offerLines) * l.offer * 1.3
  const org = lines(`Offered by ${card.organization}`, l.org, 0.5, l.orgLines) * l.org * 1.3
  const blocks = [l.eyebrow * 1.2, title, offer, card.organization ? org : 0].filter(Boolean)
  return blocks.reduce((a, b) => a + b, 0) + l.gap * (blocks.length - 1)
}

function Pill({ card, size }: { card: ShareCard; size: number }) {
  if (!card.deadline) return null
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: size * 0.45,
        alignSelf: "flex-start",
        padding: `${size * 0.42}px ${size * 0.8}px`,
        borderRadius: 999,
        background: card.closed ? C.separator : C.surface,
        color: card.closed ? C.inkSecondary : C.ink,
        fontFamily: TEXT,
        fontWeight: 700,
        fontSize: size,
        lineHeight: 1,
        boxShadow: "0 2px 10px rgba(20, 36, 28, 0.12)",
      }}
    >
      <div style={{ width: size * 0.45, height: size * 0.45, borderRadius: 999, background: card.closed ? C.inkSecondary : C.sun }} />
      {card.deadline}
    </div>
  )
}

function Text({ card, l }: { card: ShareCard; l: Layout }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: l.gap, minWidth: 0 }}>
      <div style={{ display: "flex", fontFamily: TEXT, fontWeight: 700, fontSize: l.eyebrow, color: C.link, letterSpacing: l.eyebrow * 0.04, textTransform: "uppercase" }}>
        {card.eyebrow}
      </div>
      <div style={{ ...clamp(l.titleLines), fontFamily: DISPLAY, fontWeight: 800, fontSize: l.title, lineHeight: 1.04, letterSpacing: -l.title * 0.02, color: C.ink }}>
        {card.title}
      </div>
      {card.offer ? (
        <div style={{ ...clamp(l.offerLines), fontFamily: TEXT, fontWeight: 600, fontSize: l.offer, lineHeight: 1.3, color: C.ink }}>{card.offer}</div>
      ) : null}
      {card.organization ? (
        <div style={{ ...clamp(l.orgLines), fontFamily: TEXT, fontWeight: 400, fontSize: l.org, lineHeight: 1.3, color: C.inkSecondary }}>
          Offered by {card.organization}
        </div>
      ) : null}
    </div>
  )
}

function Footer({ card, l }: { card: ShareCard; l: Layout }) {
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        height: l.footer,
        flexShrink: 0,
        padding: `0 ${l.pad}px`,
        background: C.forest,
        color: C.onForest,
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: l.mark * 0.32 }}>
        <div style={{ display: "flex", padding: l.mark * 0.06, borderRadius: l.mark * 0.36, background: "rgba(255,255,255,0.14)" }}>
          <img src={markDataUri(l.mark)} width={l.mark} height={l.mark} />
        </div>
        <div style={{ display: "flex", fontFamily: TEXT, fontWeight: 600, fontSize: l.brand, letterSpacing: -l.brand * 0.01 }}>
          Found on&nbsp;<span style={{ fontFamily: DISPLAY, fontWeight: 800 }}>Blesser</span>
        </div>
      </div>
      <div style={{ display: "flex", fontFamily: TEXT, fontWeight: 600, fontSize: l.hostSize, color: "rgba(255,255,255,0.78)" }}>{card.host}</div>
    </div>
  )
}

function Frame({ format, children }: { format: ShareFormat; children: ReactNode }) {
  const { width, height } = SIZES[format]
  return <div style={{ display: "flex", flexDirection: "column", width, height, background: C.canvas, color: C.ink }}>{children}</div>
}

function Art({ card, shape, width, height, radius }: { card: ShareCard; shape: "banner" | "square"; width: number; height: number; radius: number }) {
  return (
    <img
      src={artDataUri(card.seed, card.category, card.kind, shape, width, height)}
      width={width}
      height={height}
      style={{ borderRadius: radius, flexShrink: 0 }}
    />
  )
}

/** The share image: kind and category, title, offer, "Offered by", deadline, art and the Blesser footer. */
export function ShareImage({ card, format }: { card: ShareCard; format: ShareFormat }) {
  const l = layout(format, card)
  const { width, height } = SIZES[format]
  const inner = width - l.pad * 2

  if (format === "wide") {
    const art = height - l.footer - l.pad * 2
    return (
      <Frame format={format}>
        <div style={{ display: "flex", flex: 1, padding: l.pad, gap: 48, alignItems: "center" }}>
          <div style={{ display: "flex", flexDirection: "column", flex: 1, gap: 26, minWidth: 0, justifyContent: "center" }}>
            <Text card={card} l={l} />
            <Pill card={card} size={l.pill} />
          </div>
          <Art card={card} shape="square" width={art} height={art} radius={28} />
        </div>
        <Footer card={card} l={l} />
      </Frame>
    )
  }

  const artGap = format === "story" ? 64 : 40
  const available = height - l.footer - l.pad * 1.8 - artGap
  const [minArt, maxArt] = format === "story" ? [560, 1080] : [340, 560]
  const artHeight = Math.round(Math.min(maxArt, Math.max(minArt, available - textHeight(card, l, inner) - 8)))
  return (
    <Frame format={format}>
      <div style={{ display: "flex", flexDirection: "column", flex: 1, padding: l.pad, paddingBottom: l.pad * 0.8, gap: artGap }}>
        <div style={{ display: "flex", position: "relative", width: inner, height: artHeight }}>
          <Art card={card} shape={format === "story" ? "square" : "banner"} width={inner} height={artHeight} radius={format === "story" ? 44 : 32} />
          <div style={{ display: "flex", position: "absolute", top: l.pill, left: l.pill }}>
            <Pill card={card} size={l.pill} />
          </div>
        </div>
        <Text card={card} l={l} />
      </div>
      <Footer card={card} l={l} />
    </Frame>
  )
}
