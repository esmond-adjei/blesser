// @vitest-environment jsdom
import * as React from "react"
import { act } from "react"
import { createRoot, type Root } from "react-dom/client"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import type { CvLimitCheck, DocumentLimits } from "../../lib/types"
import { ChecksButton, LengthMeter, LimitNote } from "./LimitsAndChecks"

;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true

let host: HTMLDivElement
let root: Root

beforeEach(() => {
  host = document.createElement("div")
  document.body.appendChild(host)
  root = createRoot(host)
})
afterEach(() => {
  act(() => root.unmount())
  host.remove()
})

const render = (el: React.ReactElement) => act(() => root.render(el))
const none: DocumentLimits = { word_limit: null, page_limit: null }
const meter = (words: number, pages: number | null, limits = none) => (
  <LengthMeter words={words} pages={pages} limits={limits} own={limits} inherited={null} canEdit onSave={vi.fn()} />
)

describe("the length meter", () => {
  it("counts words, and pages once the layout is known", () => {
    render(meter(812, null))
    expect(host.textContent).toBe("812 words")
    render(meter(812, 2))
    expect(host.textContent).toBe("812 words, 2 pages")
  })

  it("counts against the limits and says when it's over", () => {
    render(meter(980, 2, { word_limit: 1000, page_limit: 2 }))
    expect(host.textContent).toBe("980 / 1,000 words, 2 / 2 pages")
    expect(host.querySelector("svg")).toBeNull()
    render(meter(1012, 2, { word_limit: 1000, page_limit: 2 }))
    expect(host.textContent).toContain("over by 12 words")
    expect(host.querySelector("button")?.className).toContain("caution")
  })
})

const check = (extra: Partial<CvLimitCheck>): CvLimitCheck => ({
  word_limit: 1000,
  page_limit: null,
  delta: 12,
  words_before: 995,
  words_after: 1007,
  pages_after: null,
  over_limit: false,
  offset: false,
  ...extra,
})

describe("a suggestion on a limited document", () => {
  it("is flagged when it puts the document over", () => {
    render(<LimitNote check={check({ over_limit: true })} />)
    expect(host.textContent).toBe("Over the limit: 1,007 of 1,000 words with this.")
  })

  it("says when a cut with it makes room, and nothing otherwise", () => {
    render(<LimitNote check={check({ offset: true, words_after: 990 })} />)
    expect(host.textContent).toContain("a cut suggested with it keeps you within the limit")
    render(<LimitNote check={check({ delta: -4 })} />)
    expect(host.textContent).toBe("")
    render(<LimitNote check={null} />)
    expect(host.textContent).toBe("")
  })
})

describe("the checks", () => {
  it("show a count only when there's something to check", () => {
    render(<ChecksButton findings={[]} onLocate={vi.fn()} />)
    expect(host.textContent).toBe("")
    render(
      <ChecksButton
        findings={[{ kind: "placeholder", message: "“TODO” looks like a placeholder left to fill.", quote: "TODO", line: 2 }]}
        onLocate={vi.fn()}
      />,
    )
    expect(host.textContent).toBe("1 to check")
  })
})
