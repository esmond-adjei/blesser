import { AlertDialog, AlertDialogContent, AlertDialogTitle, AlertDialogDescription } from "../ui/alert-dialog"
import { Checkbox } from "../ui/checkbox"
import { Select as NativeSelect } from "@blesser/ui"
import * as React from "react"
import { Eye, EyeOff, Plus, Trash2, X } from "lucide-react"
import { Button, Field, Textarea, cn } from "@blesser/ui"
import { completenessLabel } from "../../lib/kit"
import { SettingsGroup } from "../settings/controls"
import { DialogBody, DialogHeader } from "../ui/dialog"

export function CompletenessMeter({ value, hint, className }: { value: number; hint?: string | null; className?: string }) {
  const n = Math.round(Math.min(100, Math.max(0, value || 0)))
  const id = React.useId()
  return (
    <div className={cn("min-w-0", className)}>
      <div className="flex items-baseline justify-between gap-3">
        <p id={id} className="text-footnote font-semibold text-ink">{completenessLabel(n)}</p>
        <p className="text-footnote text-ink-secondary tabular-nums">{n}%</p>
      </div>
      <div
        role="meter"
        aria-labelledby={id}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={n}
        aria-valuetext={`${n}% complete`}
        className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-surface-sunk"
      >
        <div className="h-full rounded-full bg-forest transition-[width] duration-500 ease-out motion-reduce:transition-none" style={{ width: `${n}%` }} />
      </div>
      {hint ? <p className="mt-2 text-footnote text-ink-secondary">{hint}</p> : null}
    </div>
  )
}

export function FormGrid({ children, className }: { children: React.ReactNode; className?: string }) {
  return <div className={cn("grid gap-4 px-4 py-4 sm:grid-cols-2 sm:px-5", className)}>{children}</div>
}

type TextProps = Omit<React.InputHTMLAttributes<HTMLInputElement>, "value" | "onChange" | "children"> & {
  label: string
  value: string | number | null | undefined
  onChange: (value: string) => void
  hint?: React.ReactNode
  wide?: boolean
}

export function TextField({ label, value, onChange, hint, wide, className, ...input }: TextProps) {
  return (
    <Field
      label={label}
      hint={hint}
      value={value ?? ""}
      onChange={(e) => onChange(e.target.value)}
      className={cn(wide && "sm:col-span-2", className)}
      {...input}
    />
  )
}

export function TextAreaField({ label, value, onChange, hint, rows = 4, maxLength, placeholder, counter }: {
  label: string
  value: string
  onChange: (value: string) => void
  hint?: React.ReactNode
  rows?: number
  maxLength?: number
  placeholder?: string
  counter?: boolean
}) {
  const note = counter && maxLength ? (
    <span className="flex justify-between gap-3">
      <span>{hint}</span>
      <span className={cn("shrink-0 tabular-nums", value.length > maxLength * 0.9 && "text-caution")}>{value.length} / {maxLength}</span>
    </span>
  ) : hint
  return (
    <Field label={label} hint={note} className="sm:col-span-2">
      <Textarea value={value} onChange={(e) => onChange(e.target.value)} rows={rows} maxLength={maxLength} placeholder={placeholder} className="min-h-0 text-callout" />
    </Field>
  )
}

export function SelectField({ label, value, onChange, options, hint, placeholder }: {
  label: string
  value: string
  onChange: (value: string) => void
  options: { value: string; label: string }[]
  hint?: React.ReactNode
  placeholder?: string
}) {
  return (
    <Field label={label} hint={hint}>
      <NativeSelect
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="select-chevron h-control-md w-full min-w-0 cursor-pointer appearance-none rounded-sm border border-input-border bg-surface px-3.5 pr-10 text-body text-ink outline-none transition-[border-color,box-shadow] duration-150 hover:border-input-border-hover"
      >
        {placeholder !== undefined ? <option value="">{placeholder}</option> : null}
        {options.map((o) => (
          <option key={o.value} value={o.value}>{o.label}</option>
        ))}
      </NativeSelect>
    </Field>
  )
}

export function CheckField({ label, checked, onChange, hint }: { label: string; checked: boolean; onChange: (v: boolean) => void; hint?: string }) {
  return (
    <label className="flex cursor-pointer items-start gap-2.5 self-end py-1">
      <Checkbox checked={checked} onCheckedChange={(value) => onChange(value === true)} className="mt-0.5" />
      <span className="min-w-0">
        <span className="block text-callout font-medium text-ink">{label}</span>
        {hint ? <span className="block text-footnote text-ink-secondary">{hint}</span> : null}
      </span>
    </label>
  )
}

