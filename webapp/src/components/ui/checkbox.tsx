import * as React from "react"
import { Checkbox as CheckboxPrimitive } from "radix-ui"
import { Check, Minus } from "lucide-react"
import { cn } from "@blesser/ui"

export function Checkbox({ className, ...props }: React.ComponentProps<typeof CheckboxPrimitive.Root>) {
  return <CheckboxPrimitive.Root className={cn("grid size-4 shrink-0 cursor-pointer place-items-center rounded-[4px] border border-control-border bg-surface text-on-forest outline-none focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus data-[state=checked]:border-forest data-[state=checked]:bg-forest data-[state=indeterminate]:border-forest data-[state=indeterminate]:bg-forest disabled:cursor-not-allowed disabled:opacity-50", className)} {...props}>
    <CheckboxPrimitive.Indicator>{props.checked === "indeterminate" ? <Minus className="size-3" /> : <Check className="size-3" />}</CheckboxPrimitive.Indicator>
  </CheckboxPrimitive.Root>
}
