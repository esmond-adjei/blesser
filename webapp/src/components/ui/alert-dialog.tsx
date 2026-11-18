import * as React from "react"
import { AlertDialog as AlertDialogPrimitive } from "radix-ui"
import { cn } from "@blesser/ui"

export const AlertDialog = AlertDialogPrimitive.Root
export const AlertDialogTitle = AlertDialogPrimitive.Title
export const AlertDialogDescription = AlertDialogPrimitive.Description
export function AlertDialogContent({ className, ...props }: React.ComponentProps<typeof AlertDialogPrimitive.Content>) {
  return <AlertDialogPrimitive.Portal>
    <AlertDialogPrimitive.Overlay className="bl-scrim fixed inset-0 z-50 bg-scrim" />
    <AlertDialogPrimitive.Content className={cn("bl-modal fixed top-[12dvh] left-1/2 z-50 flex max-h-[calc(88dvh-1rem)] w-[calc(100%-2rem)] max-w-lg -translate-x-1/2 flex-col overflow-hidden rounded-lg bg-surface-raised text-ink shadow-elevation-3 focus:outline-none", className)} {...props} />
  </AlertDialogPrimitive.Portal>
}
