import { renderToStaticMarkup } from "react-dom/server"
import { MemoryRouter } from "react-router-dom"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { describe, expect, it } from "vitest"
import type { AssistantSource } from "../../lib/assistant"
import { RecordCards } from "./RecordCards"

const notice = (minutes: number): AssistantSource => ({
  key: "p1",
  kind: "scan_limit",
  id: "scan-limit",
  title: "No scans left this hour",
  detail: "You can start 3 scans an hour and 10 a day.",
  url: "/scans",
  opportunity: null,
  preview: true,
  available_at: new Date(Date.now() + minutes * 60_000).toISOString().slice(0, 19),
})

const render = (source: AssistantSource) =>
  renderToStaticMarkup(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter><RecordCards sources={[source]} onOpen={() => {}} /></MemoryRouter>
    </QueryClientProvider>,
  )

describe("scan limit card", () => {
  it("says when the next scan frees up", () => {
    const html = render(notice(23))
    expect(html).toContain("No scans left this hour")
    expect(html).toMatch(/Your next scan frees up at .+, in 2[34] min\./)
    expect(html).toContain("View scans")
    expect(html).not.toContain('aria-label="Records"')
  })

  it("invites a new scan once the time has passed", () => {
    const html = render(notice(-5))
    expect(html).toContain("You can scan again")
    expect(html).toContain("Start a scan")
  })
})
