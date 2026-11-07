import * as React from "react"
import { Brain, ChevronRight, Loader2, ListTree, RefreshCw } from "lucide-react"
import { toastError, toastSuccess } from "../../lib/toast"
import { taskMarkdown } from "../../lib/taskMarkdown"
import { fmt, formatDuration, taskDurationSeconds, utcMs } from "../../lib/format"
import type { Task, TaskLogEvent } from "../../lib/types"
import { cn } from "../../lib/utils"
import { useNow } from "../../lib/useNow"
import { Button } from "../ui/button"
import { TaskActions } from "./TaskActions"
import { TaskStatusSquare } from "./TaskStatusSquare"
import { RecordCard } from "./RecordCard"
import { useTaskControls } from "../../lib/taskControls"
import { taskLabel, withFinalText } from "../../lib/taskTrace"
import { Alert, AlertDescription } from "../ui/feedback"
import { AgentTrace, ToolRow } from "./AgentTrace"
import { usePreviewParam } from "../../lib/urlParams"
import { useHealth } from "../../lib/queries"
import { useQueryClient } from "@tanstack/react-query"

type CardTask = Pick<
  Task,
  "id" | "status" | "task_type" | "target_name" | "turns" | "error"
> &
  Partial<Pick<Task, "input_tokens" | "output_tokens" | "final_text" | "log" | "started_at" | "finished_at" | "duration_seconds">>

export function TaskCard({
  task,
  runId,
  collapsed = false,
  onToggleCollapsed,
}: {
  task: CardTask
  runId: string
  /** Header only; the list's outline can collapse and expand cards. */
  collapsed?: boolean
  onToggleCollapsed?: () => void
}) {
  const { previewId, openPreview } = usePreviewParam()
  const queryClient = useQueryClient()
  const controls = useTaskControls(runId)
  // A "running" claim with no live worker is stale (the reaper requeues it
  // later): don't pulse it like real progress.
  const { data: health } = useHealth()
  const working = task.status === "running" && !health?.no_workers

  // The trace keeps a clipped copy of each turn's text; a finished task's
  // last turn shows the full final text instead.
  const logs = React.useMemo(
    () => withFinalText(task.log ?? [], task.status === "done" ? task.final_text : null),
    [task.log, task.status, task.final_text],
  )
  // Depend on the row's log reference: `logs` is a fresh array every render
  // and would defeat the memo.
  const saved = React.useMemo(() => savedItems(task.log ?? []), [task.log])

  async function copyAsMarkdown() {
    try {
      await navigator.clipboard.writeText(taskMarkdown(task, taskLabel(task.task_type, task.target_name)))
      toastSuccess("Task copied as Markdown")
    } catch (err) {
      toastError(err, "Couldn't copy the task")
    }
  }

  return (
    <div id={`task-${task.id}`} className="scroll-mt-20 space-y-3 overflow-hidden">
      <div className="flex w-full items-center gap-3 text-left">
        {onToggleCollapsed ? (
          <button
            type="button"
            onClick={onToggleCollapsed}
            aria-expanded={!collapsed}
            aria-label={collapsed ? "Expand task" : "Collapse task"}
            className="group/collapse relative flex size-4 shrink-0 cursor-pointer items-center justify-center"
          >
            <TaskStatusSquare status={task.status} working={working} className="transition-opacity group-hover/collapse:opacity-0" />
            <ChevronRight aria-hidden className={cn("absolute size-4 opacity-0 transition-[opacity,transform] group-hover/collapse:opacity-100", !collapsed && "rotate-90")} />
          </button>
        ) : (
          <TaskStatusSquare status={task.status} working={working} />
        )}

        <div className={cn("truncate text-muted-foreground", working && "italic shimmer-text")}>
          {taskLabel(task.task_type, task.target_name)}
        </div>
        <TaskStats task={task} logs={logs} working={working} />
        <TaskActions task={task} runId={runId} controls={controls} onCopy={() => void copyAsMarkdown()} />
      </div>

      {!collapsed && (
        <>
        {task.error && (
          // A pending task's note explains why it waits (a retry, OpenAlex's budget), not a failure.
          <Alert variant={task.status === "pending" || task.status === "deferred" ? "default" : "destructive"}>
            <AlertDescription>{task.error}</AlertDescription>
          </Alert>
        )}

        {logs.length === 0 ? (
          !working && <p className="type-meta">No tool calls recorded.</p>
        ) : (
          <AgentTrace events={logs} working={working} className="ml-7 text-base" textClassName="mb-6 text-foreground" />
        )}

        {saved.length > 0 && (
          <div className={cn("ml-7 grid gap-2 pr-2", saved.length > 1 && "sm:grid-cols-2")}>
            {saved.map((item) => (
              <RecordCard
                key={item.key}
                kind={item.kind}
                label={item.label}
                sublabel={item.sublabel}
                // The run page resolves the id to the record, so previews deep-link.
                onClick={() => {
                  if (item.kind === "application") void queryClient.invalidateQueries({ queryKey: ["applications"] })
                  openPreview(savedId(item))
                }}
                tooltip={`Open ${item.label} in the detail panel`}
                active={previewId === savedId(item)}
              />
            ))}
          </div>
        )}

        <div className="flex flex-wrap gap-2">
          {task.status === "error" && (
            <Button data-tooltip="Queue another attempt at this failed task" size="sm" variant="outline" onClick={() => void controls.run(task.id, "retry")} disabled={controls.busy !== null}>
              <RefreshCw className={cn(controls.busy === "retry" && "animate-spin")} /> Retry task
            </Button>
          )}
        </div>
        </>
      )}
    </div>
  )
}

