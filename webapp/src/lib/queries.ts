import * as React from "react"
import { keepPreviousData, useInfiniteQuery, useQueries, useQuery, useQueryClient } from "@tanstack/react-query"
import { API_BASE, getAccessToken } from "./api"
import * as api from "./api"
import type { BoardTask, Candidate, Draft, ListParams, School, TraceDelta } from "./types"
import { runTitle } from "./format"

// Live events patch caches in place; this only bounds remount refetches.
const IDLE_STALE_MS = 30_000

export function useReady() {
  return useQuery({
    queryKey: ["ready"],
    queryFn: api.getReady,
    refetchInterval: 15_000,
    retry: 1,
  })
}

// 401/403 means the session lapsed, not a backend outage — don't retry.
function retryUnlessAuth(failureCount: number, error: unknown) {
  if (error instanceof api.ApiError && (error.status === 401 || error.status === 403))
    return false
  return failureCount < 1
}

export function useHealth(enabled = true) {
  return useQuery({
    queryKey: ["health"],
    queryFn: api.getHealth,
    refetchInterval: 15_000,
    retry: retryUnlessAuth,
    enabled,
  })
}

export function useWorkers(enabled = true) {
  return useQuery({
    queryKey: ["workers"],
    queryFn: api.listWorkers,
    refetchInterval: 15_000,
    retry: retryUnlessAuth,
    enabled,
  })
}

export function useRuns(pollMs?: number) {
  return useQuery({
    queryKey: ["runs"],
    queryFn: api.listRuns,
    refetchInterval: pollMs,
    staleTime: IDLE_STALE_MS,
  })
}

const RUN_PAGE = 30

/** The sidebar's runs, a page at a time as it scrolls. Shares the "runs"
 * prefix, so every invalidation of the run list refreshes it too. */
export function useRunPages(pollMs?: number) {
  return useInfiniteQuery({
    queryKey: ["runs", "pages"],
    queryFn: ({ pageParam }) => api.listRunsPage(RUN_PAGE, pageParam),
    initialPageParam: 0,
    getNextPageParam: (lastPage, allPages) =>
      lastPage.length < RUN_PAGE ? undefined : allPages.reduce((n, page) => n + page.length, 0),
    refetchInterval: pollMs,
    staleTime: IDLE_STALE_MS,
  })
}

export function useRun(runId: string) {
  return useQuery({
    queryKey: ["run", runId],
    queryFn: () => api.getRun(runId),
    staleTime: IDLE_STALE_MS,
  })
}

/** Research allowance per cap; polls with the run while it is live. */
export function useRunBudget(runId: string, pollMs?: number | false) {
  return useQuery({
    queryKey: ["budget", runId],
    queryFn: () => api.getRunBudget(runId),
    refetchInterval: pollMs,
    enabled: runId !== "",
  })
}

export function useRunUsage(runId: string, enabled = true) {
  return useQuery({
    queryKey: ["usage", runId],
    queryFn: () => api.getUsage(runId),
    enabled,
  })
}

export function useRunRefusals(runId: string, enabled = true) {
  return useQuery({
    queryKey: ["refusals", runId],
    queryFn: () => api.getRefusals(runId),
    enabled,
  })
}

export function useDeletePreview(runId: string, enabled: boolean) {
  return useQuery({
    queryKey: ["delete-preview", runId],
    queryFn: () => api.getDeletePreview(runId),
    enabled,
  })
}

export function useRunBoard(runId: string, pollMs?: number | false) {
  return useQuery({
    queryKey: ["board", runId],
    queryFn: () => api.getBoard(runId),
    refetchInterval: pollMs,
    staleTime: IDLE_STALE_MS,
  })
}

