import * as React from "react"
import { useQueryClient } from "@tanstack/react-query"
import { useNavigate } from "react-router-dom"
import { ArrowRight, Copy, FileText, ThumbsDown, ThumbsUp, Trash2 } from "lucide-react"
import * as api from "../../lib/api"
import { draftEmailText } from "../../lib/drafts"
import { useTailorCv } from "../../lib/tailorCv"
import { useRowActions } from "../../lib/useRowActions"
import type { Draft } from "../../lib/types"
import { MenuItem, MenuSeparator } from "../ui/menu"
import { RowMenu, type RowMenuVariant } from "../ui/row-menu"
import { ConfirmDialog } from "../dialogs/ConfirmDialog"

/** Also the rail's header menu. Tailoring toasts its failures because it navigates away. */
export function DraftRowMenu({
  draft,
  runId,
  isActive,
  variant = "row",
  className,
}: {
  draft: Draft
  runId: string
  isActive: boolean
  variant?: RowMenuVariant
  /** Row overlay position; see ROW_MENU_POSITION. */
  className?: string
}) {
  const qc = useQueryClient()
  const navigate = useNavigate()
  const [confirmDelete, setConfirmDelete] = React.useState(false)
  const [copied, setCopied] = React.useState(false)
  const { tailoring, tailorCv } = useTailorCv(draft.candidate_id)
  const { busy, run, remove } = useRowActions(
    () =>
      Promise.all([
        qc.invalidateQueries({ queryKey: ["drafts", runId] }),
        qc.invalidateQueries({ queryKey: ["candidates", runId] }),
        qc.invalidateQueries({ queryKey: ["candidate", draft.candidate_id] }),
      ]),
    isActive,
  )

  async function onCopy() {
    await navigator.clipboard.writeText(draftEmailText(draft))
    setCopied(true)
    setTimeout(() => setCopied(false), 1500)
  }

  return (
    <>
      <RowMenu variant={variant} label={`Manage draft for ${draft.professor_name}`} className={className}>
        <MenuItem onSelect={() => navigate(`/dossier/${draft.candidate_id}`)}>
          <ArrowRight /> Open review
        </MenuItem>
        <MenuItem disabled={tailoring} onSelect={() => void tailorCv()}>
          <FileText /> {tailoring ? "Opening…" : "Tailor my CV"}
        </MenuItem>
        <MenuItem onSelect={() => void onCopy()}>
          <Copy /> {copied ? "Copied" : "Copy email"}
        </MenuItem>
        {draft.candidate_status !== "approved" && (
          <MenuItem disabled={busy !== null} onSelect={() => void run("approve", () => api.reviewCandidate(draft.candidate_id, true))}>
            <ThumbsUp /> Approve
          </MenuItem>
        )}
        {draft.candidate_status !== "rejected" && (
          <MenuItem disabled={busy !== null} onSelect={() => void run("reject", () => api.reviewCandidate(draft.candidate_id, false))}>
            <ThumbsDown /> Reject
          </MenuItem>
        )}
        <MenuSeparator />
        <MenuItem destructive onSelect={() => setConfirmDelete(true)}>
          <Trash2 /> Discard
        </MenuItem>
      </RowMenu>
      <ConfirmDialog
        open={confirmDelete}
        onOpenChange={setConfirmDelete}
        title="Discard draft?"
        description="The candidate goes back to being scored."
        loading={busy === "delete"}
        onConfirm={() => {
          setConfirmDelete(false)
          void remove(() => api.deleteDraft(draft.id))
        }}
      />
    </>
  )
}
