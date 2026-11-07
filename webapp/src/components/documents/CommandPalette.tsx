import * as React from "react"
import { Command } from "lucide-react"
import { cn } from "../../lib/utils"
import { Dialog, DialogBody, DialogContent, DialogTitle } from "../ui/dialog"

export type PaletteCommand = {
  id: string
  label: string
  hint?: string
  disabled?: boolean
  run: () => void
}

/** Ctrl+K / Cmd+K: type to filter the editor's commands, Enter runs. */
export function CommandPalette({
  open,
  onOpenChange,
  commands,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  commands: PaletteCommand[]
}) {
  const [q, setQ] = React.useState("")
  const [index, setIndex] = React.useState(0)
  // Cleared on the way out, so the next open starts empty.
  const close = React.useCallback(() => {
    setQ("")
    setIndex(0)
    onOpenChange(false)
  }, [onOpenChange])
  const shown = commands.filter(
    (c) => !c.disabled && c.label.toLowerCase().includes(q.trim().toLowerCase()),
  )
  function run(c: PaletteCommand | undefined) {
    if (!c) return
    close()
    // After the dialog closes, so focus moves where the command sends it.
    window.setTimeout(c.run, 0)
  }
  return (
    <Dialog open={open} onOpenChange={(next) => (next ? onOpenChange(true) : close())}>
      <DialogContent onClose={close} className="max-w-md">
        <DialogTitle className="sr-only">Commands</DialogTitle>
        <div className="flex shrink-0 items-center gap-2 border-b border-border px-4 py-3 pr-12">
          <Command className="size-4 text-muted-foreground" />
          <input
            autoFocus
            value={q}
            onChange={(e) => {
              setQ(e.target.value)
              setIndex(0)
            }}
            onKeyDown={(e) => {
              if (e.key === "ArrowDown") {
                e.preventDefault()
                setIndex((i) => Math.min(i + 1, shown.length - 1))
              } else if (e.key === "ArrowUp") {
                e.preventDefault()
                setIndex((i) => Math.max(i - 1, 0))
              } else if (e.key === "Enter") {
                e.preventDefault()
                run(shown[index])
              }
            }}
            placeholder="Type a command"
            aria-label="Command"
            className="w-full bg-transparent text-sm focus:outline-none"
          />
        </div>
        <DialogBody className="max-h-72 px-2 py-2">
          <ul role="listbox">
            {shown.map((c, i) => (
              <li key={c.id} role="option" aria-selected={i === index}>
                <button
                  type="button"
                  onMouseEnter={() => setIndex(i)}
                  onClick={() => run(c)}
                  className={cn(
                    "flex w-full items-center justify-between rounded-md px-2 py-1.5 text-left text-sm",
                    i === index && "bg-accent",
                  )}
                >
                  {c.label}
                  {c.hint && <span className="type-caption">{c.hint}</span>}
                </button>
              </li>
            ))}
            {shown.length === 0 && <li className="px-2 py-2 type-meta">No matching command.</li>}
          </ul>
        </DialogBody>
      </DialogContent>
    </Dialog>
  )
}