// Offset-window pages: the cache key omits offset, so scrolling appends
// instead of swapping pages. The next offset follows the last page's own
// offset, not a count of the loaded pages, so it can't repeat a window.
export function useRunTasksInfinite(
  runId: string,
  base: Omit<ListParams, "offset">,
  pollMs?: number | false,
) {
  return useInfiniteQuery({
    queryKey: ["tasks", runId, base],
    queryFn: ({ pageParam }) => api.listTasks(runId, { ...base, offset: pageParam }),
    initialPageParam: 0,
    getNextPageParam: (lastPage, _allPages, lastOffset) => {
      const next = lastOffset + lastPage.items.length
      return lastPage.items.length > 0 && next < lastPage.total ? next : undefined
    },
    refetchInterval: pollMs,
    staleTime: IDLE_STALE_MS,
  })
}

export function useRunSchools(runId: string, pollMs?: number | false, enabled = true) {
  return useQuery({
    queryKey: ["schools", runId],
    queryFn: () => api.listRunSchools(runId),
    refetchInterval: pollMs,
    staleTime: IDLE_STALE_MS,
    enabled,
  })
}

export function useRunCandidates(runId: string, params: ListParams, pollMs?: number | false, enabled = true) {
  return useQuery({
    queryKey: ["candidates", runId, params],
    queryFn: () => api.listRunCandidates(runId, params),
    refetchInterval: pollMs,
    placeholderData: keepPreviousData,
    staleTime: IDLE_STALE_MS,
    enabled,
  })
}

// Callers needing every row pass a high limit.
export function useCandidateSearch(params: ListParams, enabled = true) {
  return useQuery({
    queryKey: ["candidate-search", params],
    queryFn: () => api.searchCandidates(params),
    placeholderData: keepPreviousData,
    staleTime: IDLE_STALE_MS,
    enabled,
  })
}

export interface ScopedSchool {
  school: School
  /** The newest run that uses the school. */
  runId: string
  runTitle: string
  /** Every run that uses it, oldest first. */
  runIds: string[]
}

export function useAllRunSchools(enabled = true) {
  const { data: runs } = useRuns()
  const query = useQuery({
    queryKey: ["account-schools"],
    queryFn: api.listSchools,
    enabled,
  })
  const titles = React.useMemo(() => new Map((runs ?? []).map((r) => [r.id, runTitle(r)])), [runs])
  const items: ScopedSchool[] = React.useMemo(
    () =>
      (query.data ?? []).map((school) => {
        const runIds = school.run_ids ?? []
        const runId = runIds[runIds.length - 1] ?? ""
        return { school, runId, runTitle: titles.get(runId) ?? "", runIds }
      }),
    [query.data, titles],
  )
  const isLoading = enabled && query.isLoading
  return { items, isLoading, isError: query.isError, refetch: () => query.refetch() }
}

/** A school's faculty across every run, each with their best candidate. */
export function useSchoolFaculty(schoolId: string | null | undefined) {
  return useQuery({
    queryKey: ["faculty", "school", schoolId],
    queryFn: () => api.listSchoolFaculty(schoolId as string),
    enabled: !!schoolId,
  })
}

/** Every professor the account has, matched or not. */
export function useProfessors() {
  return useQuery({ queryKey: ["faculty", "all"], queryFn: api.listProfessors })
}

export function useRunDrafts(runId: string, pollMs?: number | false, enabled = true) {
  return useQuery({
    queryKey: ["drafts", runId],
    queryFn: () => api.listRunDrafts(runId),
    refetchInterval: pollMs,
    staleTime: IDLE_STALE_MS,
    enabled,
  })
}

export interface OutboxItem {
  draft: Draft
  runId: string
  runTitle: string
}

// Every run's drafts tagged with their run. Keys match useRunDrafts, so the
// outbox and review tabs share cache.
export function useOutboxDrafts(enabled = true) {
  const { data: runs } = useRuns()
  const queries = useQueries({
    queries: (runs ?? []).map((run) => ({
      queryKey: ["drafts", run.id],
      queryFn: () => api.listRunDrafts(run.id),
      enabled,
    })),
  })
  // Not memoized on purpose: fresh wrapper objects would retrigger consumer effects.
  const items: OutboxItem[] = (runs ?? []).flatMap((run, i) =>
    (queries[i]?.data ?? []).map((draft) => ({
      draft,
      runId: run.id,
      runTitle: runTitle(run),
    })),
  )
  const isLoading = !runs || queries.some((q) => q.isLoading)
  const isError = queries.some((q) => q.isError)
  const refetch = () => Promise.all(queries.map((q) => q.refetch()))
  return { items, isLoading, isError, refetch }
}

