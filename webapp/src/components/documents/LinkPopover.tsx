import * as React from "react"
import { createPortal } from "react-dom"
import { Link2 } from "lucide-react"
import { Button } from "../ui/button"
import { normalizeUrl } from "./documentText"

export type LinkRequest = {
  /** The selection's box, in viewport pixels: the popover goes under it,
   * or over it near the bottom of the screen. */
  left: number
  top: number
  bottom: number
  /** The selected text the link goes on ("" links the word at the cursor). */
  label: string
  /** A web or mail address to start from: the selection or the clipboard. */
  url: string
}

const WIDTH = 320
const HEIGHT = 50
const GAP = 6
const MARGIN = 8

export function LinkPopover({
  request,
  onApply,
  onClose,
}: {
  request: LinkRequest | null
  onApply: (url: string) => void
  onClose: () => void
}) {
  const panel = React.useRef<HTMLFormElement | null>(null)
  const [url, setUrl] = React.useState("")
  const [shown, setShown] = React.useState<LinkRequest | null>(null)
  if (request !== shown) {
    setShown(request)
    setUrl(request?.url ?? "")
  }

  React.useEffect(() => {
    if (!request) return
    const onDown = (e: PointerEvent) => {
      if (!panel.current?.contains(e.target as Node)) onClose()
    }
    document.addEventListener("pointerdown", onDown)
    return () => document.removeEventListener("pointerdown", onDown)
  }, [request, onClose])

  if (!request) return null
  const width = Math.min(WIDTH, window.innerWidth - 2 * MARGIN)
  const left = Math.max(MARGIN, Math.min(request.left, window.innerWidth - width - MARGIN))
  const fitsBelow = request.bottom + GAP + HEIGHT <= window.innerHeight - MARGIN
  const top = fitsBelow ? request.bottom + GAP : Math.max(MARGIN, request.top - GAP - HEIGHT)
  return createPortal(
    <form
      ref={panel}
      role="dialog"
      aria-label="Insert link"
      style={{ position: "fixed", left, top, width }}
      className="z-50 flex items-center gap-2 rounded-lg border border-border bg-popover p-2 text-popover-foreground shadow-md"
      onSubmit={(e) => {
        e.preventDefault()
        if (url.trim()) onApply(normalizeUrl(url))
      }}
      onKeyDown={(e) => {
        if (e.key === "Escape") {
          e.preventDefault()
          onClose()
        }
      }}
    >
      <Link2 className="size-4 shrink-0 text-muted-foreground" aria-hidden />
      <input
        autoFocus
        value={url}
        onChange={(e) => setUrl(e.target.value)}
        placeholder="Paste or type a link"
        aria-label={request.label ? `Link for “${request.label.slice(0, 60)}”` : "Link address"}
        className="h-8 min-w-0 flex-1 bg-transparent text-sm focus:outline-none"
      />
      <Button type="submit" size="sm" disabled={!url.trim()}>
        Apply
      </Button>
    </form>,
    document.body,
  )
}