/** A list of like entries inside a settings-style group: one card row each, remove per row, add at the foot. */
export function Repeatable<T>({ items, onChange, make, noun, title, render, empty }: {
  items: T[]
  onChange: (items: T[]) => void
  make: () => T
  noun: string
  title: (item: T, index: number) => string
  render: (item: T, set: (patch: Partial<T>) => void, index: number) => React.ReactNode
  empty?: string
}) {
  const listRef = React.useRef<HTMLDivElement | null>(null)
  const add = () => {
    onChange([...items, make()])
    requestAnimationFrame(() => {
      const blocks = listRef.current?.querySelectorAll<HTMLElement>("[data-entry]")
      blocks?.[blocks.length - 1]?.querySelector<HTMLElement>("input, textarea, select")?.focus()
    })
  }
  return (
    <div ref={listRef} className="divide-y divide-separator">
      {items.length === 0 && empty ? <p className="px-4 py-4 text-footnote text-ink-secondary sm:px-5">{empty}</p> : null}
      {items.map((item, i) => {
        const heading = title(item, i)
        return (
          <div key={i} data-entry className="min-w-0">
            <div className="flex items-center justify-between gap-3 px-4 pt-3 sm:px-5">
              <p className="min-w-0 truncate text-footnote font-semibold text-ink-secondary">{heading}</p>
              <Button
                size="sm"
                variant="quiet"
                icon={<Trash2 />}
                aria-label={`Remove ${heading}`}
                className="size-8 text-ink-tertiary hover:text-critical [&_svg]:size-4"
                onClick={() => onChange(items.filter((_, j) => j !== i))}
              />
            </div>
            <FormGrid className="pt-2">{render(item, (patch) => onChange(items.map((x, j) => (j === i ? { ...x, ...patch } : x))), i)}</FormGrid>
          </div>
        )
      })}
      <div className="px-4 py-2.5 sm:px-5">
        <Button size="sm" variant="quiet" icon={<Plus />} onClick={add} className="-ml-2 text-link [&_svg]:size-4">
          Add {noun}
        </Button>
      </div>
    </div>
  )
}

/** Chips with a text box: Enter or comma adds, Backspace on empty removes the last. */
export function TagInput({ label, values, onChange, placeholder, hint, className }: {
  label: string
  values: string[]
  onChange: (values: string[]) => void
  placeholder?: string
  hint?: string
  className?: string
}) {
  const [text, setText] = React.useState("")
  const id = React.useId()
  const commit = (raw = text) => {
    const next = raw.split(",").map((s) => s.trim()).filter(Boolean)
    if (next.length) onChange([...values, ...next.filter((n) => !values.some((v) => v.toLowerCase() === n.toLowerCase()))])
    setText("")
  }
  return (
    <div className={cn("flex min-w-0 flex-col gap-1.5", className)}>
      <label htmlFor={id} className="text-sm leading-5 font-semibold text-ink">{label}</label>
      <div className="flex min-h-control-md flex-wrap items-center gap-1.5 rounded-sm border border-input-border bg-surface px-2 py-1.5 transition-[border-color,box-shadow] duration-150 hover:border-input-border-hover">
        {values.map((v) => (
          <span key={v} className="inline-flex h-6 max-w-full items-center gap-1 rounded-full bg-surface-sunk pr-1 pl-2.5 text-footnote text-ink">
            <span className="truncate">{v}</span>
            <button
              type="button"
              aria-label={`Remove ${v}`}
              onClick={() => onChange(values.filter((x) => x !== v))}
              className="grid size-4 cursor-pointer place-items-center rounded-full text-ink-tertiary hover:bg-separator hover:text-ink"
            >
              <X className="size-3" />
            </button>
          </span>
        ))}
        <input
          id={id}
          value={text}
          onChange={(e) => (e.target.value.includes(",") ? commit(e.target.value) : setText(e.target.value))}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault()
              commit()
            } else if (e.key === "Backspace" && !text && values.length) {
              onChange(values.slice(0, -1))
            }
          }}
          onBlur={() => commit()}
          placeholder={values.length ? undefined : placeholder}
          aria-describedby={hint ? `${id}-hint` : undefined}
          className="h-7 min-w-24 flex-1 bg-transparent px-1 text-callout text-ink outline-none placeholder:text-ink-tertiary"
        />
      </div>
      {hint ? <span id={`${id}-hint`} className="text-footnote text-ink-secondary">{hint}</span> : null}
    </div>
  )
}

