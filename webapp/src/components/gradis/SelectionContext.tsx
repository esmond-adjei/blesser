import * as React from "react"
import { createPortal } from "react-dom"
import { MessageCircle, Plus } from "lucide-react"
import { useLocation } from "react-router-dom"
import { useGradis } from "./GradisProvider"

/** Pages that describe one thing: the only place besides chat where a passage is worth keeping. */
const DETAIL_PATHS = [
  /^\/runs\/[^/]+$/,
  /^\/runs\/[^/]+\/programmes\/[^/]+$/,
  /^\/dossier\/[^/]+$/,
  /^\/professors\/[^/]+$/,
  /^\/outbox\/[^/]+$/,
  /^\/applications\/[^/]+$/,
  /^\/schools\/[^/]+$/,
]

function hasDetailContext(pathname: string) {
  const path = pathname.length > 1 ? pathname.replace(/\/+$/, "") : pathname
  return path === "/chat" || path.startsWith("/chat/") || DETAIL_PATHS.some((pattern) => pattern.test(path))
}

export function SelectionContext() {
  const { attachSelection } = useGradis()
  const { pathname } = useLocation()
  const active = hasDetailContext(pathname)
  const [picked, setPicked] = React.useState<{ text: string; x: number; y: number } | null>(null)
  React.useEffect(() => {
    // Listings, settings, editors and public pages say too little about one
    // subject for a loose selection to make sense as chatbot context.
    if (!active) {
      setPicked(null)
      return
    }
    function inspect() {
      const selection = window.getSelection()
      const node = selection?.anchorNode?.parentElement
      const end = selection?.focusNode?.parentElement
      const text = selection?.toString().trim() ?? ""
      const relevant = "main, article, [data-context-source]"
      const excluded = "input, textarea, select, [contenteditable=true], nav, [data-gradis-composer]"
      if (!selection?.rangeCount || !text || text.length > 5000 || !node?.closest(relevant) || !end?.closest(relevant) || node.closest(excluded) || end.closest(excluded)) { setPicked(null); return }
      const rect = selection.getRangeAt(0).getBoundingClientRect()
      setPicked({ text, x: Math.max(8, Math.min(rect.left, window.innerWidth - 196)), y: Math.max(8, Math.min(rect.bottom + 8, window.innerHeight - 48)) })
    }
    function dismiss() { setPicked(null) }
    function key(e: KeyboardEvent) { if (e.key === "Escape") dismiss(); else inspect() }
    document.addEventListener("pointerup", inspect)
    document.addEventListener("keyup", key)
    document.addEventListener("scroll", dismiss, true)
    window.addEventListener("resize", dismiss)
    return () => { document.removeEventListener("pointerup", inspect); document.removeEventListener("keyup", key); document.removeEventListener("scroll", dismiss, true); window.removeEventListener("resize", dismiss) }
  }, [active])
  if (!picked) return null
  return createPortal(<button type="button" onPointerDown={e => e.preventDefault()} onClick={() => { attachSelection(picked.text); setPicked(null); window.getSelection()?.removeAllRanges() }} style={{ left: picked.x, top: picked.y }} className="fixed z-[80] flex cursor-pointer items-center gap-2 rounded-lg border border-border bg-popover px-3 py-2 text-xs text-popover-foreground shadow-lg"><MessageCircle className="size-4" /><span>Add to Gradis context</span><Plus className="size-3" /></button>, document.body)
}
