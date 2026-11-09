import * as React from "react"
import { cn } from "@blesser/ui"

export function PageHeader({
  title,
  description,
  actions,
  back,
  className,
}: {
  title: React.ReactNode
  description?: React.ReactNode
  actions?: React.ReactNode
  back?: React.ReactNode
  className?: string
}) {
  return (
    <header className={cn("flex flex-wrap items-start justify-between gap-x-4 gap-y-3", className)}>
      <div className="min-w-0 flex-1 basis-64">
        {back ? <div className="mb-1 text-footnote text-ink-secondary">{back}</div> : null}
        <h1 className="font-display text-xl leading-7 font-semibold tracking-[-0.01em] text-ink">{title}</h1>
        {description ? <p className="mt-0.5 max-w-2xl text-footnote text-ink-secondary">{description}</p> : null}
      </div>
      {actions ? <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div> : null}
    </header>
  )
}

/** Segmented filter: one pressed option, arrow keys move between them. */
export function Segmented<T extends string>({
  label,
  value,
  options,
  onChange,
  className,
}: {
  label: string
  value: T
  options: { value: T; label: string; count?: number }[]
  onChange: (value: T) => void
  className?: string
}) {
  const refs = React.useRef<(HTMLButtonElement | null)[]>([])
  const move = (from: number, step: number) => {
    const next = (from + step + options.length) % options.length
    refs.current[next]?.focus()
    onChange(options[next].value)
  }
  return (
    <div
      role="radiogroup"
      aria-label={label}
      className={cn("nice-scroll flex w-fit max-w-full items-center gap-0.5 overflow-x-auto rounded-md bg-surface-sunk p-0.5", className)}
    >
      {options.map((o, i) => {
        const selected = o.value === value
        return (
          <button
            key={o.value}
            ref={(el) => {
              refs.current[i] = el
            }}
            type="button"
            role="radio"
            aria-checked={selected}
            tabIndex={selected ? 0 : -1}
            onClick={() => onChange(o.value)}
            onKeyDown={(e) => {
              if (e.key === "ArrowRight" || e.key === "ArrowDown") {
                e.preventDefault()
                move(i, 1)
              } else if (e.key === "ArrowLeft" || e.key === "ArrowUp") {
                e.preventDefault()
                move(i, -1)
              }
            }}
            className={cn(
              "flex h-7 shrink-0 cursor-pointer items-center gap-1.5 rounded-[6px] px-2.5 text-footnote font-medium whitespace-nowrap transition-colors duration-160",
              selected ? "bg-surface text-ink shadow-elevation-1" : "text-ink-secondary hover:text-ink",
            )}
          >
            {o.label}
            {o.count != null ? <span className="text-ink-tertiary tabular-nums">{o.count}</span> : null}
          </button>
        )
      })}
    </div>
  )
}

/** A two-state filter toggle that reads as a checkbox, not a coloured pill. */
export function FilterToggle({
  pressed,
  onChange,
  children,
}: {
  pressed: boolean
  onChange: (next: boolean) => void
  children: React.ReactNode
}) {
  return (
    <button
      type="button"
      aria-pressed={pressed}
      onClick={() => onChange(!pressed)}
      className={cn(
        "flex h-control-sm shrink-0 cursor-pointer items-center gap-2 rounded-sm border px-2.5 text-footnote font-medium whitespace-nowrap transition-colors duration-160",
        pressed ? "border-forest/50 bg-forest-soft text-link" : "border-separator bg-surface text-ink-secondary hover:text-ink",
      )}
    >
      <span
        aria-hidden="true"
        className={cn(
          "grid size-3.5 place-items-center rounded-[3px] border",
          pressed ? "border-forest bg-forest text-on-forest" : "border-control-border",
        )}
      >
        {pressed ? (
          <svg viewBox="0 0 12 12" className="size-2.5" fill="none" stroke="currentColor" strokeWidth={2}>
            <path d="m2.5 6 2.5 2.5 4.5-5" />
          </svg>
        ) : null}
      </span>
      {children}
    </button>
  )
}