/** Shows a masked value until the member asks to see it; editing needs the plain value first. */
export function SecretField({ label, value, masked, revealed, onReveal, onHide, onChange, busy, hint, type = "text" }: {
  label: string
  value: string
  masked: string
  revealed: boolean
  onReveal: () => void
  onHide: () => void
  onChange: (value: string) => void
  busy?: boolean
  hint?: string
  type?: "text" | "date"
}) {
  const id = React.useId()
  return (
    <div className="flex min-w-0 flex-col gap-1.5">
      <label htmlFor={id} className="text-sm leading-5 font-semibold text-ink">{label}</label>
      <div className="flex gap-2">
        <input
          id={id}
          type={revealed ? type : "text"}
          value={revealed ? value : masked}
          readOnly={!revealed}
          onChange={(e) => onChange(e.target.value)}
          onFocus={() => !revealed && !busy && onReveal()}
          autoComplete="off"
          spellCheck={false}
          placeholder={revealed ? undefined : "Not added"}
          aria-describedby={hint ? `${id}-hint` : undefined}
          className={cn(
            "h-control-md w-full min-w-0 rounded-sm border border-input-border bg-surface px-3.5 font-mono text-callout text-ink placeholder:font-sans placeholder:text-ink-tertiary outline-none transition-[border-color,box-shadow] duration-150 hover:border-input-border-hover",
            !revealed && "bg-surface-sunk text-ink-secondary",
          )}
        />
        <Button
          size="md"
          variant="secondary"
          icon={revealed ? <EyeOff /> : <Eye />}
          aria-label={revealed ? `Hide ${label}` : `Show ${label}`}
          disabled={busy}
          onClick={revealed ? onHide : onReveal}
          className="[&_svg]:size-4"
        />
      </div>
      {hint ? <span id={`${id}-hint`} className="text-footnote text-ink-secondary">{hint}</span> : null}
    </div>
  )
}

export function ConfirmDialog({ open, onOpenChange, title, description, confirm, onConfirm }: {
  open: boolean
  onOpenChange: (open: boolean) => void
  title: string
  description: string
  confirm: string
  onConfirm: () => Promise<void> | void
}) {
  const [busy, setBusy] = React.useState(false)
  const close = React.useCallback(() => onOpenChange(false), [onOpenChange])
  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent className="max-w-md">
        <DialogHeader>
          <AlertDialogTitle className="type-title-3">{title}</AlertDialogTitle>
          <AlertDialogDescription className="text-callout text-ink-secondary">{description}</AlertDialogDescription>
        </DialogHeader>
        <DialogBody>
          <div className="flex justify-end gap-2">
            <Button size="sm" variant="quiet" onClick={close}>Cancel</Button>
            <Button
              size="sm"
              variant="danger"
              disabled={busy}
              onClick={async () => {
                setBusy(true)
                try {
                  await onConfirm()
                  close()
                } finally {
                  setBusy(false)
                }
              }}
            >
              {confirm}
            </Button>
          </div>
        </DialogBody>
      </AlertDialogContent>
    </AlertDialog>
  )
}

export function KitSkeleton({ rows = 3 }: { rows?: number }) {
  return (
    <div className="space-y-3" aria-busy="true" aria-label="Loading">
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} className="h-24 animate-pulse rounded-lg bg-surface-sunk motion-reduce:animate-none" />
      ))}
    </div>
  )
}

export function KitGroup({ id, title, description, children }: { id: string; title: string; description?: string; children: React.ReactNode }) {
  return (
    <div id={id} className="scroll-mt-6">
      <SettingsGroup title={title} description={description}>
        <div className="min-w-0">{children}</div>
      </SettingsGroup>
    </div>
  )
}

/** The wide-screen rail: completeness, then jump links to each group. */
export function KitRail({ label, completeness, hint, sections }: { label: string; completeness: number; hint: string | null; sections: readonly { id: string; label: string }[] }) {
  return (
    <aside className="hidden lg:block">
      <div className="sticky top-10 space-y-5">
        <div className="rounded-lg border border-separator bg-surface p-4">
          <CompletenessMeter value={completeness} hint={hint} />
        </div>
        <nav aria-label={label}>
          <ul className="space-y-0.5">
            {sections.map((s) => (
              <li key={s.id}>
                <a href={`#${s.id}`} className="flex h-8 items-center rounded-sm px-2.5 text-footnote font-medium text-ink-secondary transition-colors duration-160 hover:bg-highlight hover:text-ink">
                  {s.label}
                </a>
              </li>
            ))}
          </ul>
        </nav>
      </div>
    </aside>
  )
}

export function KitMeterCard({ completeness, hint }: { completeness: number; hint: string | null }) {
  return (
    <div className="rounded-lg border border-separator bg-surface p-4 sm:px-5 lg:hidden">
      <CompletenessMeter value={completeness} hint={hint} />
    </div>
  )
}
