import { describe, expect, it } from "vitest"
import { imageFilename, quickLinks } from "./share"
import type { ShareKit } from "./types"

const kit: ShareKit = {
  share_url: "https://blesser.example/s/abc",
  images: { square: "s", wide: "w", story: "t" },
  captions: { short: "Seed Fund (Accra). https://blesser.example/s/abc via Blesser", standard: "Seed Fund\nOffered by Accra & Co", hashtags: "" },
  disclaimer: "Blesser is not affiliated with Accra & Co.",
}

describe("quickLinks", () => {
  it("encodes each network's caption or link", () => {
    const links = Object.fromEntries(quickLinks(kit, "Seed Fund & more").map((l) => [l.label, l.href]))
    expect(Object.keys(links)).toEqual(["WhatsApp", "X", "LinkedIn", "Facebook", "Email"])
    expect(links.X).toBe(`https://x.com/intent/tweet?text=${encodeURIComponent(kit.captions.short)}`)
    expect(links.WhatsApp).toContain("Offered%20by%20Accra%20%26%20Co")
    expect(links.LinkedIn).toContain(encodeURIComponent(kit.share_url))
    expect(links.Email).toMatch(/^mailto:\?subject=Seed%20Fund%20%26%20more&body=/)
  })

  it("names downloads safely", () => {
    expect(imageFilename("gates-cambridge", "wide")).toBe("blesser-gates-cambridge-wide.png")
    expect(imageFilename("../../x y", "story")).toBe("blesser-xy-story.png")
    expect(imageFilename("", "square")).toBe("blesser-opportunity-square.png")
  })
})