export function useCandidate(candidateId: string | null | undefined) {
  return useQuery({
    queryKey: ["candidate", candidateId],
    queryFn: () => api.getCandidate(candidateId as string),
    enabled: !!candidateId,
  })
}

export function useCandidateDrafts(candidateId: string, enabled = true) {
  return useQuery({
    queryKey: ["candidate-drafts", candidateId],
    queryFn: () => api.listCandidateDrafts(candidateId),
    staleTime: IDLE_STALE_MS,
    enabled: enabled && candidateId !== "",
  })
}

/** A saved record opened from a task card, resolved against this run. */
export type RunPreviewItem =
  | { kind: "candidate"; candidate: Candidate }
  | { kind: "draft"; draft: Draft }
  | { kind: "professor"; professorId: string; name: string }
  | { kind: "application"; applicationId: string; name: string }
  | { kind: "program"; programId: string; name: string }

// Shared with the dossier single-scope query, so both reuse one cache entry.
const PREVIEW_CANDIDATE_PARAMS: ListParams = { status: "all", sort: "score", limit: 100, offset: 0 }

// Resolve ?preview= against the run's own lists; unscored professors need a
// single record probe. Memoized so publish effects don't rerun every render.
export function useRunPreviewItem(
  runId: string,
  previewId: string | null,
): { item: RunPreviewItem | null; isLoading: boolean } {
  const active = !!previewId && !!runId
  const cands = useRunCandidates(runId, PREVIEW_CANDIDATE_PARAMS, false, active)
  const drafts = useRunDrafts(runId, false, active)
  const schools = useRunSchools(runId, false, active)

  const cand = previewId ? (cands.data?.items.find((c) => c.id === previewId) ?? null) : null
  const draft = previewId ? (drafts.data?.find((d) => d.id === previewId) ?? null) : null
  const prog = previewId
    ? ((schools.data ?? []).flatMap((s) => s.programs).find((p) => p.id === previewId) ?? null)
    : null
  const listsLoading = cands.isLoading || drafts.isLoading || schools.isLoading
  // An unscored professor has no candidate row, so probe only after the lists miss.
  const needProfProbe = active && !listsLoading && !cand && !draft && !prog
  const profProbe = useProfessor(needProfProbe && previewId ? previewId : null)
  const applications = useQuery({ queryKey: ["applications"], queryFn: api.listApplications, enabled: needProfProbe })
  const application = previewId ? applications.data?.find((item) => item.id === previewId) : undefined

  return React.useMemo(() => {
    if (!previewId) return { item: null, isLoading: false }
    if (listsLoading) return { item: null, isLoading: true }
    if (cand) return { item: { kind: "candidate", candidate: cand } as RunPreviewItem, isLoading: false }
    if (draft) return { item: { kind: "draft", draft } as RunPreviewItem, isLoading: false }
    if (prog)
      return {
        item: { kind: "program", programId: prog.id, name: prog.name } as RunPreviewItem,
        isLoading: false,
      }
    if (application) return { item: { kind: "application", applicationId: application.id, name: application.program || application.school } as RunPreviewItem, isLoading: false }
    if (profProbe.isLoading || applications.isLoading) return { item: null, isLoading: true }
    if (profProbe.data)
      return {
        item: { kind: "professor", professorId: profProbe.data.id, name: profProbe.data.name } as RunPreviewItem,
        isLoading: false,
      }
    return { item: null, isLoading: false }
  }, [previewId, listsLoading, cand, draft, prog, application, applications.isLoading, profProbe.isLoading, profProbe.data])
}

