import * as React from "react"
import { Popover as PopoverPrimitive } from "radix-ui"
import { cn } from "@blesser/ui"

export const Popover = PopoverPrimitive.Root
export const PopoverTrigger = PopoverPrimitive.Trigger
export function PopoverContent({ className, align = "center", sideOffset = 6, ...props }: React.ComponentProps<typeof PopoverPrimitive.Content>) {
  return <PopoverPrimitive.Portal><PopoverPrimitive.Content align={align} sideOffset={sideOffset} className={cn("z-50 rounded-md border border-separator bg-surface-raised text-ink shadow-elevation-2 outline-none", className)} {...props} /></PopoverPrimitive.Portal>
}
