/* eslint-disable react/only-export-components -- the mode table ships with its picker */
import * as React from "react"
import { Bot, Check, ChevronDown, MessageCircle, type LucideIcon } from "lucide-react"
import { useLocation, useNavigate } from "react-router-dom"
import { AGENT_MODES, type AgentMode } from "../../lib/gradis"
import { cn } from "../../lib/utils"
import { useKeepInViewport } from "../ui/keepInViewport"
import { useDismiss } from "../../lib/useDismiss"

const ROW = "flex w-full cursor-pointer items-start gap-2 rounded-md px-2 py-1.5 text-left hover:bg-accent focus-visible:bg-accent focus-visible:outline-none"

/** What each mode is called and does, as the picker shows it. The tools
 * behind each live on the server (api/assistant/modes.py). */
export const MODE_INFO: Record<AgentMode, { label: string; hint: string; icon: LucideIcon }> = {
  chat: { label: "Chat", hint: "Talk it through with answers from your data and the web. Makes no changes.", icon: MessageCircle },
  agent: { label: "Agent", hint: "Does the work, asks before changing anything.", icon: Bot },
}

/** Mode picker beside the model chip; built like ModelDropup. */
export function ModeDropup({ value, onChange }: { value: AgentMode; onChange: (mode: AgentMode) => void }) {
  const navigate = useNavigate()
  const location = useLocation()
  const [open, setOpen] = React.useState(false)
  const boxRef = React.useRef<HTMLSpanElement>(null)
  const listRef = React.useRef<HTMLDivElement>(null)
  useKeepInViewport(listRef, open)

  React.useEffect(() => {
    if (!open) return
    // Focus the current mode, so arrows start from it.
    requestAnimationFrame(() =>
      listRef.current?.querySelector<HTMLElement>("[aria-checked=true]")?.focus(),
    )
  }, [open])
  useDismiss(open, boxRef, () => setOpen(false))

  const active = MODE_INFO[value]
  const Icon = active.icon

  function pick(mode: AgentMode) {
    onChange(mode)
    setOpen(false)
  }

  function manageTools() {
    setOpen(false)
    const params = new URLSearchParams(location.search)
    params.set("settings", "agents")
    navigate(`${location.pathname}?${params.toString()}`)
  }

  function onListKey(e: React.KeyboardEvent<HTMLDivElement>) {
    if (e.key !== "ArrowDown" && e.key !== "ArrowUp") return
    const items = Array.from(listRef.current?.querySelectorAll<HTMLElement>("button") ?? [])
    const at = items.indexOf(document.activeElement as HTMLElement)
    e.preventDefault()
    const step = e.key === "ArrowDown" ? 1 : -1
    items[(at + step + items.length) % items.length]?.focus()
  }

  return (
    <span ref={boxRef} className="relative">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-haspopup="menu"
        aria-expanded={open}
        data-tooltip={`Mode: ${active.label}. ${active.hint}`}
        aria-label={`Mode: ${active.label}`}
        className="flex h-7 cursor-pointer items-center gap-1.5 rounded-md px-2 text-xs font-medium text-muted-foreground hover:bg-accent hover:text-foreground @max-[24rem]/composer:w-7 @max-[24rem]/composer:justify-center @max-[24rem]/composer:px-0"
      >
        <Icon className="size-3.5 shrink-0" />
        <span className="@max-[24rem]/composer:hidden">{active.label}</span>
        <ChevronDown className={cn("size-3 transition-transform @max-[24rem]/composer:hidden", open && "rotate-180")} />
      </button>
      {open && (
        <div
          ref={listRef}
          role="menu"
          aria-label="Choose a mode"
          onKeyDown={onListKey}
          className="absolute bottom-full left-0 z-20 mb-2 w-64 max-w-[calc(100vw-1rem)] overflow-hidden rounded-xl border border-border bg-popover text-sm shadow-xl depth-fade"
        >
          <div className="space-y-1 p-1">
            {AGENT_MODES.map((mode) => {
              const info = MODE_INFO[mode]
              const selected = mode === value
              return (
                <button
                  key={mode}
                  type="button"
                  role="menuitemradio"
                  aria-checked={selected}
                  onClick={() => pick(mode)}
                  className={ROW}
                >
                  <info.icon className="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-hidden />
                  <span className="min-w-0 flex-1">
                    <span className="block">{info.label}</span>
                    <span className="block type-caption">{info.hint}</span>
                  </span>
                  <span className="mt-0.5 w-4 shrink-0">{selected && <Check className="size-3.5" />}</span>
                </button>
              )
            })}
          </div>
          <div className="border-t border-border p-1">
            <button type="button" role="menuitem" onClick={manageTools} className={cn(ROW, "items-center")}>
              <span className="w-4 shrink-0" />
              <span className="flex-1">Manage tools...</span>
            </button>
          </div>
        </div>
      )}
    </span>
  )
}