export function useProgram(programId: string | null) {
  return useQuery({
    queryKey: ["program", programId],
    queryFn: () => api.getProgram(programId as string),
    enabled: programId !== null,
  })
}

export function useProfessor(professorId: string | null) {
  return useQuery({
    queryKey: ["professor", professorId],
    queryFn: () => api.getProfessor(professorId as string),
    enabled: professorId !== null,
  })
}

export function useCvDocuments() {
  return useQuery({
    queryKey: ["documents"],
    queryFn: api.listCvDocuments,
    staleTime: IDLE_STALE_MS,
  })
}

export function useDocumentFolders() {
  return useQuery({
    queryKey: ["document-folders"],
    queryFn: api.listDocumentFolders,
    staleTime: IDLE_STALE_MS,
  })
}

export function useCvDocument(documentId: string | null) {
  return useQuery({
    queryKey: ["document", documentId],
    queryFn: () => api.getCvDocument(documentId as string),
    enabled: documentId !== null,
    // The editor owns the text once loaded (and syncs it): fetched
    // fresh each time a CV opens, never behind the editor's back.
    staleTime: Infinity,
    refetchOnMount: "always",
  })
}

export function useCvVersion(versionId: string | null) {
  return useQuery({
    queryKey: ["document-version", versionId],
    queryFn: () => api.getCvVersion(versionId as string),
    enabled: versionId !== null,
    staleTime: Infinity,
    refetchOnMount: "always",
  })
}

export function useCvSuggestions(documentId: string | null, versionId: string | null) {
  return useQuery({
    queryKey: ["document-suggestions", documentId, versionId],
    queryFn: () => api.listCvSuggestions({ document_id: documentId as string, version_id: versionId }),
    enabled: documentId !== null,
    staleTime: IDLE_STALE_MS,
  })
}

// Board rows are slim; the dialog loads the full task and polls while it is open.
export function useTask(taskId: string | null, pollMs?: number | false) {
  return useQuery({
    queryKey: ["task", taskId],
    queryFn: () => api.getTask(taskId as string),
    enabled: taskId !== null,
    refetchInterval: pollMs,
    staleTime: IDLE_STALE_MS,
  })
}

export type RunEventKind = "task" | "candidate" | "draft" | "done" | "run_status"

/** Reconnect backoff: 1s, 2s, 4s, 8s, capped. */
const RECONNECT_BASE_MS = 1_000
const RECONNECT_MAX_MS = 15_000

