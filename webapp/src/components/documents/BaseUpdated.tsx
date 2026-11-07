import * as React from "react"
import { useQuery } from "@tanstack/react-query"
import { GitCompareArrows } from "lucide-react"
import * as api from "../../lib/api"
import type { BaseChange } from "../../lib/types"
import { cn } from "../../lib/utils"
import { Button } from "../ui/button"
import { Dialog, DialogBody, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "../ui/dialog"
import { SkeletonStack } from "../ui/feedback"

function Lines({ text, tone }: { text: string; tone: "old" | "new" }) {
  const lines = text.replace(/\n$/, "").split("\n")
  return (
    <div
      className={cn(
        "whitespace-pre-wrap px-2 py-1 text-compact leading-snug",
        tone === "old" ? "bg-critical-soft text-label-secondary line-through decoration-critical" : "bg-positive-soft",
      )}
    >
      {lines.map((l, i) => (
        <div key={i}>
          <span aria-hidden className="mr-2 select-none opacity-50">
            {tone === "old" ? "−" : "+"}
          </span>
          {l || " "}
        </div>
      ))}
    </div>
  )
}

function BaseChangeView({ change }: { change: BaseChange }) {
  return (
    <li className="overflow-hidden rounded-md border border-border">
      {change.before && <Lines text={change.before} tone="old" />}
      {change.after && <Lines text={change.after} tone="new" />}
      {!change.applicable && (
        <p className="border-t border-border px-2 py-1 text-xs text-muted-foreground">You changed this part in the variant; copy it by hand if you want it.</p>
      )}
    </li>
  )
}

/** A variant is a fork, so the base's later edits don't reach it on their own.
 * Nothing here writes the variant's text. */
export function BaseUpdatedBar({
  versionId,
  noun,
  busy,
  onSuggest,
  onKeep,
}: {
  versionId: string
  noun: string
  busy: boolean
  onSuggest: () => void
  onKeep: () => void
}) {
  const [open, setOpen] = React.useState(false)
  const changes = useQuery({
    queryKey: ["base-changes", versionId],
    queryFn: () => api.getBaseChanges(versionId),
    enabled: open,
    staleTime: 0,
  })
  const list = changes.data?.changes ?? []
  const ready = list.filter((c) => c.applicable).length
  return (
    <>
      <div
        role="status"
        className="flex flex-none flex-wrap items-center gap-x-3 gap-y-1.5 border-b border-separator bg-tint-soft px-3 py-2 text-sm sm:px-4"
      >
        <GitCompareArrows className="size-4 shrink-0 text-tint" aria-hidden />
        <span className="min-w-[14rem] flex-1">
          <span className="font-medium">Base updated since fork.</span>{" "}
          <span className="hidden text-muted-foreground sm:inline">The base {noun} changed after this variant was made.</span>
        </span>
        <span className="flex shrink-0 gap-1.5">
          <Button size="sm" variant="ghost" className="h-8" onClick={() => setOpen(true)}>
            See changes
          </Button>
          <Button size="sm" variant="outline" className="h-8" disabled={busy} onClick={onSuggest}>
            Suggest them
          </Button>
          <Button size="sm" variant="ghost" className="h-8 text-muted-foreground" disabled={busy} onClick={onKeep}>
            Keep as is
          </Button>
        </span>
      </div>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent onClose={() => setOpen(false)} className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>Changes to the base</DialogTitle>
            <DialogDescription>Since this variant was made. Your variant stays as it is unless you apply them.</DialogDescription>
          </DialogHeader>
          <DialogBody>
            {changes.isLoading ? (
              <SkeletonStack className="space-y-2" blocks={["h-12", "h-12"]} />
            ) : list.length === 0 ? (
              <p className="text-sm text-muted-foreground">No changes to show.</p>
            ) : (
              <ul aria-label="Changes to the base" className="space-y-2">
                {list.map((c, i) => (
                  <BaseChangeView key={i} change={c} />
                ))}
              </ul>
            )}
          </DialogBody>
          <DialogFooter>
            <Button variant="outline" onClick={() => setOpen(false)}>
              Close
            </Button>
            <Button
              disabled={busy || ready === 0}
              onClick={() => {
                setOpen(false)
                onSuggest()
              }}
            >
              {ready > 0 ? `Suggest ${ready === 1 ? "it" : `these ${ready}`}` : "Nothing to suggest"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  )
}
