import * as React from "react"
import { useQueryClient } from "@tanstack/react-query"
import { Link, useNavigate, useParams } from "react-router-dom"
import { Ellipsis, FileDown, Loader2, MailPlus, Pencil, RefreshCw, Trash2 } from "lucide-react"
import * as api from "../lib/api"
import { useAuth } from "../lib/auth"
import { draftRequestMessage, hasDraft, isDraftInProgress } from "../lib/drafts"
import { toastError, toastInfo } from "../lib/toast"
import { useExportPdf } from "../lib/exportPdf"
import { applyTraceEvent } from "../lib/live"
import { useCandidate, useCandidateDrafts, useProfessor, useRunEvents, useSaveDraft, useTask } from "../lib/queries"
import type { Task } from "../lib/types"
import { cn } from "../lib/utils"
import { Button } from "../components/ui/button"
import { Menu, MenuItem, MenuSeparator } from "../components/ui/menu"
import { DetailSkeleton } from "../components/ui/feedback"
import { EmptyNote } from "../components/ui/reading"
import { ErrorState } from "../components/feedback/EmptyState"
import { ProfessorEditDialog } from "../components/dialogs/ProspectDialogs"
import { ConfirmDialog } from "../components/dialogs/ConfirmDialog"
import { MatchProfessorDialog } from "../components/dialogs/MatchProfessorDialog"
import { ProfessorDetailView } from "../components/dossier/ProfessorDetailView"
import { CopyEmailButton, EmailCard, ReviewToggle } from "../components/entity/detail"
import { TailorButton } from "../components/documents/TailorButton"
import { AgentTrace } from "../components/cards/AgentTrace"