// SSE run feed. Subscribe while the page is mounted, not while the run looks
// busy; `done` only means the queue drained. `onError` means SSE is blocked —
// fall back to polling.
export function useRunEvents(
  runId: string,
  opts: {
    enabled: boolean
    onEvent: (kind: RunEventKind, id: string | null) => void
    onTask?: (row: BoardTask) => void
    onTrace?: (delta: TraceDelta) => void
    onError: () => void
  },
) {
  const ref = React.useRef(opts)
  ref.current = opts
  const [attempt, setAttempt] = React.useState(0)
  // Reset backoff only when the subscription target changes, not on reconnect.
  const attemptRef = React.useRef(0)
  const subKeyRef = React.useRef("")

  React.useEffect(() => {
    const subKey = `${runId}|${opts.enabled}`
    if (subKeyRef.current !== subKey) {
      subKeyRef.current = subKey
      attemptRef.current = 0
    }
    if (!opts.enabled || !runId) return
    let closed = false
    let received = false
    let timer: number | undefined
    // EventSource can't set headers, so the token rides ?token=. Always present
    // here: the stream only opens behind RequireAuth.
    const token = getAccessToken()
    const es = new EventSource(
      `${API_BASE}/api/runs/${runId}/events${token ? `?token=${encodeURIComponent(token)}` : ""}`,
    )

    const listeners: Array<readonly [string, EventListener]> = []
    const on = (name: string, fn: (e: MessageEvent) => void) => {
      es.addEventListener(name, fn as EventListener)
      listeners.push([name, fn as EventListener])
    }

    const parse = <T,>(e: MessageEvent): T | null => {
      try {
        return JSON.parse(e.data) as T
      } catch {
        return null // malformed payload: ignore the frame, keep the stream
      }
    }

    for (const kind of ["task", "candidate", "draft"] as const) {
      on(kind, (e) => {
        received = true
        attemptRef.current = 0
        const data = parse<{ id?: string } & Partial<BoardTask>>(e)
        if (!data) return
        if (kind === "task" && data.id && data.status) {
          ref.current.onTask?.(data as BoardTask)
          return
        }
        ref.current.onEvent(kind, data.id ?? null)
      })
    }

    on("trace", (e) => {
      received = true
      attemptRef.current = 0
      const delta = parse<TraceDelta>(e)
      if (delta?.id && Array.isArray(delta.events)) ref.current.onTrace?.(delta)
    })

    on("run_status", (e) => {
      received = true
      const data = parse<{ status?: string }>(e)
      ref.current.onEvent("run_status", data?.status ?? null)
    })

    on("done", () => {
      received = true
      ref.current.onEvent("done", null)
    })

    es.onerror = () => {
      es.close()
      if (closed) return
      // No frames ever arrived, so SSE is blocked; fall back to polling for good.
      if (!received) {
        ref.current.onError()
        return
      }
      const delay = Math.min(
        RECONNECT_BASE_MS * 2 ** attemptRef.current,
        RECONNECT_MAX_MS,
      )
      attemptRef.current += 1
      timer = window.setTimeout(() => {
        if (!closed) setAttempt((a) => a + 1)
      }, delay)
    }

    return () => {
      closed = true
      window.clearTimeout(timer)
      for (const [name, fn] of listeners) es.removeEventListener(name, fn)
      es.close()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [runId, opts.enabled, attempt])
}

const RUN_SCORES_PARAMS = { status: "all", sort: "score", limit: 200, offset: 0 } as const

// Candidates keyed by professor id for score/status; shares the candidates cache.
export function useRunScores(runId: string | null | undefined, pollMs?: number | false) {
  const { data } = useRunCandidates(runId ?? "", RUN_SCORES_PARAMS, pollMs, !!runId)
  return React.useMemo(() => new Map((data?.items ?? []).map((c) => [c.professor_id, c])), [data])
}

export function useSaveDraft() {
  const qc = useQueryClient()
  return React.useCallback(
    async (draft: { id: string; candidate_id: string }, next: { subject: string; body: string }) => {
      await api.updateDraft(draft.id, next)
      await Promise.all([
        qc.invalidateQueries({ queryKey: ["drafts"] }),
        qc.invalidateQueries({ queryKey: ["candidates"] }),
        qc.invalidateQueries({ queryKey: ["candidate", draft.candidate_id] }),
        qc.invalidateQueries({ queryKey: ["candidate-drafts", draft.candidate_id] }),
      ])
    },
    [qc],
  )
}

/** Polled, not streamed, so tabs hold no LISTEN connection; service-worker push messages refresh it at once. */
export function useNotificationInbox(enabled = true) {
  const qc = useQueryClient()
  React.useEffect(() => {
    if (!enabled || !("serviceWorker" in navigator)) return
    const onMessage = (event: MessageEvent) => {
      if ((event.data as { type?: string } | null)?.type === "notification") {
        void qc.invalidateQueries({ queryKey: ["notifications"] })
      }
    }
    navigator.serviceWorker.addEventListener("message", onMessage)
    return () => navigator.serviceWorker.removeEventListener("message", onMessage)
  }, [enabled, qc])
  return useQuery({
    queryKey: ["notifications"],
    queryFn: api.listNotifications,
    refetchInterval: 60_000,
    refetchOnWindowFocus: true,
    retry: retryUnlessAuth,
    enabled,
  })
}
