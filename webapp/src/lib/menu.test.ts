import { describe, expect, it } from "vitest"
import { menuKeyTarget } from "./menu"

describe("menuKeyTarget", () => {
  it("moves down and wraps to the first item", () => {
    expect(menuKeyTarget("ArrowDown", 0, 4)).toBe(1)
    expect(menuKeyTarget("ArrowDown", 3, 4)).toBe(0)
  })

  it("moves up and wraps to the last item", () => {
    expect(menuKeyTarget("ArrowUp", 2, 4)).toBe(1)
    expect(menuKeyTarget("ArrowUp", 0, 4)).toBe(3)
  })

  it("enters from outside the menu at either end", () => {
    expect(menuKeyTarget("ArrowDown", -1, 4)).toBe(0)
    expect(menuKeyTarget("ArrowUp", -1, 4)).toBe(3)
  })

  it("jumps with Home and End", () => {
    expect(menuKeyTarget("Home", 2, 4)).toBe(0)
    expect(menuKeyTarget("End", 0, 4)).toBe(3)
  })

  it("ignores other keys and empty menus", () => {
    expect(menuKeyTarget("Enter", 1, 4)).toBeNull()
    expect(menuKeyTarget("Tab", 1, 4)).toBeNull()
    expect(menuKeyTarget("ArrowDown", -1, 0)).toBeNull()
  })
})
