import * as React from "react"
import { useQueryClient } from "@tanstack/react-query"
import { useNavigate } from "react-router-dom"
import { ArrowRight, FileDown, MailPlus, RefreshCw, ThumbsDown, ThumbsUp, Trash2 } from "lucide-react"
import * as api from "../../lib/api"
import { hasDraft } from "../../lib/drafts"
import { useExportPdf } from "../../lib/exportPdf"
import { useRowActions } from "../../lib/useRowActions"
import type { Candidate } from "../../lib/types"
import { MenuItem, MenuSeparator } from "../ui/menu"
import { RowMenu, type RowMenuVariant } from "../ui/row-menu"
import { ConfirmDialog } from "../dialogs/ConfirmDialog"
import { MatchProfessorDialog } from "../dialogs/MatchProfessorDialog"

/** Hover-only dossier row menu: the review actions without opening the rail. */
export function CandidateRowMenu({
  candidate,
  runId,
  isActive,
  variant = "row",
  className,
}: {
  candidate: Candidate
  runId: string
  isActive: boolean
  variant?: RowMenuVariant
  className?: string
}) {
  const qc = useQueryClient()
  const navigate = useNavigate()
  const [confirmDelete, setConfirmDelete] = React.useState(false)
  const [rescoring, setRescoring] = React.useState(false)
  const { exporting, exportPdf } = useExportPdf()
  const { busy, run, remove } = useRowActions(
    () =>
      Promise.all([
        qc.invalidateQueries({ queryKey: ["candidates", runId] }),
        qc.invalidateQueries({ queryKey: ["drafts", runId] }),
        qc.invalidateQueries({ queryKey: ["candidate", candidate.id] }),
      ]),
    isActive,
  )

  const draftReady = hasDraft(candidate)

  return (
    <>
      <RowMenu variant={variant} label={`Manage ${candidate.professor_name}`} className={className}>
        {/* In the rail header, "Open as page" already goes there. */}
        {variant === "row" && (
          <MenuItem onSelect={() => navigate(`/dossier/${candidate.id}`)}>
            <ArrowRight /> Open review
          </MenuItem>
        )}
        {!draftReady && candidate.status === "scored" && (
          <MenuItem disabled={busy !== null} onSelect={() => void run("draft", () => api.requestDraft(candidate.id))}>
            <MailPlus /> {busy === "draft" ? "Queueing..." : "Request draft"}
          </MenuItem>
        )}
        {candidate.status !== "approved" && (
          <MenuItem disabled={busy !== null} onSelect={() => void run("approve", () => api.reviewCandidate(candidate.id, true))}>
            <ThumbsUp /> Approve
          </MenuItem>
        )}
        {candidate.status !== "rejected" && (
          <MenuItem disabled={busy !== null} onSelect={() => void run("reject", () => api.reviewCandidate(candidate.id, false))}>
            <ThumbsDown /> Reject
          </MenuItem>
        )}
        <MenuItem onSelect={() => setRescoring(true)}>
          <RefreshCw /> Recalculate fit
        </MenuItem>
        <MenuItem disabled={exporting} onSelect={() => void exportPdf([candidate.id])}>
          <FileDown /> {exporting ? "Exporting..." : "Export PDF"}
        </MenuItem>
        <MenuSeparator />
        <MenuItem destructive onSelect={() => setConfirmDelete(true)}>
          <Trash2 /> Discard
        </MenuItem>
      </RowMenu>
      {rescoring && (
        <MatchProfessorDialog
          professor={{ id: candidate.professor_id, name: candidate.professor_name }}
          runId={candidate.run_id}
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
          void remove(() => api.deleteCandidate(candidate.id))
        }}
      />
    </>
  )
}