/** A professor's full dossier page: the shared detail view plus review, drafts and edits. */
export function CandidateDetail() {
  const { candidateId } = useParams<{ candidateId: string }>()
  const navigate = useNavigate()
  const qc = useQueryClient()
  const { data: c, isLoading, isError } = useCandidate(candidateId ?? "")
  // All saved drafts, newest first; the reader can pick between them.
  const { data: allDrafts } = useCandidateDrafts(candidateId ?? "")
  const [selectedDraftId, setSelectedDraftId] = React.useState<string | null>(null)
  // Professor record for contact links, loaded once the candidate reveals its id.
  const { data: prof } = useProfessor(c?.professor_id ?? null)
  const [editingDraft, setEditingDraft] = React.useState(false)
  const [editingProf, setEditingProf] = React.useState(false)
  const [rescoring, setRescoring] = React.useState(false)
  const [confirmDelete, setConfirmDelete] = React.useState(false)
  const [confirmDiscardDraft, setConfirmDiscardDraft] = React.useState(false)
  const [busy, setBusy] = React.useState<string | null>(null)
  const { exporting, exportPdf } = useExportPdf()
  const { user } = useAuth()
  const saveDraft = useSaveDraft()

  const refresh = () =>
    Promise.all([
      qc.invalidateQueries({ queryKey: ["candidate", candidateId] }),
      qc.invalidateQueries({ queryKey: ["candidate-drafts", candidateId] }),
      qc.invalidateQueries({ queryKey: ["candidates"] }),
      qc.invalidateQueries({ queryKey: ["drafts"] }),
    ])
  const draftInProgress = !!c && !hasDraft(c) && isDraftInProgress(c.draft_task_status)
  const draftTask = useLiveDraft(c?.run_id ?? null, c?.draft_task_id ?? null, draftInProgress, refresh)

  if (!candidateId) return <p>Missing route param.</p>
  if (isLoading) return <DetailSkeleton />
  if (isError || !c)
    return (
      <ErrorState
        mascot="not-found"
        title="Candidate not found"
        description="It may have been discarded."
        action={<Link to="/dossier" className="type-meta hover:text-foreground">Go to Matches</Link>}
      />
    )

  // Back-links prefer the candidate's run and fall back to the dossier.
  const rid: string | null = c.run_id ?? null
  const backTo = rid ? `/runs/${rid}` : "/dossier"

  async function run(action: string, fn: () => Promise<unknown>): Promise<boolean> {
    setBusy(action)
    try {
      await fn()
      await refresh()
      return true
    } catch (e) {
      if (action === "draft") toastError(draftRequestMessage(e))
      else toastError(e)
      return false
    } finally {
      setBusy(null)
    }
  }

  const draftReady = hasDraft(c)
  // Prefer the drafts list; fall back to the candidate row's latest-draft
  // fields while it loads. Selection defaults to the newest.
  const drafts = allDrafts ?? []
  const activeDraft =
    drafts.find((d) => d.id === selectedDraftId) ??
    drafts[0] ??
    null
  const draftForEditor = activeDraft
    ? {
        id: activeDraft.id,
        candidate_id: c.id,
        professor_name: c.professor_name,
        candidate_status: c.status,
        similarity_score: c.similarity_score,
        rationale: c.rationale,
        subject: activeDraft.subject,
        body: activeDraft.body,
        created_at: activeDraft.created_at,
      }
    : draftReady && c.draft_subject !== null && c.draft_body !== null
      ? {
          id: c.draft_id as string,
          candidate_id: c.id,
          professor_name: c.professor_name,
          candidate_status: c.status,
          similarity_score: c.similarity_score,
          rationale: c.rationale,
          subject: c.draft_subject,
          body: c.draft_body,
          // The empty string only satisfies the type when the row predates
          // the field.
          created_at: c.draft_created_at ?? "",
        }
      : null

  const draftSection = draftInProgress ? (
    <DraftProgress task={draftTask} />
  ) : !draftReady || !draftForEditor ? (
    <EmptyNote>
      {c.draft_task_status === "failed"
        ? "The last draft didn't finish. Request another from the button at the top."
        : "No draft yet. Request one from the button at the top."}
    </EmptyNote>
  ) : (
    <div className="space-y-3">
      {drafts.length > 1 && (
        <div className="flex flex-wrap gap-1" role="tablist" aria-label="Drafts">
          {drafts.map((d, i) => {
            const active = (activeDraft?.id ?? drafts[0].id) === d.id
            return (
              <button
                key={d.id}
                role="tab"
                aria-selected={active}
                type="button"
                data-tooltip={d.subject}
                onClick={() => setSelectedDraftId(d.id)}
                className={cn(
                  "cursor-pointer rounded-md px-2.5 py-1 text-xs font-medium transition-colors",
                  active ? "bg-accent text-foreground" : "text-muted-foreground hover:bg-muted hover:text-foreground",
                )}
              >
                {i === 0 ? "Latest" : `Draft ${drafts.length - i}`}
              </button>
            )
          })}
        </div>
      )}
      <EmailCard
        from={{ name: user?.display_name || user?.email || "You", email: user?.email, avatarUrl: user?.avatar_url }}
        to={{ name: c.professor_name, email: prof?.email }}
        date={draftForEditor.created_at}
        subject={draftForEditor.subject}
        body={draftForEditor.body}
        editing={editingDraft}
        onEditingChange={setEditingDraft}
        onSave={(next) =>
          saveDraft({ id: draftForEditor.id, candidate_id: c.id }, next).catch((e) => {
            toastError(e, "Save failed")
            throw e
          })
        }
        footer={
          <>
            <Button data-tooltip="Delete this outreach draft" size="sm" variant="ghost" className="mr-auto text-destructive hover:bg-destructive/10 hover:text-destructive" onClick={() => setConfirmDiscardDraft(true)}>
              <Trash2 /> Discard
            </Button>
            <TailorButton candidateId={c.id} />
            <Button data-tooltip="Edit the subject and message before reaching out" size="sm" variant="outline" onClick={() => setEditingDraft(true)}>
              <Pencil /> Edit
            </Button>
            <CopyEmailButton subject={draftForEditor.subject} body={draftForEditor.body} />
          </>
        }
      />
    </div>
  )

  return (
    <div className="mx-auto max-w-4xl">
      <ProfessorDetailView
        size="page"
        candidate={c}
        professor={prof}
        draft={draftSection}
        actions={
          <>
            {!draftReady && !draftInProgress && (
              <Button data-tooltip="Ask the outreach agent to draft an email for this professor" size="sm" disabled={busy !== null} onClick={() => void run("draft", () => api.requestDraft(c.id))}>
                <MailPlus /> {busy === "draft" ? "Queueing…" : "Request draft"}
              </Button>
            )}
            <ReviewToggle
              status={c.status}
              busy={busy !== null}
              onReview={(approved) => void run(approved ? "approve" : "reject", () => api.reviewCandidate(c.id, approved))}
            />
            <Menu
              label="Candidate actions"
              trigger={
                <Button type="button" size="icon" variant="outline" className="size-8" aria-label="Candidate actions">
                  <Ellipsis />
                </Button>
              }
            >
              <MenuItem disabled={exporting} onSelect={() => void exportPdf([c.id])}>
                {exporting ? <Loader2 className="animate-spin" /> : <FileDown />} Export PDF
              </MenuItem>
              <MenuItem disabled={!prof} onSelect={() => setEditingProf(true)}>
                <Pencil /> Edit professor
              </MenuItem>
              <MenuItem onSelect={() => setRescoring(true)}>
                <RefreshCw /> Recalculate fit
              </MenuItem>
              <MenuSeparator />
              <MenuItem destructive onSelect={() => setConfirmDelete(true)}>
                <Trash2 /> Discard candidate
              </MenuItem>
            </Menu>
          </>
        }
      />

      {prof && (
        <ProfessorEditDialog
          key={`prof-${prof.id}-${prof.name}-${prof.email ?? ""}`}
          prof={prof}
          open={editingProf}
          onOpenChange={(o) => { if (!o) setEditingProf(false) }}
        />
      )}

      {rescoring && (
        <MatchProfessorDialog
          professor={{ id: c.professor_id, name: c.professor_name }}
          runId={c.run_id}
          open
          onOpenChange={setRescoring}
        />
      )}

      <ConfirmDialog
        open={confirmDelete}
        onOpenChange={setConfirmDelete}
        title="Discard candidate?"
        description="Removes the candidate and its draft. Their papers stay with the professor."
        loading={busy === "delete"}
        onConfirm={() => {
          setConfirmDelete(false)
          void run("delete", () => api.deleteCandidate(c.id)).then((ok) => {
            if (ok) navigate(backTo)
          })
        }}
      />
      <ConfirmDialog
        open={confirmDiscardDraft}
        onOpenChange={setConfirmDiscardDraft}
        title="Discard draft?"
        description="The candidate goes back to being scored."
        loading={busy === "discard-draft"}
        onConfirm={() => {
          setConfirmDiscardDraft(false)
          if (draftForEditor) {
            setSelectedDraftId(null)
            void run("discard-draft", () => api.deleteDraft(draftForEditor.id))
          } else toastInfo("No draft to discard.")
        }}
      />
    </div>
  )
}

