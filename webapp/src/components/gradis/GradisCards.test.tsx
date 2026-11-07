// @vitest-environment jsdom
import { renderToStaticMarkup } from "react-dom/server"
import { MemoryRouter } from "react-router-dom"
import { describe, expect, it } from "vitest"
import type { CitationSource } from "../../lib/citations"
import type { TaskLogEvent } from "../../lib/types"
import { GradisSavedCards } from "./GradisCards"

const ada: CitationSource = {
  key: "s1", kind: "candidate", id: "c1", title: "Ada Lovelace",
  subtitle: "MIT, EECS", href: "/dossier/c1",
}
const grace: CitationSource = {
  key: "s2", kind: "candidate", id: "c2", title: "Grace Hopper",
  subtitle: "Yale, Computer science", href: "/dossier/c2",
}

function cards(tools: TaskLogEvent[]) {
  return renderToStaticMarkup(<MemoryRouter><GradisSavedCards tools={tools} /></MemoryRouter>)
}

describe("Gradis record cards", () => {
  it("shows no card for reads, lists or citations", () => {
    expect(cards([{ turn: 1, tool: "list_candidates", ok: true, sources: [ada, grace] }])).toBe("")
    expect(cards([{ turn: 1, tool: "get_candidate", ok: true, sources: [ada] }])).toBe("")
  })

  it("shows the record Gradis chose to show", () => {
    const output = cards([{ turn: 1, tool: "show_record", ok: true, sources: [grace] }])
    expect(output).toContain("Grace Hopper")
    expect(output).toContain('href="/dossier/c2"')
    expect(output).not.toContain("Ada Lovelace")
  })

  it("shows documents and papers in their own themes", () => {
    const output = cards([
      { turn: 1, tool: "show_record", ok: true, sources: [
        { key: "s3", kind: "document", id: "d1", title: "SOP draft", subtitle: "Statement of purpose", href: "/documents/d1" },
        { key: "s4", kind: "paper", id: "p1", title: "Legged robots", subtitle: "Lin · 2024", href: "/professors/f1?paper=p1" },
      ] },
    ])
    expect(output).toContain('href="/documents/d1"')
    expect(output).toContain("Document")
    expect(output).toContain('href="/professors/f1?paper=p1"')
    expect(output).toContain("fuchsia")
  })

  it("shows a card for professors Gradis saved or updated, once each", () => {
    const output = cards([
      { turn: 1, tool: "create_professor", ok: true, input: { name: "Chelsea Finn" }, result_preview: '{"id": "f1", "name": "Chelsea Finn", "school_name": "Stanford"}' },
      { turn: 2, tool: "save_professor_papers", ok: true, input: { professor_id: "f1" }, result_preview: '{"id": "f1", "name": "Chelsea Finn"}' },
      { turn: 3, tool: "update_professor", ok: true, input: { professor_id: "f2" }, result_preview: '{"id": "f2", "name": "Sergey Levine"}' },
    ])
    expect(output.match(/href="\/professors\/f1"/g)).toHaveLength(1)
    expect(output).toContain("Chelsea Finn")
    expect(output).toContain('href="/professors/f2"')
  })

  it("does not show a failed show or the same record twice", () => {
    expect(cards([{ turn: 1, tool: "show_record", ok: false, sources: [ada] }])).toBe("")
    const twice: TaskLogEvent[] = [
      { turn: 1, tool: "show_record", ok: true, sources: [ada] },
      { turn: 2, tool: "show_record", ok: true, sources: [ada] },
    ]
    expect(cards(twice).match(/href="\/dossier\/c1"/g)).toHaveLength(1)
  })
})
