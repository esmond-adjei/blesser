import { renderToStaticMarkup } from "react-dom/server"
import { MemoryRouter } from "react-router-dom"
import { describe, expect, it } from "vitest"
import { Markdown } from "./Markdown"

const render = (text: string) => renderToStaticMarkup(<MemoryRouter><Markdown text={text} /></MemoryRouter>)

describe("Markdown", () => {
  it("gives each code block a labelled copy button", () => {
    const html = render("```python\nprint(1)\n```")
    expect(html).toContain('aria-label="Copy code"')
    expect(html).toContain("python")
    expect(html).toContain("print(1)")
  })

  it("opens outside links in a new tab and keeps app links in the app", () => {
    const html = render("[site](https://example.com) and [kit](/kit/answers)")
    expect(html).toMatch(/<a href="https:\/\/example.com" target="_blank" rel="noreferrer noopener">/)
    expect(html).toMatch(/<a href="\/kit\/answers"[^>]*>kit<\/a>/)
    expect(html).not.toMatch(/href="\/kit\/answers" target/)
  })

  it("scrolls wide tables inside their own frame", () => {
    const html = render("| a | b |\n|---|---|\n| 1 | 2 |")
    expect(html).toMatch(/<div class="[^"]*overflow-x-auto[^"]*"><table>/)
  })
})
