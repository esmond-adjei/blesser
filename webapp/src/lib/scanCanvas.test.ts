import { describe, expect, it } from "vitest"
import { CARD_H, CARD_W, COMPOSER_ROOM, GAP, WORLD_HALF, clampCard, clampOffset, focusOffset, freeSlot, revealOffset } from "./scanCanvas"

describe("scan canvas", () => {
  it("pans every way from the start until the world edge", () => {
    expect(clampOffset({ x: 500, y: 400 }, 1200, 800)).toEqual({ x: 500, y: 400 })
    expect(clampOffset({ x: -500, y: -400 }, 1200, 800)).toEqual({ x: -500, y: -400 })
    expect(clampOffset({ x: 99_999, y: 99_999 }, 1200, 800)).toEqual({ x: WORLD_HALF, y: WORLD_HALF })
    expect(clampOffset({ x: -99_999, y: -99_999 }, 1200, 800)).toEqual({ x: 1200 - WORLD_HALF, y: 800 - WORLD_HALF })
  })

  it("keeps cards inside the world, including up and left of the start", () => {
    expect(clampCard({ x: -200, y: -100 })).toEqual({ x: -200, y: -100 })
    expect(clampCard({ x: -99_999, y: 99_999 })).toEqual({ x: -WORLD_HALF, y: WORLD_HALF - CARD_H })
  })

  it("places new cards in the first free grid slot", () => {
    const first = freeSlot([], 1000)
    expect(first).toEqual({ x: GAP, y: GAP })
    expect(freeSlot([first], 1000)).toEqual({ x: GAP + CARD_W + GAP, y: GAP })
  })

  it("brings an off-screen card into view and leaves a visible one alone", () => {
    expect(revealOffset({ x: GAP, y: GAP }, { x: 0, y: 0 }, 1200, 800)).toBeNull()
    expect(revealOffset({ x: GAP, y: 2000 }, { x: 0, y: 0 }, 1200, 800)).toEqual({ x: 0, y: GAP - 2000 })
    expect(revealOffset({ x: -900, y: GAP }, { x: 0, y: 0 }, 1200, 800)).toEqual({ x: GAP + 900, y: 0 })
  })

  it("centres the newest cards, or the first when they don't all fit", () => {
    expect(focusOffset([], 1200, 800)).toBeNull()
    const spot = { x: 1000, y: 900 }
    const centred = focusOffset([spot], 1200, 800)!
    expect(centred.x + spot.x + CARD_W / 2).toBe(600)
    expect(centred.y + spot.y + CARD_H / 2).toBe((800 - COMPOSER_ROOM) / 2)
    const far = { x: spot.x + 5000, y: spot.y }
    expect(focusOffset([spot, far], 1200, 800)).toEqual(centred)
  })
})
