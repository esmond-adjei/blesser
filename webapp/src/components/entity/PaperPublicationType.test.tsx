import { renderToStaticMarkup } from "react-dom/server"
import { expect, it } from "vitest"
import { PaperCard } from "./detail"

it("shows a paper's publication type when it is known", () => {
  const html = renderToStaticMarkup(<PaperCard paper={{ title: "Paper", abstract: null, year: 2025, url: null, publication_type: "conference-paper" }} />)
  expect(html).toContain("Conference paper")
})
