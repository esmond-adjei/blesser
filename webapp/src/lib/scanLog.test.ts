import { describe, expect, it } from "vitest"
import { describeEvent, errorReason, formatDuration, parseSites, runSummary, scanElapsedMs, scheduleStatus, shortUrl, siteLabel, sourceStatus } from "./scanLog"
import type { MemberSource, Scan, ScanSchedule, ScanTask } from "./types"

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

describe("source status", () => {
  const base: MemberSource = {
    id: "s1",
    url: "https://ug.edu.gh/scholarships",
    category: "student",
    note: "",
    paused: false,
    next_check_at: "2026-11-25T10:00:00",
    last_checked_at: "2026-11-18T10:00:00",
    last_scan_id: "scan1",
    finds: 3,
    created_at: "2026-11-01T10:00:00",
  }
  const now = Date.UTC(2026, 10, 20, 10, 0, 0)

  it("says when it was checked, what it found and when it runs next", () => {
    expect(sourceStatus(base, now)).toBe("Checked 2d ago, 3 found, next in 5 days")
  })

  it("covers new and paused sources", () => {
    expect(sourceStatus({ ...base, last_checked_at: null }, now)).toBe("First check within the hour")
    expect(sourceStatus({ ...base, paused: true }, now)).toBe("Paused")
  })
})

describe("repeating scans", () => {
  const base: ScanSchedule = {
    id: "s1", audience: "member", name: "", categories: ["startup"], region: "Ghana", focus: "", sites: [],
    interval_hours: 168, paused: false, pause_reason: null, next_run_at: "2026-11-24T09:00:00Z",
    last_run_at: "2026-11-17T09:00:00Z", runs: 1, last_run: null, created_at: "2026-11-10T09:00:00Z",
  }
  const now = Date.parse("2026-11-21T09:00:00Z")

  it("says when the next run is", () => {
    expect(scheduleStatus(base, now)).toBe("Next run in 3 days")
    expect(scheduleStatus({ ...base, next_run_at: "2026-11-21T08:00:00Z" }, now)).toBe("Next run today")
  })

  it("says why it paused", () => {
    expect(scheduleStatus({ ...base, paused: true, next_run_at: null, pause_reason: "empty" }, now)).toBe("Paused after weeks with nothing new")
    expect(scheduleStatus({ ...base, paused: true, next_run_at: null, pause_reason: "inactive" }, now)).toBe("Paused while you were away")
    expect(scheduleStatus({ ...base, paused: true, next_run_at: null }, now)).toBe("Paused")
  })

  it("sums up a run", () => {
    expect(runSummary({ new: 3, updated: 2 })).toBe("3 new, 2 updated")
    expect(runSummary({ new: 0, updated: 1 })).toBe("1 updated")
    expect(runSummary({ new: 0, updated: 0 })).toBe("Nothing new")
  })
})

describe("scanElapsedMs for a scan run again", () => {
  const task = (created: string, started: string, finished: string | null) =>
    ({ created_at: created, started_at: started, finished_at: finished }) as never
  it("counts only the latest run, not the first start", () => {
    const scan = {
      status: "running",
      created_at: "2026-11-20T10:00:00",
      finished_at: null,
      tasks: [
        task("2026-11-20T10:00:00", "2026-11-20T10:00:05", "2026-11-20T10:10:00"),
        task("2026-11-21T09:00:00", "2026-11-21T09:00:10", null),
      ],
    } as never
    expect(scanElapsedMs(scan, Date.parse("2026-11-21T09:02:10Z"))).toBe(120_000)
  })
})
