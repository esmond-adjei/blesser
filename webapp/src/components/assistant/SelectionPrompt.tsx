import { useEffect, useState } from "react"
import { createPortal } from "react-dom"
import { MessageCircle } from "lucide-react"
import { useOpenAssistant } from "./dockContext"
import { usePageContext } from "./pageContextState"

const SKIP = "input, textarea, select, [contenteditable=true], nav, [data-sidebar], [aria-label=Assistant]"

/** On a record, selecting text offers to hand it to the Assistant with the next question. */
export function SelectionPrompt() {
  const { hasRecord, attachSelection } = usePageContext()
  const open = useOpenAssistant()
  const [picked, setPicked] = useState<{ text: string; x: number; y: number } | null>(null)
  useEffect(() => {
    if (!hasRecord) return
    const inspect = () => {
      const selection = window.getSelection()
      const text = selection?.toString().trim() ?? ""
      const start = selection?.anchorNode?.parentElement
      const end = selection?.focusNode?.parentElement
      if (!selection?.rangeCount || !text || text.length > 5000 || !start || !end || start.closest(SKIP) || end.closest(SKIP)) return setPicked(null)
      const rect = selection.getRangeAt(0).getBoundingClientRect()
      setPicked({ text, x: Math.max(8, Math.min(rect.left, window.innerWidth - 220)), y: Math.max(8, Math.min(rect.bottom + 8, window.innerHeight - 48)) })
    }
    const clear = () => setPicked(null)
    const key = (event: KeyboardEvent) => (event.key === "Escape" ? clear() : inspect())
    document.addEventListener("pointerup", inspect)
    document.addEventListener("keyup", key)
    document.addEventListener("scroll", clear, true)
    window.addEventListener("resize", clear)
    return () => {
      document.removeEventListener("pointerup", inspect)
      document.removeEventListener("keyup", key)
      document.removeEventListener("scroll", clear, true)
      window.removeEventListener("resize", clear)
    }
  }, [hasRecord])
  if (!hasRecord || !picked) return null
  return createPortal(
    <button
      type="button"
      onPointerDown={(event) => event.preventDefault()}
      onClick={() => { attachSelection(picked.text); setPicked(null); window.getSelection()?.removeAllRanges(); open() }}
      style={{ left: picked.x, top: picked.y }}
      className="bl-appear fixed z-[80] flex cursor-pointer items-center gap-2 rounded-lg border border-separator bg-surface px-3 py-2 text-footnote text-ink shadow-elevation-3 hover:bg-highlight"
    >
      <MessageCircle className="size-4" aria-hidden="true" />
      Ask the Assistant about this
    </button>,
    document.body,
  )
}
