import * as React from "react"
import { ChevronDown } from "lucide-react"
import { cn } from "../../lib/utils"

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
        "relative h-5 w-9 shrink-0 cursor-pointer rounded-full transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-wait disabled:opacity-50",
        mixed ? "bg-primary/45" : checked ? "bg-primary" : "bg-muted-foreground/30",
      )}
    >
      <span className={cn("absolute top-0.5 flex size-4 items-center justify-center rounded-full bg-background shadow transition-all", mixed ? "left-[10px]" : checked ? "left-[18px]" : "left-0.5")}>
        {mixed && <span className="h-0.5 w-2 rounded-full bg-primary/70" />}
      </span>
    </button>
  )
}

export function SettingsPanel({ title, description, action, children }: {
  title: string
  description: string
  action?: React.ReactNode
  children: React.ReactNode
}) {
  return (
    <div className="min-w-0 pb-2">
      <header className="flex flex-wrap items-start justify-between gap-3 border-b border-border/70 pb-4">
        <div className="min-w-0 flex-1 basis-48">
          <h2 className="text-xl font-semibold tracking-tight text-foreground">{title}</h2>
          <p className="mt-2 max-w-xl text-sm leading-relaxed text-muted-foreground">{description}</p>
        </div>
        {action && <div className="shrink-0">{action}</div>}
      </header>
      {children}
    </div>
  )
}

export function SettingRow({ title, description, control }: {
  title: string
  description?: string
  control: React.ReactNode
}) {
  return (
    <div className="flex min-w-0 flex-col gap-3 py-4 sm:flex-row sm:items-start sm:justify-between sm:gap-6">
      <div className="min-w-0 flex-1">
        <p className="text-sm font-medium text-foreground">{title}</p>
        {description && <p className="mt-1 text-xs leading-relaxed text-muted-foreground">{description}</p>}
      </div>
      <div className="flex max-w-full shrink-0 flex-wrap items-center gap-2 sm:justify-end">{control}</div>
    </div>
  )
}

export function SettingSection({ title, description, children }: {
  title: string
  description?: string
  children: React.ReactNode
}) {
  return (
    <section className="mt-5 min-w-0">
      <header className="mb-2">
        <h3 className="text-sm font-semibold text-foreground">{title}</h3>
        {description && <p className="mt-1 text-xs leading-relaxed text-muted-foreground">{description}</p>}
      </header>
      <div className="min-w-0 divide-y divide-border/60 rounded-xl border border-border bg-card px-4 sm:px-5">{children}</div>
    </section>
  )
}

export function SettingDisclosure({ title, description, leading, control, children }: {
  title: string
  description?: string
  /** An icon tile after the chevron. */
  leading?: React.ReactNode
  control?: React.ReactNode
  children: React.ReactNode
}) {
  const [open, setOpen] = React.useState(false)
  const id = React.useId()
  return (
    <div className="min-w-0">
      <div className="flex items-start gap-3">
        <button type="button" aria-expanded={open} aria-controls={id} onClick={() => setOpen(!open)} className="flex min-w-0 flex-1 cursor-pointer items-start gap-3 rounded-md py-4 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
          <ChevronDown aria-hidden className={cn("mt-0.5 size-4 shrink-0 text-muted-foreground transition-transform", !open && "-rotate-90")} />
          {leading}
          <span className="min-w-0">
            <span className="block text-sm font-medium text-foreground">{title}</span>
            {description && <span className="mt-1 block text-xs leading-relaxed text-muted-foreground">{description}</span>}
          </span>
        </button>
        {control && <div className="flex shrink-0 flex-wrap items-center gap-2 py-4">{control}</div>}
      </div>
      <div id={id} hidden={!open} className="min-w-0 border-t border-border/60 pb-4 pt-1">{open && children}</div>
    </div>
  )
}
