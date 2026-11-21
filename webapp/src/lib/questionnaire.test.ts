import { expect, it } from "vitest"
import type { Question } from "./assistant"
import { answersOf, emptyDraft, problems } from "./questionnaire"

const questions: Question[] = [
  { id: "region", prompt: "Which region?", type: "single", options: ["Ghana", "West Africa"], allow_other: true, max_choices: null, required: true },
  { id: "kinds", prompt: "What kinds?", type: "multiple", options: ["Grants", "Fellowships", "Prizes"], allow_other: false, max_choices: 2, required: true },
  { id: "start", prompt: "From when?", type: "date", options: [], allow_other: false, max_choices: null, required: false },
]

it("asks for every required answer before sending", () => {
  expect(problems(questions, {})).toEqual({ region: "Answer this one.", kinds: "Choose at least one." })
})

it("limits multiple choice and uses the other text in place of a choice", () => {
  const drafts = {
    region: { ...emptyDraft(), choice: "Ghana", other: true, text: "  Kumasi  city " },
    kinds: { ...emptyDraft(), choices: ["Grants", "Fellowships", "Prizes"] },
  }
  expect(problems(questions, drafts)).toEqual({ kinds: "Choose up to 2." })
  drafts.kinds.choices = ["Grants"]
  expect(problems(questions, drafts)).toEqual({})
  expect(answersOf(questions, drafts)).toEqual({ region: "Kumasi city", kinds: ["Grants"] })
})

it("sends optional answers only when given", () => {
  const drafts = {
    region: { ...emptyDraft(), choice: "Ghana" },
    kinds: { ...emptyDraft(), choices: ["Prizes"] },
    start: { ...emptyDraft(), text: "2026-12-01" },
  }
  expect(answersOf(questions, drafts)).toEqual({ region: "Ghana", kinds: ["Prizes"], start: "2026-12-01" })
})
