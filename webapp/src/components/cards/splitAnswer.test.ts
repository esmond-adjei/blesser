import { describe, expect, it } from "vitest"
import { splitAnswer, type TraceEvent } from "./AgentTrace"

const turn = (n: number, note: string, thought?: string): TraceEvent =>
  ({ kind: "turn", turn: n, note, ...(thought ? { thought } : {}) }) as TraceEvent
const tool = (n: number, name: string): TraceEvent => ({ turn: n, tool: name, ok: true }) as TraceEvent

describe("splitAnswer", () => {
  it("puts thoughts, in-between text and calls in the work, and the text after the last call in the answer", () => {
    const events = [
      turn(1, "Let me look that up.", "They want their runs."),
      tool(1, "list_runs"),
      turn(2, "You have two runs.", "Two came back."),
    ]
    const { work, answer } = splitAnswer(events)
    expect(answer).toBe("You have two runs.")
    expect(work.map((e) => e.tool ?? e.note)).toEqual(["Let me look that up.", "list_runs", ""])
    expect(work.at(-1)?.thought).toBe("Two came back.")
  })

  it("treats a reply with no calls as all answer, its reasoning as work", () => {
    const { work, answer } = splitAnswer([turn(1, "Hello!", "A greeting.")])
    expect(answer).toBe("Hello!")
    expect(work).toHaveLength(1)
  })

  it("has no answer yet while the model is still calling tools", () => {
    const { work, answer } = splitAnswer([turn(1, "Checking."), tool(1, "list_runs")])
    expect(answer).toBe("")
    expect(work).toHaveLength(2)
  })
})
