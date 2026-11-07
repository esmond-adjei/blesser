import { describe, expect, it } from "vitest"
import type { TaskLogEvent } from "./types"
import { withFinalText } from "./taskTrace"

const turn = (note: string): TaskLogEvent => ({ turn: 3, kind: "turn", note }) as TaskLogEvent

describe("withFinalText", () => {
  const full = "A long closing summary. ".repeat(10).trim()

  it("replaces a clipped last note with the full final text", () => {
    const out = withFinalText([turn(full.slice(0, 40) + "...")], full)
    expect(out.at(-1)?.note).toBe(full)
  })

  it("leaves the trace alone when the last event isn't the final turn", () => {
    const tool = { turn: 3, tool: "save_professor_record" } as TaskLogEvent
    expect(withFinalText([tool], full)).toEqual([tool])
    expect(withFinalText([turn("something else")], full).at(-1)?.note).toBe("something else")
    expect(withFinalText([turn(full.slice(0, 40))], null).at(-1)?.note).toBe(full.slice(0, 40))
  })
})
