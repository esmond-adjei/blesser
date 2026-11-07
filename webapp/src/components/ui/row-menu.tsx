import * as React from "react"
import { Ellipsis } from "lucide-react"
import { cn } from "../../lib/utils"
import { Menu } from "./menu"

/** "row" and "sidebar" float over a hovered row; "header" sits inline in a header. */
export type RowMenuVariant = "row" | "header" | "sidebar"

/** Overlays the row's top-right corner, so hidden controls leave the content its full width. */
export function RowOverlay({ className, children }: { className?: string; children: React.ReactNode }) {
  return (
    <div
      className={cn(
        "pointer-events-none absolute top-1 right-1 z-10 flex opacity-0 transition-opacity group-hover:pointer-events-auto group-hover:opacity-100 focus-within:pointer-events-auto focus-within:opacity-100 has-[[data-open]]:pointer-events-auto has-[[data-open]]:opacity-100",
        className,
      )}
    >
      {children}
    </div>
  )
}

const TRIGGER: Record<RowMenuVariant, string> = {
  header: "cursor-pointer rounded-sm p-1.5 text-muted-foreground transition-colors hover:bg-accent hover:text-foreground",
  sidebar:
    "flex size-7 cursor-pointer items-center justify-center rounded-sm bg-background/90 text-muted-foreground shadow-xs transition-colors hover:bg-background hover:text-foreground",
  row: "flex size-7 cursor-pointer items-center justify-center rounded-sm border border-border bg-card/95 text-muted-foreground transition-colors hover:bg-accent hover:text-foreground",
}

export function RowMenu({
  label,
  className,
  variant = "row",
  children,
}: {
  label: string
  /** Overlay position for the floating variants, e.g. ROW_MENU_POSITION. */
  className?: string
  variant?: RowMenuVariant
  children: React.ReactNode
}) {
  const menu = (
    <Menu
      label={label}
      trigger={
        <button type="button" aria-label={label} data-tooltip="More actions" className={TRIGGER[variant]}>
          <Ellipsis className="size-4" />
        </button>
      }
    >
      {children}
    </Menu>
  )
  if (variant === "header") return menu
  return <RowOverlay className={cn(variant === "row" && "top-2 right-2", className)}>{menu}</RowOverlay>
}