/** A row without an `ok` verdict yet is still streaming: spinner, not check. */
export function ToolLogs({
  logs,
  open = false,
}: {
  logs: TaskLogEvent[]
  open?: boolean
}) {
  const [viewTool, setViewTool] = React.useState<number | null>(null)
  const [openLogs, setOpenLogs] = React.useState(open)
  const logId = React.useId()

  return (
    <div>
      <button
        type="button"
        aria-expanded={openLogs}
        aria-controls={logId}
        onClick={() => setOpenLogs(!openLogs)}
        className={cn("flex p-3 w-full bg-card rounded-xl cursor-pointer rounded-b-none items-center gap-2 text-sm font-medium text-muted-foreground", !openLogs ? "rounded-b-xl": "hover:text-foreground")}
      >
        <ListTree aria-hidden className="size-4" />
        <span>Tool logs</span>
        <ChevronRight className={cn("size-4 ml-auto transition-transform", openLogs && "rotate-90")} />
      </button>
      {/* `relative` contains the rows' absolutely positioned `sr-only` spans so they don't grow the page. */}
      <div
        id={logId}
        className="nice-scroll relative max-h-80 rounded-xl rounded-t-none bg-card divide-y divide-border overflow-y-auto max-w-500"
      >
        {openLogs && logs.map((c, idx) => c.kind === "turn" ? (
          <ThinkingRow
            key={c.turn + "-turn-" + idx}
            event={c}
            expanded={viewTool === idx}
            onToggle={() => setViewTool(viewTool === idx ? null : idx)}
          />
        ) : (
          <ToolRow
            key={c.turn + "-" + c.tool + "-" + idx}
            event={c}
            expanded={viewTool === idx}
            onToggle={() => setViewTool(viewTool === idx ? null : idx)}
          />
        ))}
      </div>
    </div>
  )
}

function ThinkingRow({ event, expanded, onToggle }: { event: TaskLogEvent; expanded: boolean; onToggle: () => void }) {
  return (
    <button type="button" aria-expanded={expanded} onClick={onToggle} className={cn("w-full cursor-pointer p-3 text-left text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring", !expanded && "hover:bg-accent/50")}>
      <span className="flex items-start gap-2">
        <Brain className="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-label="Model thinking" />
        <span className={cn("min-w-0 flex-1 whitespace-pre-wrap text-muted-foreground", !expanded && "line-clamp-2")}>
          {event.note}
        </span>
      </span>
    </button>
  )
}

/** Tokens come from the row once done and from the trace while running. */
function TaskStats({ task, logs, working }: { task: CardTask; logs: TaskLogEvent[]; working: boolean }) {
  const running = task.status === "running"
  const now = useNow(running)
  const last = logs.at(-1)
  const stored = (task.input_tokens ?? 0) + (task.output_tokens ?? 0)
  let tokens = task.input_tokens != null ? stored : null
  if (running) {
    // Earlier attempts' spend is on the row; this attempt's is in its
    // latest trace entry (entries from before this claim don't count).
    const latest = [...logs].reverse().find((e) => e.tokens != null)
    const started = utcMs(task.started_at)
    const current = latest && !(utcMs(latest.at) < started - 1000) ? (latest.tokens ?? 0) : 0
    tokens = stored + current || null
  }
  const elapsed = taskDurationSeconds(task, now)
  // The model's text for a turn lands before its tools run.
  const runningTools = last?.kind === "turn"
  const activity = runningTools ? "Running tools" : "Thinking"
  return (
    <span className="ml-auto flex shrink-0 items-center gap-1.5 tabular-nums type-caption" aria-live="off">
      {working && (
        <span className="flex items-center gap-1.5 font-sans italic">
          <Loader2 className="size-3.5 animate-spin" />
          <span className="shimmer-text hidden sm:inline">{activity}</span>
        </span>
      )}
      <span>
        {[tokens != null ? `${fmt(tokens)} tok` : null, elapsed != null ? formatDuration(elapsed) : null].filter(Boolean).join(", ")}
      </span>
    </span>
  )
}

