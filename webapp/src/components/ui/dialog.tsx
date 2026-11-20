import * as React from "react"
import { Dialog as DialogPrimitive } from "radix-ui"
import { X } from "lucide-react"
import { cn } from "@blesser/ui"

export const Dialog = DialogPrimitive.Root

export function DialogContent({ className, children, onClose }: {
  className?: string
  children: React.ReactNode
  onClose: () => void
}) {
  return (
    <DialogPrimitive.Portal>
      <DialogPrimitive.Overlay className="bl-scrim fixed inset-0 z-50 bg-scrim" />
      <DialogPrimitive.Content className={cn(
        "bl-modal fixed top-[12dvh] left-1/2 z-50 flex max-h-[calc(88dvh-1rem)] w-[calc(100%-2rem)] max-w-lg -translate-x-1/2 flex-col overflow-hidden rounded-lg max-sm:top-auto max-sm:bottom-0 max-sm:max-h-[92dvh] max-sm:w-full max-sm:max-w-none! max-sm:rounded-b-none max-sm:pb-[env(safe-area-inset-bottom)] bg-surface-raised p-0 text-ink shadow-elevation-3 focus:outline-none",
        className,
      )}>
          <button type="button" aria-label="Close" onClick={onClose} className="absolute top-4 right-4 z-20 flex size-8 cursor-pointer items-center justify-center rounded-full bg-surface-sunk text-ink-secondary transition-colors hover:bg-separator hover:text-ink focus-visible:outline-2 focus-visible:outline-focus">
            <X className="size-4" />
          </button>
        {children}
      </DialogPrimitive.Content>
    </DialogPrimitive.Portal>
  )
}

export function DialogHeader({ className, ...props }: React.ComponentProps<"div">) {
  return <div className={cn("flex shrink-0 flex-col gap-1.5 px-6 pr-14 pt-6 text-left", className)} {...props} />
}

export function DialogTitle({ className, ...props }: React.ComponentProps<typeof DialogPrimitive.Title>) {
  return <DialogPrimitive.Title className={cn("type-title-3", className)} {...props} />
}

export function DialogDescription({ className, ...props }: React.ComponentProps<typeof DialogPrimitive.Description>) {
  return <DialogPrimitive.Description className={cn("text-callout text-ink-secondary", className)} {...props} />
}

export function DialogBody({ className, ...props }: React.ComponentPropsWithRef<"div">) {
  return <div className={cn("nice-scroll min-h-0 flex-auto overflow-y-auto overscroll-contain px-6 py-5", className)} {...props} />
}

export function DialogFooter({ className, ...props }: React.ComponentProps<"div">) {
  return <div className={cn("flex shrink-0 flex-col-reverse gap-2 px-6 pt-1 pb-6 sm:flex-row sm:justify-end", className)} {...props} />
}
