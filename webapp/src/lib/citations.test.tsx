// @vitest-environment jsdom
import { act } from "react"
import { createRoot } from "react-dom/client"
import { renderToStaticMarkup } from "react-dom/server"
import { MemoryRouter } from "react-router-dom"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { Markdown } from "../components/ui/Markdown"
import { citationIndex, citationsToMarkdown, citedKeys, type CitationSource } from "./citations"

// Tell React this is a test environment, so act() flushes updates.
(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true

const SOURCES: Record<string, CitationSource> = {
  s1: { key: "s1", kind: "candidate", id: "c1", title: "Ada Lovelace", subtitle: "MIT, EECS", href: "/dossier/c1" },
  s2: { key: "s2", kind: "web", title: "Soft Robotics Lab", url: "https://lab.example.edu", snippet: "We build soft robots." },
  s3: { key: "s3", kind: "paper", title: "Grasping", url: "https://doi.org/1", venue: "ICRA", year: 2024 },
}

function html(text: string): string {
  return renderToStaticMarkup(
    <MemoryRouter>
      <Markdown text={text} citations={citationIndex(text, SOURCES)} />
    </MemoryRouter>,
  )
}

/** The numbers of the citation chips, in document order. */
function chips(markup: string): string[] {
  return [...markup.matchAll(/data-citation="(s\d+)"[^>]*>(\d+)</g)].map((m) => `${m[1]}=${m[2]}`)
}

describe("citation numbering", () => {
  it("numbers by first appearance and reuses the number", () => {
    const text = "Lab [s2] and Ada [s1]. Again [s2][s3]."
    expect(citedKeys(text)).toEqual(["s2", "s1", "s3"])
    const index = citationIndex(text, SOURCES)
    expect(Object.fromEntries(Object.entries(index).map(([k, v]) => [k, v.n]))).toEqual({ s2: 1, s1: 2, s3: 3 })
    expect(chips(html(text))).toEqual(["s2=1", "s1=2", "s2=1", "s3=3"])
  })

  it("leaves unknown keys as plain text", () => {
    const markup = html("Known [s1], unknown [s9].")
    expect(chips(markup)).toEqual(["s1=1"])
    expect(markup).toContain("unknown [s9].")
  })

  it("never touches code spans or code blocks", () => {
    const markup = html("Inline `[s1]` and real [s2].\n\n```\nlist[s3]\n```")
    expect(chips(markup)).toEqual(["s2=1"])
    expect(markup).toContain("<code>[s1]</code>")
    expect(markup).toContain("list[s3]")
  })

  it("renders plain markdown unchanged without citations", () => {
    const markup = renderToStaticMarkup(<Markdown text="See [s1] and [a link](https://x.example)." />)
    expect(markup).toContain("See [s1] and")
    expect(markup).toContain('href="https://x.example"')
  })

  it("copies citations as Markdown footnotes", () => {
    const text = "Ada [s1] wrote `x[s1]`; lab [s2]."
    const out = citationsToMarkdown(text, citationIndex(text, SOURCES), "https://app.example")
    expect(out).toBe(
      "Ada [^1] wrote `x[s1]`; lab [^2].\n\n" +
        "[^1]: [Ada Lovelace](https://app.example/dossier/c1)\n" +
        "[^2]: [Soft Robotics Lab](https://lab.example.edu)",
    )
  })
})

describe("citation preview", () => {
  let host: HTMLDivElement
  beforeEach(() => {
    vi.useFakeTimers()
    host = document.createElement("div")
    document.body.appendChild(host)
  })
  afterEach(() => {
    vi.useRealTimers()
    host.remove()
    document.body.innerHTML = ""
  })

  it("opens the source card on focus and closes on Escape", async () => {
    const text = "Her lab [s2] builds robots."
    const root = createRoot(host)
    await act(async () => {
      root.render(
        <MemoryRouter>
          <Markdown text={text} citations={citationIndex(text, SOURCES)} />
        </MemoryRouter>,
      )
    })
    const chip = host.querySelector<HTMLButtonElement>("[data-citation=s2]")
    expect(chip).not.toBeNull()
    expect(document.querySelector("[role=dialog]")).toBeNull()

    await act(async () => {
      chip!.focus()
      vi.advanceTimersByTime(200)
    })
    const card = document.querySelector("[role=dialog]")
    expect(card).not.toBeNull()
    expect(card!.textContent).toContain("Web page")
    expect(card!.textContent).toContain("Soft Robotics Lab")
    expect(card!.textContent).toContain("We build soft robots.")
    const open = card!.querySelector("a")
    expect(open?.getAttribute("href")).toBe("https://lab.example.edu")
    expect(open?.getAttribute("rel")).toBe("noopener noreferrer")
    expect(open?.getAttribute("target")).toBe("_blank")
    // Focus stays on the chip: a preview never pulls focus away.
    expect(document.activeElement).toBe(chip)

    await act(async () => {
      chip!.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }))
    })
    expect(document.querySelector("[role=dialog]")).toBeNull()
    await act(async () => root.unmount())
  })
})

