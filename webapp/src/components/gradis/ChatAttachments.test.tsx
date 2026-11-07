// @vitest-environment jsdom
import { renderToStaticMarkup } from "react-dom/server"
import { describe, expect, it } from "vitest"
import { attachmentSummary } from "../../lib/gradis"
import { AttachmentChips } from "./ChatAttachments"

describe("attachment chips", () => {
  it("shows a thumbnail for an image and a file icon for a document", () => {
    const items = attachmentSummary([
      { kind: "image", name: "figure.png", data_url: "data:image/png;base64,AAAA", thumb_url: "data:image/jpeg;base64,BBBB" },
      { kind: "text", name: "notes.txt", text: "Robotics" },
    ])
    expect(items).toEqual([
      { kind: "image", name: "figure.png", thumb_url: "data:image/jpeg;base64,BBBB" },
      { kind: "text", name: "notes.txt", chars: 8 },
    ])
    const html = renderToStaticMarkup(<AttachmentChips items={items} />)
    expect(html).toContain('src="data:image/jpeg;base64,BBBB"')
    expect(html).toContain("notes.txt")
    expect(html).not.toContain("Remove")
  })
})
