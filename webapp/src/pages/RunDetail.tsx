import * as React from "react"
import { useQueryClient } from "@tanstack/react-query"
import { Link, useNavigate, useParams } from "react-router-dom"
import {
  Ban,
  Copy,
  EllipsisVertical,
  Pause,
  Pencil,
  Play,
  RefreshCw,
  SquareKanban,
  ChartColumn,
  Trash2,
} from "lucide-react"
import * as api from "../lib/api"
import { toastError, toastInfo } from "../lib/toast"
import { applyTaskEvent, applyTraceEvent, flushLiveInvalidations } from "../lib/live"
import { formatAgo, formatDate, formatDegrees, formatRelativeDate, runTitle } from "../lib/format"
import { useNow } from "../lib/useNow"
import {
  useRun,
  useRunBoard,
  useRunEvents,
  type RunEventKind,
} from "../lib/queries"
import { Button } from "../components/ui/button"
import { Menu, MenuItem, MenuSeparator } from "../components/ui/menu"
import { Alert, AlertDescription, AlertTitle, DetailSkeleton } from "../components/ui/feedback"
import { ErrorState } from "../components/feedback/EmptyState"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "../components/ui/tabs"
import { DeleteRunDialog } from "../components/dialogs/DeleteRunDialog"
import { Dialog, DialogBody, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "../components/ui/dialog"
import { EditRunDialog } from "../components/dialogs/EditRunDialog"
import { RunAllowance } from "../components/run/RunAllowance"
import { RunModelDropup } from "../components/run/ModelPicker"
import { PushPrompt } from "../components/run/PushPrompt"
import { useDetailPanel } from "../components/layout/DetailPanel"
import { HealthBanner } from "../components/layout/AppShell"
import { usePreviewParam, useUrlParam } from "../lib/urlParams"
import { useRunPreviewItem } from "../lib/queries"
import { DossierDetailPanel } from "../components/dossier/DossierDetailPanel"
import { ProfessorDetailPanel } from "../components/dossier/ProfessorDetailPanel"
import { OutboxDetailPanel } from "../components/outbox/OutboxDetailPanel"
import { CandidatePreviewActions, DraftPreviewActions } from "../components/layout/PreviewActions"
import { SavedProgramPanel } from "../components/run/SavedProgramPanel"
import { TaskBoard } from "../components/lists/TaskBoard"
import { RunSidebar } from "../components/run/RunSidebar"
import { TasksTab } from "../components/run/TasksTab"
import { AgentControls, AgentStatusNote } from "../components/run/AgentControls"
import { TASK_TYPE_TAB_LABELS, type TaskTypeFilter } from "../components/run/taskTypes"
import { RunStatusBadge } from "../components/ui/status"
import { ConfirmDialog } from "../components/dialogs/ConfirmDialog"
import { cn } from "../lib/utils"
import { runActivity, stallReason } from "../lib/runActivity"
import { Markdown } from "../components/ui/MarkdownLazy"
import { StatsRefreshButton } from "../components/run/StatsRefreshButton"
import { artifactPreview } from "../components/gradis/GradisArtifactPreview"

const RESEARCH_TABS: TaskTypeFilter[] = [
  "discover_programs",
  "research_professor",
  "research_one_professor",
  "draft_email",
]
/** Opportunity scans (api/opportunities/scans.py) run one agent type only. */
const SCAN_TABS: TaskTypeFilter[] = ["discover_opportunities"]

function isScanRun(run: { field: string } | undefined): boolean {
  return !!run?.field.startsWith("Opportunities:")
}

// Charts load with the Stats panel, not the run page.
const UsageTab = React.lazy(() => import("../components/run/UsageTab").then((m) => ({ default: m.UsageTab })))

export function RunDetail() {
  const { runId } = useParams<{ runId: string }>()
  const navigate = useNavigate()
  const qc = useQueryClient()
  // Workspace filters live in the URL (?tab=, ?status=) so they are shareable.
  const [tabParam, setTabParam] = useUrlParam("tab", "")
  const [tasksStatus, setTasksStatus] = useUrlParam("status", "all")
  // ?board=1 opens the task board, so the header's queue badge can link to it.
  const [boardParam, setBoardParam] = useUrlParam("board", "")
  const boardOpen = boardParam === "1"
  const setBoardOpen = React.useCallback((open: boolean) => setBoardParam(open ? "1" : ""), [setBoardParam])
  const [confirmDelete, setConfirmDelete] = React.useState(false)
  const [outlineSlot, setOutlineSlot] = React.useState<HTMLDivElement | null>(null)
  const [editOpen, setEditOpen] = React.useState(false)
  const [confirmCancel, setConfirmCancel] = React.useState(false)
  const [busy, setBusy] = React.useState<string | null>(null)
  const [sseFailed, setSseFailed] = React.useState(false)
  const [interestExpanded, setInterestExpanded] = React.useState(false)

  const { data: run, isLoading: runLoading, isError: runError } = useRun(runId ?? "")
  // Preselected-list runs skip discovery; open on the faculty agents instead
  // of an empty "School Agents (0)" tab.
  const scan = isScanRun(run)
  const TASK_TABS = scan ? SCAN_TABS : RESEARCH_TABS
  const defaultTab = run?.region === "(preselected list)" ? "research_professor" : TASK_TABS[0]
  const tab = (TASK_TABS as string[]).includes(tabParam) ? tabParam : defaultTab
  const rid = runId ?? ""

  // Fall back to polling only when SSE never connected and the run is still
  // running. Derived from run status, not the board cache, to avoid a feedback loop.
  const fb = sseFailed && run?.status === "running" ? 5_000 : false

  // Live feed for as long as the page is open. Task rows patch caches in place;
  // candidate/draft frames carry only an id, so they invalidate (batched in lib/live).
  useRunEvents(rid, {
    enabled: !!run,
    onTask: (row) => applyTaskEvent(qc, rid, row),
    onTrace: (delta) => applyTraceEvent(qc, rid, delta),
    onEvent: (kind: RunEventKind, id: string | null) => {
      if (kind === "candidate") {
        // Professor saves land 1:1 with candidates, so school counts change too.
        void qc.invalidateQueries({ queryKey: ["candidates", rid] })
        void qc.invalidateQueries({ queryKey: ["schools", rid] })
        void qc.invalidateQueries({ queryKey: ["account-schools"] })
        if (id) void qc.invalidateQueries({ queryKey: ["candidate", id] })
      } else if (kind === "draft") {
        void qc.invalidateQueries({ queryKey: ["drafts", rid] })
        void qc.invalidateQueries({ queryKey: ["candidates", rid] })
      } else if (kind === "run_status") {
        // Header badge and sidebar both read run status; neither follows from task frames.
        void qc.invalidateQueries({ queryKey: ["run", rid] })
        void qc.invalidateQueries({ queryKey: ["runs"] })
      } else if (kind === "done") {
        // Queue drained. Reconcile what a conclusion changes; the stream stays open.
        void qc.invalidateQueries({ queryKey: ["run", rid] })
        void qc.invalidateQueries({ queryKey: ["board", rid] })
        void qc.invalidateQueries({ queryKey: ["tasks", rid] })
        void qc.invalidateQueries({ queryKey: ["candidates", rid] })
        void qc.invalidateQueries({ queryKey: ["usage", rid] })
      }
    },
    onError: () => setSseFailed(true),
  })

  // Flush batched invalidations on unmount; a mid-burst navigation would drop them.
  React.useEffect(() => () => flushLiveInvalidations(qc), [qc])

  // Companion rail: Resources by default, preview when ?preview= is set.
  // Published from an effect, not the click handler, so the panel sees current
  // state and clears on unmount; a stale element would keep querying.
  const { setPanel, clearPanel, railVisible, setRailVisible } = useDetailPanel()
  const [rail, setRail] = React.useState<"resources" | "stats" | null>(null)
  const railTitle = run ? runTitle(run) : "Run"
  const { previewId, closePreview } = usePreviewParam()
  const preview = useRunPreviewItem(rid, previewId)

  // setPanel stores an element, so republishing on every refetch would remount
  // the rail and wipe local state. Publish only when the selection changes.
  const publishedRef = React.useRef<string | null>(null)

  React.useEffect(() => {
    if (!rid) return
    if (previewId) {
      // Keep the current panel until the record resolves.
      if (preview.isLoading || !preview.item) return
      const key = `preview:${rid}:${previewId}`
      if (publishedRef.current === key) return
      const item = preview.item
      const onClose = closePreview
      if (item.kind === "candidate") {
        setPanel(
          <DossierDetailPanel key={item.candidate.id} candidateId={item.candidate.id} />,
          {
            onClose,
            title: item.candidate.professor_name,
            ref: { kind: "candidate", id: item.candidate.id },
            actions: <CandidatePreviewActions candidateId={item.candidate.id} />,
          },
        )
      } else if (item.kind === "draft") {
        setPanel(
          <OutboxDetailPanel key={item.draft.id} draft={item.draft} runId={rid} runTitle={railTitle} />,
          {
            onClose,
            title: item.draft.subject || "Draft",
            ref: { kind: "draft", id: item.draft.id },
            actions: <DraftPreviewActions draftId={item.draft.id} runId={rid} />,
          },
        )
      } else if (item.kind === "application") {
        const ref = { kind: "application" as const, id: item.applicationId }
        const application = artifactPreview(ref)
        if (!application) return
        setPanel(application.node, { onClose, title: item.name, ref, actions: application.actions })
      } else if (item.kind === "professor") {
        setPanel(
          <ProfessorDetailPanel key={item.professorId} professorId={item.professorId} />,
          { onClose, title: item.name, ref: { kind: "professor", id: item.professorId } },
        )
      } else {
        setPanel(
          <SavedProgramPanel key={item.programId} programId={item.programId} runId={rid} />,
          { onClose, title: item.name, ref: { kind: "program", id: item.programId, runId: rid } },
        )
      }
      publishedRef.current = key
      return
    }
    if (!rail) {
      if (publishedRef.current !== null) {
        clearPanel()
        publishedRef.current = null
      }
      return
    }
    const key = `${rail}:${rid}:${fb}:${railTitle}`
    if (publishedRef.current === key) return
    setPanel(rail === "stats" ? <React.Suspense fallback={null}><UsageTab runId={rid} /></React.Suspense> : <RunSidebar runId={rid} fallbackPoll={fb} />, {
      title: rail === "stats" ? "Stats" : railTitle,
      onClose: () => setRail(null),
      actions: rail === "stats" ? <StatsRefreshButton runId={rid} /> : undefined,
    })
    publishedRef.current = key
  }, [rid, previewId, preview, rail, fb, railTitle, setPanel, clearPanel, closePreview])

  function toggleRail(view: "resources" | "stats") {
    if (previewId) {
      closePreview()
      setRail(view)
    } else if (rail === view && !railVisible) {
      setRailVisible(true)
    } else {
      setRail(rail === view ? null : view)
    }
  }

  React.useEffect(() => () => clearPanel(), [clearPanel])

  const { data: board } = useRunBoard(rid, fb)
  const typeCounts = React.useMemo(() => {
    const counts: Record<string, number> = {}
    if (!board) return counts
    for (const items of Object.values(board)) {
      for (const t of items) counts[t.task_type] = (counts[t.task_type] ?? 0) + 1
    }
    return counts
  }, [board])

  const activeByType = React.useMemo(() => {
    const counts: Record<string, number> = {}
    if (!board) return counts
    for (const status of ["pending", "running"] as const) {
      for (const t of board[status] ?? []) counts[t.task_type] = (counts[t.task_type] ?? 0) + 1
    }
    return counts
  }, [board])

  // Not-yet-started tasks per type: what cancelling an agent stops.
  const queuedByType = React.useMemo(() => {
    const counts: Record<string, number> = {}
    if (!board) return counts
    for (const status of ["pending", "paused", "deferred"] as const) {
      for (const t of board[status] ?? []) counts[t.task_type] = (counts[t.task_type] ?? 0) + 1
    }
    return counts
  }, [board])

  const taskCounts: Record<string, number> = React.useMemo(() => {
    if (!board) return run?.tasks ?? {}
    const counts: Record<string, number> = {}
    for (const [status, items] of Object.entries(board)) counts[status] = items.length
    return counts
  }, [board, run])

  // Derived from open tasks, not the run row: halted runs keep queued tasks,
  // and a run whose tasks all errored stays "running" with nothing working.
  const activity = runActivity(run?.status, taskCounts)
  const liveActive = activity === "working"
  const now = useNow(!!run && !run.finished_at, 30_000)

  if (!runId) return <p>Missing run id.</p>
  if (runLoading) return <DetailSkeleton />
  if (runError || !run)
    return (
      <ErrorState
        mascot="not-found"
        title="Run not found"
        description="It may have been deleted."
      />
    )

  async function changeModel(model: string) {
    const previous = qc.getQueryData(["run", rid])
    qc.setQueryData(["run", rid], (r: typeof run) => (r ? { ...r, llm_provider: model } : r))
    try {
      await api.updateRun(rid, { llm_provider: model })
      void qc.invalidateQueries({ queryKey: ["runs"] })
    } catch (e) {
      qc.setQueryData(["run", rid], previous)
      toastError(e, "Couldn't change the model")
    }
  }

  async function control(action: "pause" | "resume" | "cancel" | "retry", fn: () => Promise<unknown>) {
    setBusy(action)
    try {
      const res = await fn()
      if (action === "retry") {
        const n = (res as { retried: number }).retried
        toastInfo(n === 0 ? "No failed tasks to retry." : `Requeued ${n} failed task${n === 1 ? "" : "s"}.`)
      }
      await Promise.all([
        qc.invalidateQueries({ queryKey: ["run", rid] }),
        qc.invalidateQueries({ queryKey: ["runs"] }),
        qc.invalidateQueries({ queryKey: ["tasks", rid] }),
        qc.invalidateQueries({ queryKey: ["board", rid] }),
      ])
    } catch (e) {
      toastError(e)
    } finally {
      setBusy(null)
      setConfirmCancel(false)
    }
  }

  const title = runTitle(run)
  const failedCount = taskCounts.error ?? 0
  // Allowance refusal parks tasks with this note and pauses the run.
  const allowanceNote =
    run.status === "paused"
      ? board?.paused?.find((t) => t.error?.startsWith(ALLOWANCE_PAUSE_PREFIX))?.error?.slice(ALLOWANCE_PAUSE_PREFIX.length)
      : undefined

  const gradType = formatDegrees(run.degree_level)

  return (
    <>
      <Tabs value={tab} onValueChange={setTabParam} className="space-y-5 max-w-4xl mx-auto px-4 lg:px-8">
        {/* No live worker: suppress the shimmer so it doesn't imply progress. */}
        <HealthBanner />
        <PushPrompt running={run.status === "running"} />
        {allowanceNote && (
          <Alert>
            <AlertTitle>Paused: the model allowance ran out</AlertTitle>
            <AlertDescription>
              {allowanceNote} Choose Resume in the run menu when you can continue; the run picks up where it
              stopped.
            </AlertDescription>
          </Alert>
        )}
        {activity === "stalled" && (
          <Alert>
            <AlertTitle>This run has stalled</AlertTitle>
            <AlertDescription>
              <p>{stallReason(failedCount, (board?.error ?? []).map((t) => t.error))}</p>
              <Button data-tooltip="Queue another attempt for the failed tasks in this run"
                size="sm"
                variant="outline"
                className="mt-2"
                disabled={busy !== null}
                onClick={() => void control("retry", () => api.retryFailed(rid))}
              >
                <RefreshCw /> {busy === "retry" ? "Retrying..." : `Retry ${failedCount} failed`}
              </Button>
            </AlertDescription>
          </Alert>
        )}
        <div className="sticky top-0 z-20 -mx-4 mb-6 flex flex-col items-start gap-3 bg-inherit px-4 pt-2 pb-3 backdrop-blur-[24px] backdrop-saturate-[1.8] lg:-mx-8 lg:px-8">
          <div className="min-w-0 flex-1 space-y-2 w-full">
            <div className="flex items-center gap-x-3 gap-y-2 type-caption">
              <RunStatusBadge status={run.status} live={liveActive} />
              <div className="flex shrink-0 items-center gap-1.5 ml-auto px-2">
                {scan ? null : (
                  <Button
                    size="sm"
                    variant="outline"
                    aria-pressed={rail === "resources" && !previewId && railVisible}
                    onClick={() => toggleRail("resources")}
                  >
                    <RunAllowance runId={rid} live={run.status === "running"} />
                  </Button>
                )}
                <Button data-tooltip="Open the task board for this research run" size="sm" variant="outline" onClick={() => setBoardOpen(true)}>
                  <SquareKanban /> Tasks
                </Button>
                <Button
                  data-tooltip="Tokens, time and outcomes for this run"
                  size="sm"
                  variant="outline"
                  aria-pressed={rail === "stats" && !previewId && railVisible}
                  onClick={() => toggleRail("stats")}
                >
                  <ChartColumn /> Stats
                </Button>

                <Menu
                  label="Run actions"
                  trigger={
                    <Button size="icon" variant="outline" aria-label="Run actions" className="size-7 rounded-sm">
                      <EllipsisVertical />
                    </Button>
                  }
                >
                  {run.status === "running" && (
                    <MenuItem disabled={busy !== null} onSelect={() => void control("pause", () => api.pauseRun(rid))}>
                      <Pause /> {busy === "pause" ? "Pausing..." : "Pause"}
                    </MenuItem>
                  )}
                  {(run.status === "paused" || run.status === "cancelled") && (
                    <MenuItem disabled={busy !== null} onSelect={() => void control("resume", () => api.resumeRun(rid))}>
                      <Play /> {busy === "resume" ? "Resuming..." : "Resume"}
                    </MenuItem>
                  )}
                  {(run.status === "running" || run.status === "paused") && (
                    <MenuItem onSelect={() => setConfirmCancel(true)}>
                      <Ban /> Cancel
                    </MenuItem>
                  )}
                  {failedCount > 0 && (
                    <MenuItem disabled={busy !== null} onSelect={() => void control("retry", () => api.retryFailed(rid))}>
                      <RefreshCw /> {busy === "retry" ? "Retrying..." : `Retry ${failedCount} failed`}
                    </MenuItem>
                  )}

                  {(run.status === "running" || run.status === "paused" || run.status === "cancelled" || failedCount > 0) && <MenuSeparator />}

                  {scan ? null : (
                    <>
                      <MenuItem onSelect={() => setEditOpen(true)}>
                        <Pencil /> Edit run
                      </MenuItem>
                      <MenuItem onSelect={() => navigate(`/new?from=${rid}`)}>
                        <Copy /> Run again with changes
                      </MenuItem>
                    </>
                  )}

                  <MenuItem destructive onSelect={() => setConfirmDelete(true)}>
                    <Trash2 /> Delete
                  </MenuItem>
                </Menu>
              </div>
            </div>
            <h1 className="type-page-title truncate">
              {scan ? `Opportunity scan: ${run.field.slice("Opportunities:".length).trim()} in ${run.region}` : `${gradType} in ${title}`}
            </h1>
            {scan && run.interest_statement.trim() === "-" ? null : <button
              type="button"
              aria-expanded={interestExpanded}
              onClick={() => setInterestExpanded((expanded) => !expanded)}
              className={cn(
                "block w-full text-sm text-left whitespace-pre-wrap",
                !interestExpanded && "line-clamp-2",
              )}
            >
              <Markdown text={run.interest_statement} />
            </button>}
            {scan ? (
              <p className="type-meta">
                Agents save only what they verify on each opportunity's own page.{" "}
                <Link to="/opportunities?sort=new" className="text-tint hover:underline">See the newest opportunities</Link>
              </p>
            ) : null}

            <div className="flex items-center gap-x-3 gap-y-2 type-caption">
              <span data-tooltip={formatDate(run.created_at)}>Started {formatRelativeDate(run.created_at, now)}</span>
              {run.updated_at && (
                <span data-tooltip={formatDate(run.updated_at)}>Last updated {formatAgo(run.updated_at, now)}</span>
              )}

              <div className="flex shrink-0 items-center gap-1.5 ml-auto px-2">
                <RunModelDropup value={run.llm_provider ?? "default"} onChange={(model) => void changeModel(model)} />
              </div>
            </div>
          </div>

          <TabsList className="nice-scroll w-full overflow-x-auto">
            {TASK_TABS.map((t) => (
              <div key={t} className="group relative flex-1 shrink-0">
                <TabsTrigger value={t} className="relative h-full w-full whitespace-nowrap">
                  {TASK_TYPE_TAB_LABELS[t]} ({(typeCounts[t] ?? 0)})
                  {(activeByType[t] ?? 0) > 0 && (
                    <span
                      data-tooltip={`${activeByType[t]} active`}
                      aria-label={`${activeByType[t]} active tasks`}
                      className="absolute top-0 right-0 inline-flex items-center justify-center rounded-full bg-tint size-4 p-1 text-xs font-semibold text-on-tint transition-opacity group-hover:opacity-0"
                    >
                      {activeByType[t] < 10 ? activeByType[t] : "9+"}
                    </span>
                  )}
                </TabsTrigger>
                {/* Sibling of the trigger, so opening it never switches tabs. */}
                <AgentControls
                  runId={rid}
                  taskType={t}
                  state={run.agent_states?.[t]}
                  queued={queuedByType[t] ?? 0}
                />
              </div>
            ))}
          </TabsList>
          {/* The folded tasks outline, kept in reach as the cards scroll. */}
          <div ref={setOutlineSlot} className="w-full empty:hidden" />
        </div>

        {TASK_TABS.map((t) => (
          <TabsContent key={t} value={t} className="space-y-3 px-2">
            <AgentStatusNote taskType={t} state={run.agent_states?.[t]} />
            <TasksTab
              runId={rid}
              fallbackPoll={fb}
              taskType={t}
              status={tasksStatus}
              outlineSlot={outlineSlot}
            />
          </TabsContent>
        ))}
      </Tabs>

      <Dialog open={boardOpen} onOpenChange={setBoardOpen}>
        <DialogContent onClose={() => setBoardOpen(false)} className="max-w-6xl">
          <DialogHeader>
            <DialogTitle>Task board</DialogTitle>
            <DialogDescription>
              Kanban across every agent task type. Select a card for the full trace.
            </DialogDescription>
          </DialogHeader>
          <DialogBody>
            <TaskBoard
              runId={rid}
              counts={taskCounts}
              fallbackPoll={fb}
              onViewAll={(s) => { setTasksStatus(s); setTabParam(TASK_TABS[0]); setBoardOpen(false) }}
            />
          </DialogBody>
        </DialogContent>
      </Dialog>

      <EditRunDialog key={`${rid}-${editOpen}`} runId={rid} open={editOpen} onOpenChange={setEditOpen} />
      <DeleteRunDialog
        key={`delete-${rid}-${confirmDelete}`}
        runId={rid}
        title={title}
        open={confirmDelete}
        onOpenChange={setConfirmDelete}
        onDeleted={() => navigate("/new")}
      />
      <ConfirmDialog
        open={confirmCancel}
        onOpenChange={setConfirmCancel}
        title="Cancel this run?"
        description="Stops any new research and keeps everything you've reviewed. Resume whenever you're ready."
        confirmLabel="Cancel run"
        loading={busy === "cancel"}
        onConfirm={() => void control("cancel", () => api.cancelRun(rid))}
      />
    </>
  )
}

const ALLOWANCE_PAUSE_PREFIX = "Paused: "

