import { describe, expect, it } from "vitest"
import { parseTheme, resolveTheme } from "./theme"

describe("parseTheme", () => {
  it("keeps the explicit choices", () => {
    expect(parseTheme("light")).toBe("light")
    expect(parseTheme("dark")).toBe("dark")
    expect(parseTheme("system")).toBe("system")
  })

  it("falls back to system for missing or unknown values", () => {
    expect(parseTheme(null)).toBe("system")
    expect(parseTheme("sepia")).toBe("system")
    expect(parseTheme(undefined)).toBe("system")
  })
})

describe("resolveTheme", () => {
  it("follows the OS for system", () => {
    expect(resolveTheme("system", true)).toBe("dark")
    expect(resolveTheme("system", false)).toBe("light")
  })

  it("ignores the OS for an explicit choice", () => {
    expect(resolveTheme("light", true)).toBe("light")
    expect(resolveTheme("dark", false)).toBe("dark")
  })
})
