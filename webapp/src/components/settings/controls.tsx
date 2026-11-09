import * as React from "react"
import { Check } from "lucide-react"
import { cn } from "@blesser/ui"
import { AutosaveContext, type Track } from "../../lib/autosave"
import { toastError } from "../../lib/toast"

export function Switch({
  checked, mixed = false, onChange, label, title, disabled = false,
}: {
  checked: boolean
  mixed?: boolean
  onChange: (next: boolean) => void
  label: string
  title?: string
  disabled?: boolean
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={mixed ? "mixed" : checked}
      aria-label={label}
      data-tooltip={title}
      disabled={disabled}
      onClick={() => onChange(mixed ? true : !checked)}
      className={cn(
        "relative h-5 w-9 shrink-0 cursor-pointer rounded-full transition-colors duration-160 disabled:cursor-wait disabled:opacity-50",
        mixed ? "bg-forest/45" : checked ? "bg-forest" : "bg-control-border",
      )}
    >
      <span className={cn("absolute top-0.5 flex size-4 items-center justify-center rounded-full bg-surface shadow-elevation-1 transition-all", mixed ? "left-[10px]" : checked ? "left-[18px]" : "left-0.5")}>
        {mixed && <span className="h-0.5 w-2 rounded-full bg-forest" />}
      </span>
    </button>
  )
}

type SaveState = "idle" | "saving" | "saved"

export function SettingsSection({ id, title, description, children }: {
  id: string
  title: string
  description: string
  children: React.ReactNode
}) {
  const [state, setState] = React.useState<SaveState>("idle")
  const timer = React.useRef<number | undefined>(undefined)
  React.useEffect(() => () => window.clearTimeout(timer.current), [])

  const track = React.useCallback<Track>(async (work) => {
    window.clearTimeout(timer.current)
    setState("saving")
    try {
      const result = await work
      setState("saved")
      timer.current = window.setTimeout(() => setState("idle"), 2400)
      return result
    } catch (err) {
      setState("idle")
      toastError(err, "Couldn't save")
      return undefined
    }
  }, [])

  return (
    <AutosaveContext.Provider value={track}>
      <section aria-labelledby={`${id}-title`} className="min-w-0">
        <header className="flex items-start justify-between gap-4 border-b border-separator pb-4">
          <div className="min-w-0">
            <h2 id={`${id}-title`} className="type-title-3 text-ink">{title}</h2>
            <p className="mt-1 text-footnote text-ink-secondary">{description}</p>
          </div>
          <p aria-live="polite" className="flex h-6 shrink-0 items-center gap-1 text-footnote text-ink-secondary">
            {state === "saving" ? "Saving…" : state === "saved" ? <><Check className="size-3.5 text-positive" aria-hidden="true" /> Saved</> : null}
          </p>
        </header>
        <div className="mt-6 space-y-8">{children}</div>
      </section>
    </AutosaveContext.Provider>
  )
}

export function SettingsGroup({ title, description, danger = false, children }: {
  title?: string
  description?: string
  danger?: boolean
  children: React.ReactNode
}) {
  return (
    <div className="min-w-0">
      {title ? <h3 className={cn("text-callout font-semibold", danger ? "text-critical" : "text-ink")}>{title}</h3> : null}
      {description ? <p className="mt-0.5 text-footnote text-ink-secondary">{description}</p> : null}
      <div className={cn(title && "mt-2.5", "min-w-0 divide-y rounded-lg border bg-surface", danger ? "divide-critical/20 border-critical/35" : "divide-separator border-separator")}>
        {children}
      </div>
    </div>
  )
}

/** Label and helper text on the left, the control on the right; `stack` drops the control below on phones. */
export function SettingRow({ label, description, control, htmlFor, stack = false, children }: {
  label: React.ReactNode
  description?: React.ReactNode
  control?: React.ReactNode
  htmlFor?: string
  stack?: boolean
  children?: React.ReactNode
}) {
  const Label = htmlFor ? "label" : "p"
  return (
    <div className="min-w-0 px-4 py-3.5 sm:px-5">
      <div className={cn("flex min-w-0 gap-x-6 gap-y-3", stack ? "flex-col sm:flex-row sm:items-center" : "items-center")}>
        <div className="min-w-0 flex-1">
          <Label htmlFor={htmlFor} className="block text-callout font-medium text-ink">{label}</Label>
          {description ? <div className="mt-0.5 text-footnote text-ink-secondary">{description}</div> : null}
        </div>
        {control ? <div className="flex max-w-full shrink-0 flex-wrap items-center gap-2">{control}</div> : null}
      </div>
      {children}
    </div>
  )
}
