import * as React from "react"
import { cn } from "../lib"

export const controlClass =
  "w-full min-w-0 rounded-sm border border-control-border bg-surface px-3.5 text-body text-ink placeholder:text-ink-tertiary focus-visible:border-focus focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-focus disabled:cursor-not-allowed disabled:opacity-50 aria-invalid:border-critical"

export const Input = React.forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(
  ({ className, ...props }, ref) => <input ref={ref} className={cn(controlClass, "h-control-md", className)} {...props} />,
)
Input.displayName = "Input"

export const Textarea = React.forwardRef<HTMLTextAreaElement, React.TextareaHTMLAttributes<HTMLTextAreaElement>>(
  ({ className, ...props }, ref) => (
    <textarea ref={ref} className={cn(controlClass, "min-h-24 resize-y py-2", className)} {...props} />
  ),
)
Textarea.displayName = "Textarea"

const CHEVRON =
  "bg-[url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%237f8a7b' stroke-width='1.75' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='m6 9 6 6 6-6'/%3E%3C/svg%3E\")]"

export const Select = React.forwardRef<HTMLSelectElement, React.SelectHTMLAttributes<HTMLSelectElement>>(
  ({ className, ...props }, ref) => (
    <select
      ref={ref}
      className={cn(
        controlClass,
        CHEVRON,
        "h-control-md cursor-pointer appearance-none bg-[length:16px] bg-[right_12px_center] bg-no-repeat pr-10",
        className,
      )}
      {...props}
    />
  ),
)
Select.displayName = "Select"

interface FieldOwnProps {
  label: string
  hint?: React.ReactNode
  error?: React.ReactNode
  id?: string
  className?: string
  /** A custom control (Select, Textarea...); it receives the id and described-by wiring. */
  children?: React.ReactElement<React.InputHTMLAttributes<HTMLElement>>
}

export type FieldProps = FieldOwnProps & Omit<React.InputHTMLAttributes<HTMLInputElement>, keyof FieldOwnProps>

export const Field = React.forwardRef<HTMLInputElement, FieldProps>(
  ({ label, hint, error, id, className, children, ...input }, ref) => {
    const generated = React.useId()
    const controlId = id ?? children?.props.id ?? generated
    const noteId = `${controlId}-note`
    const wiring = {
      id: controlId,
      "aria-invalid": error ? true : undefined,
      "aria-describedby": error || hint ? noteId : undefined,
    }
    return (
      <div className={cn("flex flex-col gap-1.5", className)}>
        <label htmlFor={controlId} className="text-sm leading-5 font-semibold text-ink">
          {label}
        </label>
        {children ? React.cloneElement(children, wiring) : <Input ref={ref} {...wiring} {...input} />}
        {error ? (
          <span id={noteId} className="text-footnote font-medium text-critical">
            {error}
          </span>
        ) : hint ? (
          <span id={noteId} className="text-footnote text-ink-secondary">
            {hint}
          </span>
        ) : null}
      </div>
    )
  },
)
Field.displayName = "Field"
