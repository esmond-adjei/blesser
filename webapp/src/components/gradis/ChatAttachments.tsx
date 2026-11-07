import * as React from "react"
import { FileText, Loader2, Paperclip, X } from "lucide-react"
import type { AttachmentSummary } from "../../lib/gradis"
import { cn } from "../../lib/utils"
import { ACCEPT, MAX_ATTACHMENTS } from "./useChatAttach"

/** In the composer each chip has a remove button. */
export function AttachmentChips({
  items,
  onRemove,
  disabled,
  className,
}: {
  items: AttachmentSummary[]
  onRemove?: (index: number) => void
  disabled?: boolean
  className?: string
}) {
  if (items.length === 0) return null
  return (
    <ul aria-label="Attachments" className={cn("flex flex-wrap gap-1.5", className)}>
      {items.map((item, i) => (
        <li
          key={`${item.name}:${i}`}
          className="inline-flex max-w-48 items-center gap-1.5 rounded-lg border border-border bg-background p-1 pr-2 text-xs"
        >
          {item.kind === "image" && item.thumb_url ? (
            <img src={item.thumb_url} alt="" className="size-8 shrink-0 rounded-md object-cover" />
          ) : (
            <span className="flex size-8 shrink-0 items-center justify-center rounded-md bg-primary/10 text-primary">
              <FileText aria-hidden className="size-4" />
            </span>
          )}
          <span className="min-w-0 truncate" title={item.name}>{item.name}</span>
          {onRemove && (
            <button
              type="button"
              aria-label={`Remove ${item.name}`}
              disabled={disabled}
              onClick={() => onRemove(i)}
              className="shrink-0 cursor-pointer rounded p-0.5 text-muted-foreground hover:bg-accent hover:text-foreground disabled:opacity-40"
            >
              <X className="size-3" />
            </button>
          )}
        </li>
      ))}
    </ul>
  )
}

/** Files can also be dropped on the composer or pasted into it. */
export function AttachButton({
  disabled,
  uploading,
  count,
  onFiles,
}: {
  disabled: boolean
  uploading: boolean
  count: number
  onFiles: (files: File[]) => void
}) {
  const input = React.useRef<HTMLInputElement>(null)
  return (
    <span className="flex items-center gap-1">
      <input
        ref={input}
        type="file"
        multiple
        accept={ACCEPT}
        className="sr-only"
        tabIndex={-1}
        onChange={(e) => {
          onFiles(Array.from(e.target.files ?? []))
          e.target.value = ""
        }}
      />
      <button
        type="button"
        disabled={disabled || uploading || count >= MAX_ATTACHMENTS}
        aria-label="Attach files"
        data-tooltip="PDF, Word, text or images: pick, drop or paste. Up to three files, 2 MB each. Images need a vision-capable model."
        onClick={() => input.current?.click()}
        className="cursor-pointer rounded-md p-1.5 text-muted-foreground hover:bg-accent disabled:opacity-40"
      >
        {uploading ? <Loader2 className="size-4 animate-spin" /> : <Paperclip className="size-4" />}
      </button>
      {uploading && <span role="status" className="text-xs text-muted-foreground">Reading attachment…</span>}
    </span>
  )
}
