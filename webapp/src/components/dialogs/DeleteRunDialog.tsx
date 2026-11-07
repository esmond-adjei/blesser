import * as React from "react"
import { useQueryClient } from "@tanstack/react-query"
import * as api from "../../lib/api"
import { useDeletePreview } from "../../lib/queries"
import { toastError } from "../../lib/toast"
import { Button } from "../ui/button"
import { Dialog, DialogBody, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "../ui/dialog"
import { Skeleton } from "../ui/feedback"

/** Delete confirmation with per-table counts from `delete-preview`. */
export function DeleteRunDialog({
  runId,
  title,
  open,
  onOpenChange,
  onDeleted,
}: {
  runId: string
  title: string
  open: boolean
  onOpenChange: (open: boolean) => void
  onDeleted: () => void
}) {
  const qc = useQueryClient()
  const { data: preview, isLoading } = useDeletePreview(runId, open)
  const [busy, setBusy] = React.useState(false)
  // Callers pass a changing `key`, so errors never leak between opens.

  async function onConfirm() {
    setBusy(true)
    try {
      await api.deleteRun(runId)
      await qc.invalidateQueries({ queryKey: ["runs"] })
      onOpenChange(false)
      onDeleted()
    } catch (e) {
      toastError(e, "Delete failed")
    } finally {
      setBusy(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent onClose={() => onOpenChange(false)}>
        <DialogHeader>
          <DialogTitle>Delete {title}?</DialogTitle>
          <DialogDescription>This can't be undone.</DialogDescription>
        </DialogHeader>
        <DialogBody>
          {isLoading && <Skeleton className="h-20" />}
          {preview && (
            <dl className="grid grid-cols-2 gap-x-4 gap-y-1 rounded-md bg-muted p-3 text-sm sm:grid-cols-4">
              <PreviewRow label="Schools" value={preview.schools} />
              <PreviewRow label="Programs" value={preview.programs} />
              <PreviewRow label="Professors" value={preview.professors} />
              <PreviewRow label="Papers" value={preview.papers} />
              <PreviewRow label="Candidates" value={preview.candidates} />
              <PreviewRow label="Drafts" value={preview.drafts} />
              <PreviewRow label="Tasks" value={preview.tasks} />
              <PreviewRow label="Tool calls" value={preview.tool_calls} />
            </dl>
          )}
        </DialogBody>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>
            Cancel
          </Button>
          <Button data-tooltip="Delete this run and the related data selected above" variant="destructive" onClick={() => void onConfirm()} disabled={busy}>
            {busy ? "Deleting..." : "Delete run"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function PreviewRow({ label, value }: { label: string; value: number }) {
  return (
    <div className="flex items-baseline justify-between gap-2">
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="tabular-nums font-semibold">{value}</dd>
    </div>
  )
}
