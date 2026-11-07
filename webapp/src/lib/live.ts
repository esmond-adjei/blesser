import type { InfiniteData, QueryClient } from "@tanstack/react-query"
import type { Board, BoardTask, Paged, Task, TaskLogEvent, TraceDelta } from "./types"

/** Task-list caches under ["tasks", runId]: single pages or infinite scrollback. */
type TasksCache = Paged<Task> | InfiniteData<Paged<Task>>

function isInfinite(cache: TasksCache): cache is InfiniteData<Paged<Task>> {
  return (cache as InfiniteData<Paged<Task>>).pages !== undefined
}

// Batched and deduped: a replay on first connect would otherwise refetch once per row.
const PENDING_FLUSH_MS = 120

const pending = new WeakMap<QueryClient, { keys: Set<string>; timer: number }>()

function invalidateSoon(qc: QueryClient, key: (string | number)[]) {
  const serialized = JSON.stringify(key)
  const entry = pending.get(qc)
  if (entry) {
    entry.keys.add(serialized)
    return
  }
  const keys = new Set([serialized])
  const timer = window.setTimeout(() => {
    pending.delete(qc)
    for (const raw of keys) {
      void qc.invalidateQueries({ queryKey: JSON.parse(raw) as unknown[] })
    }
  }, PENDING_FLUSH_MS)
  pending.set(qc, { keys, timer })
}

export function flushLiveInvalidations(qc: QueryClient) {
  const entry = pending.get(qc)
  if (!entry) return
  window.clearTimeout(entry.timer)
  pending.delete(qc)
  for (const raw of entry.keys) {
    void qc.invalidateQueries({ queryKey: JSON.parse(raw) as unknown[] })
  }
}

// The SSE frame carries the full slim board row, so patch caches in place;
// unseen ids fall back to a coalesced refetch.
export function applyTaskEvent(qc: QueryClient, runId: string, row: BoardTask) {
  const oldStatus = findTaskStatus(qc, runId, row.id)

  // 1. Board columns: patch rows already in their column so cards don't jump.
  // New arrivals append; the frame has no created_at to order by, so the
  // terminal-transition refetch restores the server's order.
  const boardKey = ["board", runId]
  const board = qc.getQueryData<Board>(boardKey)
  if (board) {
    const next: Board = {}
    for (const [status, items] of Object.entries(board)) {
      if (status !== row.status) next[status] = items.filter((t) => t.id !== row.id)
    }
    const column = board[row.status] ?? []
    next[row.status] = column.some((t) => t.id === row.id)
      ? column.map((t) => (t.id === row.id ? row : t))
      : [...column, row]
    qc.setQueryData<Board>(boardKey, next)
  }

  // 2. Task lists: merge the row into cached pages, keeping the heavy fields
  // (trace, tokens) a slim row doesn't carry.
  let seen = board !== undefined && oldStatus !== undefined
  const caches = qc.getQueriesData<TasksCache>({ queryKey: ["tasks", runId] })
  for (const [key, cache] of caches) {
    if (!cache) continue
    if (isInfinite(cache)) {
      let found = false
      const pages = cache.pages.map((page) => {
        if (!page.items.some((t) => t.id === row.id)) return page
        found = true
        return {
          ...page,
          items: page.items.map((t) => (t.id === row.id ? { ...t, ...row } : t)),
        }
      })
      if (!found) continue
      seen = true
      qc.setQueryData<InfiniteData<Paged<Task>>>(key, { ...cache, pages })
    } else {
      if (!cache.items.some((t) => t.id === row.id)) continue
      seen = true
      qc.setQueryData<Paged<Task>>(key, {
        ...cache,
        items: cache.items.map((t) => (t.id === row.id ? { ...t, ...row } : t)),
      })
    }
  }
  if (!seen) {
    // Unseen id: the row may live in an unloaded page, and new tasks can mean
    // a new school or a reopened run. Refetch those once.
    invalidateSoon(qc, ["tasks", runId])
    invalidateSoon(qc, ["run", runId])
    invalidateSoon(qc, ["schools", runId])
  }

  // 3. Terminal rows carry final_text, the full trace, and token counts the
  // slim frame omits, so pull the real row once per completion.
  if (oldStatus !== undefined && oldStatus !== row.status && !isOpenStatus(row.status)) {
    invalidateSoon(qc, ["tasks", runId])
    invalidateSoon(qc, ["task", row.id])
    invalidateSoon(qc, ["board", runId])
  }
}

const OPEN_STATUSES = new Set(["pending", "running"])

function isOpenStatus(status: string): boolean {
  return OPEN_STATUSES.has(status)
}

// `trace` frames carry tool calls for a running task: from === 0 replaces the
// log, a higher from appends, and a gap refetches rather than leaving holes.
export function applyTraceEvent(qc: QueryClient, runId: string, delta: TraceDelta) {
  if (delta.events.some((event) => event.tool === "save_application" && event.ok === true)) {
    invalidateSoon(qc, ["applications"])
  }
  let patched = false

  const merge = (existing: TaskLogEvent[] | null): TaskLogEvent[] | null => {
    if (delta.from === 0) return delta.events
    const current = existing ?? []
    if (current.length < delta.from) return null // gap — can't append safely
    return [...current.slice(0, delta.from), ...delta.events]
  }

  const caches = qc.getQueriesData<TasksCache>({ queryKey: ["tasks", runId] })
  for (const [key, cache] of caches) {
    if (!cache) continue
    const patch = (t: Task): Task => {
      if (t.id !== delta.id) return t
      const log = merge(t.log)
      if (log === null) return t
      patched = true
      return { ...t, log }
    }
    if (isInfinite(cache)) {
      if (!cache.pages.some((page) => page.items.some((t) => t.id === delta.id))) continue
      qc.setQueryData<InfiniteData<Paged<Task>>>(key, {
        ...cache,
        pages: cache.pages.map((page) => ({ ...page, items: page.items.map(patch) })),
      })
    } else {
      if (!cache.items.some((t) => t.id === delta.id)) continue
      qc.setQueryData<Paged<Task>>(key, { ...cache, items: cache.items.map(patch) })
    }
  }

  // The board dialog's detail row is its own query.
  const detail = qc.getQueryData<Task>(["task", delta.id])
  if (detail) {
    const log = merge(detail.log)
    if (log !== null) {
      patched = true
      qc.setQueryData<Task>(["task", delta.id], { ...detail, log })
    }
  }

  if (!patched) {
    // Either the task isn't in any loaded page yet, or we dropped frames.
    invalidateSoon(qc, ["tasks", runId])
  }
}

/** Previous status for a task id from the board cache, then task pages. */
function findTaskStatus(qc: QueryClient, runId: string, id: string): string | undefined {
  const board = qc.getQueryData<Board>(["board", runId])
  if (board) {
    for (const [status, items] of Object.entries(board)) {
      if (items.some((t) => t.id === id)) return status
    }
  }
  const caches = qc.getQueriesData<TasksCache>({ queryKey: ["tasks", runId] })
  for (const [, cache] of caches) {
    if (!cache) continue
    const pages = isInfinite(cache) ? cache.pages : [cache]
    for (const page of pages) {
      const found = page?.items.find((t) => t.id === id)
      if (found) return found.status
    }
  }
  return undefined
}
