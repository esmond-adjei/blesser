import type { Answers, Question } from "./assistant"

/** What the member has picked or typed so far, per question. */
export interface Draft {
  choice: string
  choices: string[]
  /** The "Something else" text, or the answer to a text or date question. */
  text: string
  other: boolean
}

export const OTHER = "Something else"

export const emptyDraft = (): Draft => ({ choice: "", choices: [], text: "", other: false })

/** The answer this draft gives, or null when it gives none. */
export function answerOf(question: Question, draft: Draft): string | string[] | null {
  const text = draft.text.replace(/\s+/g, " ").trim()
  if (question.type === "single") {
    if (draft.other) return text || null
    return draft.choice || null
  }
  if (question.type === "multiple") {
    const values = [...draft.choices, ...(draft.other && text ? [text] : [])]
    return values.length ? values : null
  }
  return text || null
}

/** Why the questionnaire can't be sent yet, per question id. Empty when it can. */
export function problems(questions: Question[], drafts: Record<string, Draft>): Record<string, string> {
  const out: Record<string, string> = {}
  for (const question of questions) {
    const draft = drafts[question.id] ?? emptyDraft()
    const answer = answerOf(question, draft)
    if (answer === null) {
      if (question.required) out[question.id] = question.type === "multiple" ? "Choose at least one." : "Answer this one."
      continue
    }
    if (question.type === "multiple" && question.max_choices && (answer as string[]).length > question.max_choices) {
      out[question.id] = `Choose up to ${question.max_choices}.`
    }
    if (typeof answer === "string" && answer.length > 300) out[question.id] = "Keep it under 300 characters."
  }
  return out
}

export function answersOf(questions: Question[], drafts: Record<string, Draft>): Answers {
  const answers: Answers = {}
  for (const question of questions) {
    const answer = answerOf(question, drafts[question.id] ?? emptyDraft())
    if (answer !== null) answers[question.id] = answer
  }
  return answers
}
