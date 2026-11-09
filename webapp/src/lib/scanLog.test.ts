import { describe, expect, it } from "vitest"
import { describeEvent, errorReason, formatDuration, savedOpportunities, scanElapsedMs, shortUrl } from "./scanLog"
import type { Scan, ScanTask } from "./types"

const task = (log: ScanTask["log"]): ScanTask => ({
  id: "t1", task_type: "discover", target: "category:student", status: "done", error: null, final_text: null,
  turns: 3, log, input_tokens: null, output_tokens: null, created_at: "2026-11-09T10:00:00Z",
  started_at: "2026-11-09T10:00:00Z", finished_at: "2026-11-09T10:23:00Z",
})

describe("scan log", () => {
  it("writes plain lines", () => {
    expect(describeEvent({ turn: 1, tool: "search_web", input: { query: "Ghana grant 2026" }, ok: true }).text).toBe("Searched “Ghana grant 2026”")
    expect(describeEvent({ turn: 1, tool: "fetch_page", input: { url: "https://www.gea.gov.gh/youstart/" }, ok: true }).text).toBe("Read gea.gov.gh/youstart")
  })

  it("explains failures in one sentence", () => {
    const line = describeEvent({
      turn: 2, tool: "save_opportunity", input: { title: "Gates" }, ok: false,
      result_preview: JSON.stringify({ error: "source_url must be a page you fetched. Fetch it first." }),
    })
    expect(line).toMatchObject({ text: "Not saved: Gates", failed: true, reason: "source_url must be a page you fetched." })
    expect(errorReason(JSON.stringify({ error: "search_web failed: Web search is unavailable right now (x). Try later." }))).toBe(
      "Web search is unavailable right now (x).",
    )
  })

  it("collects saved opportunities with ids", () => {
    const saved = savedOpportunities([
      task([
        { turn: 1, tool: "save_opportunity", input: { title: "A" }, ok: true, result_preview: JSON.stringify({ opportunity_id: "o1", created: true, deadline_date: "2026-12-08" }) },
        { turn: 2, tool: "save_opportunity", input: { title: "B" }, ok: false, result_preview: "{}" },
        { turn: 3, tool: "save_opportunity", input: { title: "C" }, ok: true, result_preview: "not json" },
      ]),
    ])
    expect(saved.map((s) => [s.opportunityId, s.title, s.deadline])).toEqual([["o1", "A", "2026-12-08"], [null, "C", null]])
  })

  it("times a finished scan from its tasks", () => {
    const scan = { status: "done", created_at: "2026-11-09T09:59:00Z", tasks: [task([])] } as unknown as Scan
    expect(formatDuration(scanElapsedMs(scan))).toBe("23m")
    expect(formatDuration(null)).toBe("—")
    expect(shortUrl("not a url")).toBe("not a url")
  })
})
