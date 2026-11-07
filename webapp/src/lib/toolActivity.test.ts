import { describe, expect, it } from "vitest"
import { toolActivity } from "./toolActivity"

describe("tool action descriptions", () => {
  it("uses the search query rather than the first parameter", () => {
    const action = toolActivity({ tool: "search_web", input: { limit: 5, query: "robotics PhD Ghana" }, ok: true })
    expect(action.label).toBe("Searched the web")
    expect(action.detail).toBe("robotics PhD Ghana")
  })

  it.each([
    ["fetch_page", { offset: 200, url: "https://example.edu/faculty" }, "Read page", "https://example.edu/faculty"],
    ["save_program", { run_id: "internal", school_name: "University of Ghana", program_name: "Computer Science" }, "Saved programme", "Computer Science, University of Ghana"],
    ["find_openalex_author", { institution_hint: "MIT", name: "Ada Lovelace" }, "Looked up author", "Ada Lovelace, MIT"],
    ["save_professor_record", { bio: "Long biography", name: "Ada Lovelace" }, "Saved professor", "Ada Lovelace"],
    ["save_email_draft", { body: "Private email body", candidate_id: "c1", subject: "Prospective PhD student" }, "Saved email draft", "Prospective PhD student"],
    ["spawn_professor_research", { names: ["Ada", "Grace", "Alan", "Edsger", "Barbara"] }, "Queued professor research", "Ada, Grace, Alan +2 more"],
    ["get_author_works", { openalex_id: "A123" }, "Read publications", "Author A123"],
    ["cv_suggest_changes", { document_id: "cv1", suggestions: [{ after: "Updated text" }, { after: "Another edit" }] }, "Suggested CV improvements", "2 suggested changes, CV cv1"],
    ["list_runs", {}, "Listed research runs", ""],
  ])("describes %s with relevant context", (tool, input, label, detail) => {
    const action = toolActivity({ tool, input, ok: true })
    expect({ label: action.label, detail: action.detail }).toEqual({ label, detail })
    expect(action.detail).not.toContain("[object Object]")
  })

  it("distinguishes running actions from completed actions", () => {
    expect(toolActivity({ tool: "search_web", input: { query: "robotics" } }).label).toBe("Searching the web")
    expect(toolActivity({ tool: "fetch_page", ok: false }).label).toBe("Reading page")
  })

  it.each([
    ["pause", "Paused research run"],
    ["resume", "Resumed research run"],
    ["cancel", "Cancelled research run"],
  ])("describes the %s run action", (action, expected) => {
    expect(toolActivity({ tool: "set_run_status", input: { action, run_id: "r1" }, ok: true }).label).toBe(expected)
  })

  it("describes the actual professor review decision", () => {
    expect(toolActivity({ tool: "review_candidate", input: { approved: false }, ok: true }).label).toBe("Rejected professor match")
    expect(toolActivity({ tool: "review_candidate", input: { approved: true } }).label).toBe("Approving professor match")
  })

  it("handles new tools and missing or structured parameters without leaking arbitrary values", () => {
    expect(toolActivity({ tool: "check_new_source", input: { token: "secret", body: { text: "hidden" } }, ok: true })).toMatchObject({ label: "Workspace action", detail: "" })
    expect(toolActivity({ tool: "search_web", input: { query: {} }, ok: true }).detail).toBe("")
    expect(toolActivity({})).toMatchObject({ label: "Workspace action", detail: "" })
  })
})
