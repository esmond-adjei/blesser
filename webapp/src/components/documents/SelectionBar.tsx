import * as React from "react"
import { ArrowUp, MessageSquare, Save } from "lucide-react"
import type { CvSuggestAction } from "../../lib/types"
import { cn } from "../../lib/utils"
import { ACTION_LABEL, MAX_SELECTION_CHARS } from "./documentText"

function Chip({ children, onClick, title }: { children: React.ReactNode; onClick: () => void; title?: string }) {
  return (
    <button
      type="button"
      title={title}
      // Keep the editor's selection: the action works on it.
      onMouseDown={(e) => e.preventDefault()}
      onClick={onClick}
      className="inline-flex h-7 min-w-0 shrink-0 cursor-pointer items-center rounded-md px-2 text-[13px] font-medium text-label-secondary transition-colors duration-150 hover:bg-accent hover:text-foreground"
    >
      {children}
    </button>
  )
}

/** Each action becomes a suggestion in the side panel, so the text only changes once it's
 * applied there. Key it by each opening, so the request field starts empty. */
export function SelectionBar({
  text,
  focus,
  saved,
  tailorFor,
  saving,
  onAsk,
  onChat,
  onSave,
  onClose,
}: {
  text: string
  /** Opened with the shortcut: start in the request field. */
  focus: boolean
  /** False for an unsaved variant: suggestions need the saved text. */
  saved: boolean
  tailorFor: string | null
  saving: boolean
  onAsk: (action: CvSuggestAction, instruction?: string) => void
  /** Hand this passage to Gradis in the panel; absent where there's no chat. */
  onChat?: () => void
  onSave: () => void
  onClose: () => void
}) {
  const [request, setRequest] = React.useState("")
  const input = React.useRef<HTMLInputElement | null>(null)

  React.useEffect(() => {
    if (focus) input.current?.focus()
  }, [focus])

  // One row on a desktop; on a phone the request field takes a row of its own.
  const shell = "cm-doc-askbar flex w-[calc(100vw-32px)] max-w-max flex-wrap items-center sm:w-max sm:max-w-[40rem] sm:flex-nowrap gap-0.5 rounded-lg border border-border bg-popover p-1 text-popover-foreground shadow-md"

  if (!saved) {
    return (
      <div role="dialog" aria-label="Suggest a change" className={cn(shell, "gap-2 pl-3")}>
        <span className="text-[13px] text-muted-foreground">Save to get suggestions</span>
        <button
          type="button"
          onMouseDown={(e) => e.preventDefault()}
          onClick={onSave}
          disabled={saving}
          className="inline-flex h-7 cursor-pointer items-center gap-1.5 rounded-md bg-primary px-2.5 text-[13px] font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-60 [&_svg]:size-3.5"
        >
          <Save /> {saving ? "Saving…" : "Save"}
        </button>
      </div>
    )
  }

  if (text.length > MAX_SELECTION_CHARS) {
    return (
      <div role="dialog" aria-label="Suggest a change" className={cn(shell, "px-3 py-1.5 text-[13px] text-muted-foreground")}>
        Select a shorter passage to get a suggestion.
      </div>
    )
  }

  const submit = (e: React.FormEvent) => {
    e.preventDefault()
    const own = request.trim()
    if (own) onAsk("custom", own)
  }

  return (
    <div role="dialog" aria-label="Suggest a change" className={shell}>
      <Chip onClick={() => onAsk("improve")}>{ACTION_LABEL.improve}</Chip>
      <Chip onClick={() => onAsk("shorten")}>{ACTION_LABEL.shorten}</Chip>
      <Chip onClick={() => onAsk("quantify")} title="Bring numbers forward; a missing figure becomes a [placeholder]">
        {ACTION_LABEL.quantify}
      </Chip>
      {tailorFor ? (
        <Chip onClick={() => onAsk("tailor")} title={`Tailor to ${tailorFor}`}>
          <span className="max-w-[10rem] truncate">Tailor to {tailorFor}</span>
        </Chip>
      ) : null}
      {onChat && (
        <Chip onClick={onChat} title="Ask Gradis about this passage, in the side panel">
          <MessageSquare className="mr-1.5 size-3.5" aria-hidden /> Ask in chat
        </Chip>
      )}
      <span aria-hidden className="mx-0.5 hidden h-4 w-px bg-border sm:block" />
      <form onSubmit={submit} className="flex h-7 min-w-[12rem] flex-1 basis-full items-center sm:basis-auto rounded-md pl-2 focus-within:bg-accent/60">
        <input
          ref={input}
          value={request}
          onChange={(e) => setRequest(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Escape") {
              e.preventDefault()
              onClose()
            }
          }}
          maxLength={1000}
          placeholder="Ask for a change…"
          aria-label="Ask for a change"
          className="h-full min-w-0 flex-1 bg-transparent text-[13px] placeholder:text-muted-foreground focus:outline-none"
        />
        <button
          type="submit"
          aria-label="Suggest"
          disabled={!request.trim()}
          className="inline-flex size-6 shrink-0 cursor-pointer items-center justify-center rounded text-muted-foreground hover:bg-accent hover:text-foreground disabled:pointer-events-none disabled:opacity-0 [&_svg]:size-3.5"
        >
          <ArrowUp />
        </button>
      </form>
    </div>
  )
}
