import * as React from "react"
import { DropdownMenu as Menu } from "radix-ui"
import { cn } from "@blesser/ui"

export const DropdownMenu = Menu.Root
export const DropdownMenuTrigger = Menu.Trigger
export const DropdownMenuRadioGroup = Menu.RadioGroup
export function DropdownMenuContent({ className, sideOffset = 6, ...props }: React.ComponentProps<typeof Menu.Content>) {
  return <Menu.Portal><Menu.Content sideOffset={sideOffset} className={cn("bl-pop z-50 w-64 rounded-md border border-separator bg-surface-raised p-1 text-ink shadow-elevation-2 outline-none", className)} {...props} /></Menu.Portal>
}
export function DropdownMenuItem({ className, ...props }: React.ComponentProps<typeof Menu.Item>) {
  return <Menu.Item className={cn("flex h-9 cursor-pointer items-center gap-2.5 rounded-sm px-2.5 text-callout outline-none select-none focus:bg-highlight data-[disabled]:opacity-50 [&_svg]:size-4 [&_svg]:shrink-0 [&_svg]:text-ink-secondary", className)} {...props} />
}
export function DropdownMenuRadioItem({ className, ...props }: React.ComponentProps<typeof Menu.RadioItem>) {
  return <Menu.RadioItem className={cn("flex h-9 cursor-pointer items-center rounded-sm px-2.5 text-callout outline-none focus:bg-highlight", className)} {...props} />
}
export function DropdownMenuSeparator({ className, ...props }: React.ComponentProps<typeof Menu.Separator>) {
  return <Menu.Separator className={cn("mx-1 my-1 h-px bg-separator", className)} {...props} />
}
