import * as React from "react"
import { Link, useLocation, useNavigate, useSearchParams } from "react-router-dom"
import { useQueryClient } from "@tanstack/react-query"
import { ChevronRight, Pencil, Trash2 } from "lucide-react"
import * as api from "../../lib/api"
import { useAuth } from "../../lib/auth"
import { toastError } from "../../lib/toast"
import { useSaveDraft } from "../../lib/queries"
import type { Draft } from "../../lib/types"
import { Avatar } from "../ui/avatar"
import { Button } from "../ui/button"
import { ReadingSection, ReadingSurface } from "../ui/reading"
import { ScoreBar } from "../ui/status"
import { Markdown } from "../ui/MarkdownLazy"
import { ConfirmDialog } from "../dialogs/ConfirmDialog"
import { CopyEmailButton, EmailCard, ReviewToggle, type DetailSize } from "../entity/detail"
import { TailorButton } from "../documents/TailorButton"

/** The page adds tailor and review actions; the panel's are in its header menu. */
export function OutboxDetailPanel({
  draft,
  runId,
  size = "panel",
}: {
  draft: Draft
  runId: string
  runTitle?: string
  size?: DetailSize
}) {
  const qc = useQueryClient()
  const navigate = useNavigate()
  const { pathname } = useLocation()
  const [searchParams] = useSearchParams()
  const { user } = useAuth()
  const saveDraft = useSaveDraft()
  const [deleting, setDeleting] = React.useState(false)
  const [editing, setEditing] = React.useState(false)
  const [busy, setBusy] = React.useState(false)
  const page = size === "page"

  async function refreshAll() {
    await Promise.all([
      qc.invalidateQueries({ queryKey: ["drafts", runId] }),
      qc.invalidateQueries({ queryKey: ["candidates", runId] }),
      qc.invalidateQueries({ queryKey: ["candidate", draft.candidate_id] }),
    ])
  }

  async function onDelete() {
    setBusy(true)
    try {
      await api.deleteDraft(draft.id)
      setDeleting(false)
      await refreshAll()
      if (page) {
        navigate("/outbox")
      } else {
        const search = new URLSearchParams(searchParams)
        search.delete("preview")
        navigate({ pathname, search: search.toString() }, { replace: true })
      }
    } catch (e) {
      toastError(e, "Delete failed")
    } finally {
      setBusy(false)
    }
  }

  async function onReview(approved: boolean) {
    setBusy(true)
    try {
      await api.reviewCandidate(draft.candidate_id, approved)
      await refreshAll()
    } catch (e) {
      toastError(e)
    } finally {
      setBusy(false)
    }
  }

  return (
    <ReadingSurface>
      <div className="flex flex-wrap items-center gap-3">
        <Link
          to={`/dossier/${draft.candidate_id}`}
          className="flex w-full justify-between gap-2"
        >
          <div className="group flex min-w-0 items-center gap-2.5 text-sm hover:text-foreground">
            <Avatar name={draft.professor_name} src={draft.professor_photo_url} size="md" className="size-10 text-xs" />
            <span className="min-w-0">
              <span className="block truncate font-semibold group-hover:underline">{draft.professor_name}</span>
              {draft.school_name && (
                <span className="block truncate type-caption">{draft.school_name}</span>
              )}
              {draft.program_name && (
                <span className="block truncate type-caption">{draft.program_name}</span>
              )}
            </span>
          </div>
          <div className="ml-auto flex items-start gap-2">
            <ScoreBar score={draft.similarity_score} />
            <ChevronRight className="size-4 shrink-0 text-muted-foreground" />
          </div>
        </Link>
        <span className="ml-auto flex items-center gap-2">
          {page && (
            <>
              <TailorButton candidateId={draft.candidate_id} />
              <ReviewToggle status={draft.candidate_status} busy={busy} onReview={(ok) => void onReview(ok)} />
            </>
          )}
        </span>
      </div>

      <EmailCard
        from={{ name: user?.display_name || user?.email || "You", email: user?.email, avatarUrl: user?.avatar_url }}
        to={{ name: draft.professor_name, email: draft.professor_email }}
        date={draft.created_at}
        subject={draft.subject}
        body={draft.body}
        editing={editing}
        onEditingChange={setEditing}
        onSave={(next) =>
          saveDraft(draft, next).catch((e) => {
            toastError(e, "Save failed")
            throw e
          })
        }
        footer={
          page && (
            <>
              <Button data-tooltip="Delete this outreach draft" size="sm" variant="ghost" className="mr-auto text-destructive hover:bg-destructive/10 hover:text-destructive" onClick={() => setDeleting(true)}>
                <Trash2 /> Discard
              </Button>
              <Button data-tooltip="Edit the subject and message before reaching out" size="sm" variant="outline" onClick={() => setEditing(true)}>
                <Pencil /> Edit
              </Button>
              <CopyEmailButton subject={draft.subject} body={draft.body} />
            </>
          )
        }
      />

      {draft.rationale && (
        <ReadingSection title="What you need to know">
          <Markdown text={draft.rationale} />
        </ReadingSection>
      )}

      <ConfirmDialog
        open={deleting}
        onOpenChange={setDeleting}
        title="Discard draft?"
        description="The candidate goes back to being scored."
        loading={busy}
        onConfirm={() => void onDelete()}
      />
    </ReadingSurface>
  )
}
