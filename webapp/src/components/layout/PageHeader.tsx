import * as React from "react"
import { cn } from "@blesser/ui"
import { RadioGroup, Toggle } from "radix-ui"
import { useIndicator } from "../ui/indicator"

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
        <h1 className="font-display text-3xl font-bold tracking-[-0.01em] text-ink">{title}</h1>
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
  options: { value: T; label: string; count?: number; icon?: React.ReactNode }[]
  onChange: (value: T) => void
  className?: string
}) {
  const { ref, ready } = useIndicator<HTMLDivElement>('[data-state="checked"]', `${value}|${options.length}`)
  return (
    <RadioGroup.Root
      ref={ref}
      aria-label={label}
      value={value}
      onValueChange={(next) => {
        const option = options.find((item) => item.value === next)
        if (option) onChange(option.value)
      }}
      className={cn("nice-scroll relative flex w-fit max-w-full items-center gap-0.5 overflow-x-auto rounded-sm bg-surface-sunk p-0.5", className)}
    >
      <span aria-hidden="true" data-ready={ready} className="bl-indicator rounded-[6px] bg-surface-raised shadow-elevation-1" />
      {options.map((o) => (
        <RadioGroup.Item
          key={o.value}
          value={o.value}
          className="relative flex h-7 shrink-0 cursor-pointer items-center gap-1.5 rounded-[6px] px-2.5 text-footnote font-medium whitespace-nowrap text-ink-secondary transition-colors duration-160 hover:text-ink focus-visible:outline-2 focus-visible:outline-focus data-[state=checked]:text-ink [&_svg]:size-3.5"
        >
          {o.icon}
          {o.icon ? <span className="max-sm:sr-only">{o.label}</span> : o.label}
          {o.count != null ? <span className="text-ink-tertiary tabular-nums">{o.count}</span> : null}
        </RadioGroup.Item>
      ))}
    </RadioGroup.Root>
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
    <Toggle.Root
      pressed={pressed}
      onPressedChange={onChange}
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
    </Toggle.Root>
  )
}
