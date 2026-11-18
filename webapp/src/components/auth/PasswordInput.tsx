import * as React from "react"
import { Input, cn } from "@blesser/ui"
import { Eye, EyeOff } from "lucide-react"

export const PasswordInput = React.forwardRef<
  HTMLInputElement,
  Omit<React.ComponentPropsWithoutRef<typeof Input>, "type">
>(({ className, disabled, ...props }, ref) => {
  const [visible, setVisible] = React.useState(false)
  const Icon = visible ? EyeOff : Eye

  return (
    <div className="relative">
      <Input
        {...props}
        ref={ref}
        type={visible ? "text" : "password"}
        disabled={disabled}
        className={cn(className, "pr-12")}
      />
      <button
        type="button"
        aria-label={visible ? "Hide password" : "Show password"}
        aria-pressed={visible}
        aria-controls={props.id}
        disabled={disabled}
        onClick={() => setVisible((current) => !current)}
        className="absolute inset-y-0 right-0 flex w-11 items-center justify-center rounded-sm text-ink-secondary hover:text-ink focus-visible:outline-2 focus-visible:-outline-offset-4 focus-visible:outline-focus disabled:cursor-not-allowed disabled:opacity-50"
      >
        <Icon className="size-5" aria-hidden="true" />
      </button>
    </div>
  )
})

PasswordInput.displayName = "PasswordInput"
