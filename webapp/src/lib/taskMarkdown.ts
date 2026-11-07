import { friendlyToolData, friendlyToolName, friendlyToolText } from "./toolActivity"
import { formatDuration, taskDurationSeconds } from "./format"
import type { Task, TaskLogEvent } from "./types"

type MarkdownTask = Pick<Task, "id" | "status" | "task_type" | "turns" | "error"> &
  Partial<Pick<Task, "input_tokens" | "output_tokens" | "final_text" | "log" | "started_at" | "finished_at" | "duration_seconds">>

/** A fenced block that survives backticks inside the text. */
function fence(text: string, lang = ""): string {
  const longest = Math.max(2, ...(text.match(/`+/g) ?? []).map((m) => m.length))
  const ticks = "`".repeat(longest + 1)
  return `${ticks}${lang}\n${text}\n${ticks}`
}

function inputJson(input: object | undefined): string {
  if (!input || Object.keys(input).length === 0) return ""
  try {
    return friendlyToolData(input)
  } catch {
    return ""
  }
}

function traceMarkdown(logs: TaskLogEvent[]): string {
  const byTurn = new Map<number, TaskLogEvent[]>()
  for (const entry of logs) {
    const list = byTurn.get(entry.turn) ?? []
    list.push(entry)
    byTurn.set(entry.turn, list)
  }
  const parts: string[] = []
  for (const [turn, entries] of [...byTurn.entries()].sort((a, b) => a[0] - b[0])) {
    parts.push(turn === 0 ? "#### Before the model (code)" : `#### Turn ${turn}`)
    for (const e of entries) {
      if (e.kind === "turn") {
        if (e.note?.trim()) parts.push(e.note.trim().split("\n").map((l) => `> ${l}`).join("\n"))
        continue
      }
      const verdict = e.ok === false ? "failed" : e.ok ? "ok" : "running"
      const args = inputJson(e.input)
      parts.push(`- **${friendlyToolName(e.tool)}** (${verdict})${args ? ` \`${args.replace(/`/g, "'")}\`` : ""}`)
      if (e.result_preview?.trim()) parts.push(fence(friendlyToolText(e.result_preview.trim())))
    }
  }
  return parts.join("\n\n")
}

/** One task as Markdown for pasting into an issue, doc or chat: title, stats,
 * error, closing summary and full tool trace. */
export function taskMarkdown(task: MarkdownTask, title: string): string {
  const stats: string[] = [`Status: ${task.status}`, `Type: \`${task.task_type}\``]
  if (task.turns != null) stats.push(`Turns: ${task.turns}`)
  if (task.input_tokens != null || task.output_tokens != null) {
    stats.push(`Tokens: ${(task.input_tokens ?? 0).toLocaleString()} in / ${(task.output_tokens ?? 0).toLocaleString()} out`)
  }
  const seconds = taskDurationSeconds(task)
  if (seconds != null) stats.push(`Duration: ${formatDuration(seconds)}`)
  stats.push(`Task id: \`${task.id}\``)

  const sections = [`## ${title}`, stats.map((s) => `- ${s}`).join("\n")]
  if (task.error) sections.push(`**Error:** ${task.error}`)
  if (task.final_text?.trim()) sections.push(`### Summary\n\n${task.final_text.trim()}`)
  const logs = task.log ?? []
  sections.push(logs.length ? `### Trace\n\n${traceMarkdown(logs)}` : "_No tool calls recorded._")
  return sections.join("\n\n") + "\n"
}
