import { describe, expect, it } from "vitest"
import { describeEvent, errorReason, formatDuration, parseSites, scanElapsedMs, shortUrl, siteLabel } from "./scanLog"
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

  it("reports a crawler check even when it yields no find", () => {
    expect(describeEvent({
      turn: 0, tool: "crawl_candidate", input: { url: "https://www.gea.gov.gh/youstart/" }, ok: false,
    })).toMatchObject({ text: "Checked gea.gov.gh/youstart", failed: false })
  })

  it("times a finished scan from its tasks", () => {
    const scan = { status: "done", created_at: "2026-11-09T09:59:00Z", tasks: [task([])] } as unknown as Scan
    expect(formatDuration(scanElapsedMs(scan))).toBe("23m")
    expect(formatDuration(null)).toBe("")
    expect(shortUrl("not a url")).toBe("not a url")
  })
})

describe("scan sites and catalog steps", () => {
  it("splits typed sites on spaces, commas and new lines", () => {
    expect(parseSites(" ug.edu.gh/scholarships, https://knust.edu.gh\nmest.org ")).toEqual([
      "ug.edu.gh/scholarships",
      "https://knust.edu.gh",
      "mest.org",
    ])
    expect(parseSites("  ,  ")).toEqual([])
  })

  it("labels sites without the scheme or www", () => {
    expect(siteLabel("www.ug.edu.gh/scholarships/")).toBe("ug.edu.gh/scholarships")
    expect(siteLabel("https://mest.org")).toBe("mest.org")
  })

  it("describes catalog searches and matches", () => {
    expect(describeEvent({ turn: 1, tool: "search_catalogue", input: { query: "agritech" }, ok: true }).text).toBe(
      "Searched the catalog for “agritech”",
    )
    const matched = describeEvent({
      turn: 2,
      tool: "add_catalogue_match",
      input: { opportunity_id: "o1" },
      result_preview: JSON.stringify({ opportunity_id: "o1", title: "Volta Grant", added: true }),
      ok: true,
    })
    expect(matched).toMatchObject({ kind: "save", text: "Matched Volta Grant", opportunityId: "o1" })
  })
})
