import * as React from "react"
import { cn } from "../lib"

export const controlClass =
  "w-full min-w-0 rounded-sm border border-input-border bg-surface px-3.5 text-body text-ink transition-[border-color,box-shadow] duration-150 outline-none placeholder:text-ink-tertiary hover:border-input-border-hover focus:border-focus focus:shadow-[0_0_0_3px_var(--focus-soft)] disabled:cursor-not-allowed disabled:opacity-50 aria-invalid:border-critical aria-invalid:focus:shadow-[0_0_0_3px_var(--critical-soft)]"

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

export const Select = React.forwardRef<HTMLSelectElement, React.SelectHTMLAttributes<HTMLSelectElement>>(
  ({ className, ...props }, ref) => (
    <select
      ref={ref}
      className={cn(controlClass, "select-chevron h-control-md cursor-pointer appearance-none pr-10", className)}
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
