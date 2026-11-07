import * as React from "react"
import { cn } from "../../lib/utils"

const Input = React.forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(
  ({ className, type, ...props }, ref) => (
    <input
      type={type}
      ref={ref}
      className={cn(
        "g-input flex disabled:cursor-not-allowed disabled:opacity-50 aria-invalid:shadow-[inset_0_0_0_1px_var(--critical)]",
        className,
      )}
      {...props}
    />
  ),
)
Input.displayName = "Input"

const Textarea = React.forwardRef<HTMLTextAreaElement, React.TextareaHTMLAttributes<HTMLTextAreaElement>>(
  ({ className, ...props }, ref) => (
    <textarea
      ref={ref}
      className={cn(
        "g-textarea flex disabled:cursor-not-allowed disabled:opacity-50",
        className,
      )}
      {...props}
    />
  ),
)
Textarea.displayName = "Textarea"

const Label = React.forwardRef<HTMLLabelElement, React.LabelHTMLAttributes<HTMLLabelElement>>(
  ({ className, ...props }, ref) => (
    <label
      ref={ref}
      className={cn("g-label", className)}
      {...props}
    />
  ),
)
Label.displayName = "Label"

export function Field({
  label,
  children,
  className,
}: {
  label: string
  children: React.ReactNode
  className?: string
}) {
  // Reuse the control's id or generate one so every Field input has an accessible name.
  const generated = React.useId()
  const only = React.Children.count(children) === 1 && React.isValidElement<{ id?: string }>(children)
  const id = only ? ((children as React.ReactElement<{ id?: string }>).props.id ?? generated) : undefined
  return (
    <div className={cn("grid gap-1.5", className)}>
      <Label htmlFor={id}>{label}</Label>
      {only ? React.cloneElement(children as React.ReactElement<{ id?: string }>, { id }) : children}
    </div>
  )
}

export { Input, Textarea, Label }
