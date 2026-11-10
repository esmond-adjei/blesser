import { describe, expect, it } from "vitest"
import {
  applyClear,
  applyEdit,
  applyWrongField,
  describeSource,
  dismissPageEdit,
  displayValue,
  feedbackFor,
  groupRows,
  markMoved,
  notePageEdit,
} from "../src/shared/review"
import type { ReviewRow } from "../src/shared/types"
import { editorFor, initialDraft } from "../src/sidepanel/editor"
import { descriptor, review, row } from "./rows"

const GENDER = descriptor("0:1", "Gender", { tag: "select", type: "select", options: ["Man", "Woman", "Non-binary", "Prefer not to say"].map((l, i) => ({ value: `g${i}`, label: l })) })

describe("review list state", () => {
  const base = review([
    row("0:0", "First name"),
    row("0:1", "Gender", { field: GENDER, value: "g0", rule: "concept:gender", note: "From profile: gender" }),
    row("0:2", "Why us?", { status: "drafted", source: "drafted", value: "Because…", confidence: "medium" }),
    row("0:3", "Pronouns", { status: "needs", value: null, filled: null, source: null, reason: "Nothing in your kit fits" }),
  ])

  it("groups rows as Filled, Drafted and Needs you", () => {
    const g = groupRows(base.rows)
    expect([g.filled, g.drafted, g.needs].map((list) => list.map((r) => r.key))).toEqual([["0:0", "0:1"], ["0:2"], ["0:3"]])
  })

  it("shows option labels, not option codes", () => {
    expect(displayValue(base.rows[1])).toBe("Man")
  })

  it("edits move a row to Filled as the member's remembered change; an empty edit is a clear", () => {
    const edited = applyEdit(base, "0:3", "she/her").rows[3]
    expect(edited).toMatchObject({ status: "filled", value: "she/her", source: "member", rule: "correction", reason: "" })
    expect(describeSource(edited)).toBe("Your change, remembered for this site")
    expect(applyEdit(base, "0:0", "").rows[0]).toMatchObject({ status: "needs", value: null, reason: "You cleared it" })
  })

  it("clear and wrong field move a row to Needs you and keep what Blesser first filled", () => {
    expect(applyClear(base, "0:0").rows[0]).toMatchObject({ status: "needs", value: null, filled: { value: "Ama" } })
    const wrong = applyWrongField(base, "0:1").rows[1]
    expect(wrong.status).toBe("needs")
    expect(wrong.reason).toMatch(/wrong field/)
  })

  it("notices page edits only when the value really changed, comparing option labels too", () => {
    expect(notePageEdit(base, "0:1", "Man").rows[1].pageEdit).toBeNull()
    expect(notePageEdit(base, "0:1", "Woman").rows[1].pageEdit).toEqual({ value: "Woman" })
    expect(notePageEdit(base, "0:0", " ama ").rows[0].pageEdit).toBeNull()
    expect(notePageEdit(base, "0:3", "she/her").rows[3].pageEdit).toBeNull()
    const kept = dismissPageEdit(notePageEdit(base, "0:0", "Ama Serwaa"), "0:0").rows[0]
    expect(kept).toMatchObject({ value: "Ama Serwaa", pageEdit: null })
  })

  it("a navigation outranks a new step", () => {
    expect(markMoved(base, "step").moved).toBe("step")
    expect(markMoved(markMoved(base, "navigated"), "step").moved).toBe("navigated")
  })
})

describe("plain-words sources", () => {
  const say = (extra: Partial<ReviewRow>) => describeSource(row("0:0", "x", extra))
  it("covers rules from the matcher", () => {
    expect(say({ rule: "inferred:nationality", value: "Ghana", confidence: "medium" })).toBe("From your nationality")
    expect(say({ rule: "correction" })).toBe("Your earlier correction")
    expect(say({ rule: "model:choice", source: "drafted" })).toBe("Chosen by Blesser, review")
    expect(say({ rule: "model:draft", source: "drafted" })).toBe("Drafted by Blesser, review")
    expect(say({ rule: "inferred:address_parts" })).toBe("From your address")
    expect(say({ rule: "qualifier:current_employer" })).toBe("From your current employer")
    expect(say({ rule: "option:normalized", source: "profile", note: "From profile: country of residence" })).toBe("From your country of residence")
    expect(say({ rule: "qualifier:education.country", value: "Ghana" })).toBe("From your education: country")
    expect(say({ rule: "concept:gender", note: "Matched 'Male' to 'Man'" })).toBe("Matched 'Male' to 'Man'")
    expect(describeSource(row("0:1", "Gender", { field: GENDER, value: "g0", rule: "concept:gender", note: "From profile: gender" }))).toBe("Matched your gender to 'Man'")
  })
  it("falls back to the source when there is no rule", () => {
    expect(say({ source: "profile", note: "From profile: given_name" })).toBe("From your given name")
    expect(say({ source: "drafted" })).toBe("Drafted by Blesser, review")
    expect(say({ source: "answer" })).toBe("From your saved answers")
    expect(say({ source: "document", note: "Default cv" })).toBe("Your default CV")
    expect(say({ source: "project", rule: "qualifier:name" })).toBe("From your project: name")
  })
})

describe("feedback payloads", () => {
  it("match the FillFeedback contract", () => {
    const r = review([row("0:1", "Gender", { field: GENDER, value: "g0", rule: "concept:gender" })])
    expect(feedbackFor(r, r.rows[0], { value: "Woman" })).toEqual({
      page: { url: "https://apply.example.org/form?step=1", host: "apply.example.org" },
      field: GENDER,
      filled: { value: "g0", source: "profile", rule: "concept:gender" },
      corrected: { value: "Woman" },
    })
    const blank = row("0:3", "Pronouns", { status: "needs", value: null, filled: null })
    expect(feedbackFor(r, blank, { wrong_field: true })).toMatchObject({ filled: { value: null, source: "unfilled", rule: null }, corrected: { wrong_field: true } })
  })
})

describe("panel editor", () => {
  it("picks a control from the field and starts from the option's value", () => {
    expect(editorFor(GENDER).kind).toBe("select")
    expect(initialDraft({ field: GENDER, value: "Woman" })).toBe("g1")
    const multi = descriptor("0:5", "Programmes", { type: "checkbox", options: [{ value: "a", label: "Accelerator" }, { value: "g", label: "Grants" }] })
    expect(editorFor(multi).kind).toBe("multi")
    expect(initialDraft({ field: multi, value: ["Grants"] })).toEqual(["g"])
    const terms = descriptor("0:6", "I agree", { type: "checkbox", options: [{ value: "on", label: "I agree" }] })
    expect(initialDraft({ field: terms, value: "on" })).toBe("Yes")
    expect(editorFor(descriptor("0:7", "Born", { type: "date" }))).toEqual({ kind: "input", inputType: "date" })
    expect(editorFor(descriptor("0:8", "Bio", { tag: "textarea", type: "textarea" })).kind).toBe("textarea")
  })
})