/** Streams the draft task's steps over the run feed (polling if it can't connect); `onSettled` fires once the draft is saved or the task ends. */
function useLiveDraft(runId: string | null, taskId: string | null, active: boolean, onSettled: () => void) {
  const qc = useQueryClient()
  const [sseFailed, setSseFailed] = React.useState(false)
  const settled = React.useRef(onSettled)
  React.useEffect(() => {
    settled.current = onSettled
  })
  const live = active && runId !== null && taskId !== null
  const { data: task } = useTask(live ? taskId : null, live && sseFailed ? 3_000 : false)

  useRunEvents(runId ?? "", {
    enabled: live,
    onTask: (row) => {
      if (row.id === taskId) qc.setQueryData<Task>(["task", row.id], (t) => (t ? { ...t, ...row } : t))
    },
    onTrace: (delta) => {
      if (runId && delta.id === taskId) applyTraceEvent(qc, runId, delta)
    },
    // The draft row lands before the task wraps up its last turn.
    onEvent: (kind) => {
      if (kind === "draft") void settled.current()
    },
    onError: () => setSseFailed(true),
  })

  const status = task?.status
  React.useEffect(() => {
    if (live && status && !isDraftInProgress(status)) void settled.current()
  }, [live, status])

  return live ? task : undefined
}

function DraftProgress({ task }: { task: Task | undefined }) {
  const running = task?.status === "running"
  const steps = task?.log ?? []
  return (
    <div className="space-y-3" aria-live="polite">
      <p className="shimmer-text italic text-muted-foreground">
        {running ? "Writing a draft now…" : "Waiting for the outreach agent to start…"}
      </p>
      {steps.length > 0 && <AgentTrace events={steps} working={running} />}
    </div>
  )
}