type SavedItem =
  | { kind: "candidate"; key: string; candidateId: string; label: string; sublabel: string | null }
  | { kind: "professor"; key: string; professorId: string; label: string; sublabel: string | null }
  | { kind: "program"; key: string; programId: string; label: string; sublabel: string | null }
  | { kind: "application"; key: string; applicationId: string; label: string; sublabel: string | null }
  | { kind: "draft"; key: string; draftId: string; label: string; sublabel: string | null }

/** The id the run page's preview param uses for a saved record. */
function savedId(item: SavedItem): string {
  return item.kind === "candidate"
    ? item.candidateId
    : item.kind === "professor"
      ? item.professorId
      : item.kind === "program"
        ? item.programId
        : item.kind === "application" ? item.applicationId : item.draftId
}

/** Parse the collapsed JSON, falling back to a regex when truncation makes it invalid. */
function previewId(preview: unknown, key: string): string | null {
  if (preview == null) return null
  if (typeof preview === "object") {
    const v = (preview as Record<string, unknown>)[key]
    return typeof v === "string" && v ? v : null
  }
  if (typeof preview !== "string") return null
  try {
    const obj = JSON.parse(preview) as Record<string, unknown>
    if (obj && typeof obj[key] === "string" && obj[key]) return obj[key] as string
  } catch {
    // Truncated: fall through to the regex.
  }
  const m = preview.match(new RegExp(`"${key}"\\s*:\\s*"([^"]+)"`))
  return m ? m[1] : null
}

function inputText(input: TaskLogEvent["input"], key: string): string | null {
  if (!input || typeof input !== "object") return null
  const v = (input as Record<string, unknown>)[key]
  return typeof v === "string" && v.trim() ? v : null
}

/** Deduped by record id: retries and OpenAlex dedup hits return the same ids. */
function savedItems(logs: TaskLogEvent[]): SavedItem[] {
  const items: SavedItem[] = []
  const seen = new Set<string>()
  for (const e of logs) {
    if (e.ok === false) continue
    if (e.tool === "save_professor_record") {
      const candidateId = previewId(e.result_preview, "candidate_id")
      const professorId = previewId(e.result_preview, "professor_id")
      const label = inputText(e.input, "name") ?? "Professor"
      if (candidateId && !seen.has(`c:${candidateId}`)) {
        seen.add(`c:${candidateId}`)
        items.push({ kind: "candidate", key: `c:${candidateId}`, candidateId, label, sublabel: "Scored against your interests" })
      } else if (!candidateId && professorId && !seen.has(`p:${professorId}`)) {
        seen.add(`p:${professorId}`)
        items.push({ kind: "professor", key: `p:${professorId}`, professorId, label, sublabel: null })
      }
    } else if (e.tool === "save_program") {
      const programId = previewId(e.result_preview, "program_id")
      if (programId && !seen.has(`g:${programId}`)) {
        seen.add(`g:${programId}`)
        const school = inputText(e.input, "school_name") ?? "School"
        const program = inputText(e.input, "program_name")
        items.push({
          kind: "program", key: `g:${programId}`, programId,
          label: program ?? school,
          sublabel: program ? school : null,
        })
      }
    } else if (e.tool === "save_application" && e.ok === true) {
      const applicationId = previewId(e.result_preview, "application_id")
      if (applicationId && !seen.has(`a:${applicationId}`)) {
        seen.add(`a:${applicationId}`)
        const school = inputText(e.input, "school")
        const program = inputText(e.input, "program")
        items.push({ kind: "application", key: `a:${applicationId}`, applicationId, label: program ?? school ?? "Application", sublabel: program ? school : null })
      }
    } else if (e.tool === "save_email_draft") {
      const draftId = previewId(e.result_preview, "draft_id")
      if (draftId && !seen.has(`d:${draftId}`)) {
        seen.add(`d:${draftId}`)
        const subject = inputText(e.input, "subject")
        items.push({ kind: "draft", key: `d:${draftId}`, draftId, label: subject ?? "Email draft", sublabel: null })
      }
    }
  }
  return items
}
