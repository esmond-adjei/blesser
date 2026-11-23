export const CARD_W = 300
export const CARD_H = 172
export const GAP = 24
/** Half the side of the square world, centred on the layout origin where cards start. */
export const WORLD_HALF = 3000
/** Room the floating composer covers at the bottom of the canvas. */
export const COMPOSER_ROOM = 160

export type Pos = { x: number; y: number }

const clamp = (n: number, min: number, max: number) => Math.min(max, Math.max(min, n))

export function freeSlot(taken: Pos[], width: number): Pos {
  const cols = Math.max(1, Math.floor((width - GAP) / (CARD_W + GAP)))
  for (let k = 0; ; k++) {
    const slot = { x: GAP + (k % cols) * (CARD_W + GAP), y: GAP + Math.floor(k / cols) * (CARD_H + GAP) }
    if (!taken.some((p) => Math.abs(p.x - slot.x) < CARD_W && Math.abs(p.y - slot.y) < CARD_H)) return slot
  }
}

/** Keeps the viewport inside the world, so the canvas pans every way until its edge. */
export function clampOffset(offset: Pos, width: number, height: number): Pos {
  return {
    x: clamp(offset.x, Math.min(0, width - WORLD_HALF), WORLD_HALF),
    y: clamp(offset.y, Math.min(0, height - WORLD_HALF), WORLD_HALF),
  }
}

export function clampCard(pos: Pos): Pos {
  return {
    x: clamp(pos.x, -WORLD_HALF, WORLD_HALF - CARD_W),
    y: clamp(pos.y, -WORLD_HALF, WORLD_HALF - CARD_H),
  }
}

/** The offset that brings a card fully into view, or null when it already is. */
export function revealOffset(spot: Pos, offset: Pos, width: number, height: number): Pos | null {
  const left = -offset.x
  const top = -offset.y
  const offX = spot.x < left || spot.x + CARD_W > left + width
  const offY = spot.y < top || spot.y + CARD_H > top + height - COMPOSER_ROOM
  if (!offX && !offY) return null
  return clampOffset({ x: offX ? GAP - spot.x : offset.x, y: offY ? GAP - spot.y : offset.y }, width, height)
}
