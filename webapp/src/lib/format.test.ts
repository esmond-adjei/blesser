import { describe, expect, it } from "vitest"
import { accountName, initials } from "./format"

describe("accountName", () => {
  it("prefers the display name, else the email's local part", () => {
    expect(accountName({ display_name: " Ama Mensah ", email: "ama@x.org" })).toBe("Ama Mensah")
    expect(accountName({ display_name: null, email: "kofi.boateng@x.org" })).toBe("kofi.boateng")
    expect(accountName(null)).toBe("")
  })
})

describe("initials", () => {
  it("takes the first and last word", () => {
    expect(initials("Ama Serwaa Mensah")).toBe("AM")
    expect(initials("kofi.boateng")).toBe("KB")
    expect(initials("ama")).toBe("A")
    expect(initials("Ama Probe 22")).toBe("AP")
    expect(initials("")).toBe("?")
  })
})
