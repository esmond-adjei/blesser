import { describe, expect, it } from "vitest"
import { parseDetail } from "./api"

describe("parseDetail", () => {
  it("reads a validation list as sentences", () => {
    const body = JSON.stringify({ detail: [{ type: "value_error", loc: ["body", "email"], msg: "Value error, enter a valid email" }] })
    expect(parseDetail(body).message).toBe("Email: Enter a valid email.")
  })
  it("keeps string and message details", () => {
    expect(parseDetail('{"detail":"Nope."}').message).toBe("Nope.")
    expect(parseDetail('{"detail":{"message":"Slow down."}}').message).toBe("Slow down.")
  })
  it("never shows raw JSON or HTML", () => {
    expect(parseDetail("<html>502</html>").message).toBe("Something went wrong. Try again.")
    expect(parseDetail('{"oops":1}').message).toBe("Something went wrong. Try again.")
  })
})
