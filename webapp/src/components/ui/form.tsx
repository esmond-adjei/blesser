import * as React from "react"
import { cn } from "../../lib/utils"

/** A titled group of fields; `id` lets a section index scroll to it. */
export function FormSection({
  id,
  title,
  description,
  children,
  className,
}: {
  id?: string
  title: string
  description?: React.ReactNode
  children: React.ReactNode
  className?: string
}) {
  return (
    <section id={id} aria-labelledby={id ? `${id}-title` : undefined} className={cn("scroll-mt-4", className)}>
      <h3 id={id ? `${id}-title` : undefined} className="text-sm font-semibold text-foreground">
        {title}
      </h3>
      {description && <p className="mt-0.5 type-caption">{description}</p>}
      <div className="mt-3 space-y-4">{children}</div>
    </section>
  )
}

type ControlProps = {
  id?: string
  "aria-invalid"?: boolean
  "aria-describedby"?: string
}

/** Wires the child's id, `aria-invalid` and `aria-describedby` so screen readers hear the error with the field. */
export function FormField({
  label,
  hint,
  error,
  optional,
  children,
  className,
}: {
  label: string
  hint?: React.ReactNode
  error?: string | null
  optional?: boolean
  children: React.ReactElement<ControlProps>
  className?: string
}) {
  const generated = React.useId()
  const id = children.props.id ?? generated
  const noteId = `${id}-note`
  const note = error || hint
  return (
    <div className={className}>
      <label htmlFor={id} className="mb-1.5 flex items-baseline gap-1.5 text-compact font-medium text-foreground">
        {label}
        {optional && <span className="text-xs font-normal text-muted-foreground">Optional</span>}
      </label>
      {React.cloneElement(children, {
        id,
        "aria-invalid": error ? true : undefined,
        "aria-describedby": note ? noteId : undefined,
      })}
      {note && (
        <p id={noteId} className={cn("mt-1.5 text-xs", error ? "text-destructive" : "text-muted-foreground")}>
          {note}
        </p>
      )}
    </div>
  )
}

/** Small-enum picker (2-4 options): one tap, all choices visible. */
export function SegmentedControl<T extends string | number>({
  value,
  onChange,
  options,
  label,
  id,
}: {
  value: T
  onChange: (next: T) => void
  options: { value: T; label: string }[]
  label: string
  id?: string
}) {
  return (
    <div id={id} role="radiogroup" aria-label={label} className="inline-flex rounded-lg bg-muted p-0.5">
      {options.map((o) => {
        const active = o.value === value
        return (
          <button
            key={o.value}
            type="button"
            role="radio"
            aria-checked={active}
            onClick={() => onChange(o.value)}
            className={cn(
              "h-7 cursor-pointer rounded-md px-3 text-compact font-medium transition-colors",
              active ? "bg-background text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground",
            )}
          >
            {o.label}
          </button>
        )
      })}
    </div>
  )
}
