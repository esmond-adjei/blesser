import * as React from "react"
import { createPortal } from "react-dom"
import { useQuery } from "@tanstack/react-query"
import { LogOut, Settings, User } from "lucide-react"
import { apiAssetUrl, identityName } from "../../lib/format"
import * as api from "../../lib/api"
import { useAuth } from "../../lib/auth"
import { useOpenTransition } from "../../lib/transition"
import { THEME_OPTIONS, useTheme } from "../../lib/theme"
import { cn } from "../../lib/utils"
import { Avatar } from "../ui/avatar"
import { useSettingsParam } from "../dialogs/SettingsDialog"

function ThemeMenuSection() {
  const { mode, setTheme } = useTheme()
  return (
    <div className="p-1">
      <div role="group" aria-label="Theme" className="inline-flex w-full items-center justify-center rounded-lg bg-muted p-1 text-muted-foreground">
        {THEME_OPTIONS.map(({ value, label, Icon }) => (
          <button
            key={value}
            type="button"
            role="menuitemradio"
            aria-checked={mode === value}
            aria-label={label}
            data-tooltip={label}
            onClick={() => setTheme(value)}
            className={cn(
              "inline-flex flex-1 cursor-pointer items-center justify-center gap-1.5 whitespace-nowrap rounded-md py-1 text-sm font-medium transition-all focus-visible:outline-none",
              mode === value ? "bg-card text-foreground" : "hover:text-foreground",
            )}
          >
            <Icon className="size-4" />
          </button>
        ))}
      </div>
    </div>
  )
}

type Placement = "above" | "below"

export function AccountMenu({ compact = false, placement = "above" }: { compact?: boolean; placement?: Placement }) {
  const { user, signOut } = useAuth()
  const [menuOpen, setMenuOpen] = React.useState(false)
  const [, setSettingsTab] = useSettingsParam()
  const displayName = identityName(user) || "Signing in…"
  const { data: plan } = useQuery({ queryKey: ["plan"], queryFn: api.getPlan, staleTime: 5 * 60_000, enabled: !!user })
  const menu = useOpenTransition(menuOpen, 150)
  const boxRef = React.useRef<HTMLDivElement>(null)
  const menuRef = React.useRef<HTMLDivElement | null>(null)
  const triggerRef = React.useRef<HTMLButtonElement | null>(null)
  const [menuPos, setMenuPos] = React.useState<{ left: number; top?: number; bottom?: number } | null>(null)

  const place = React.useCallback(() => {
    const trigger = triggerRef.current?.getBoundingClientRect()
    if (!trigger) return
    const width = menuRef.current?.offsetWidth ?? 256
    const left = Math.max(8, Math.min(trigger.left, window.innerWidth - width - 8))
    const next = placement === "above"
      ? { left, bottom: window.innerHeight - trigger.top + 6 }
      : { left, top: trigger.bottom + 6 }
    setMenuPos((previous) => (
      previous?.left === next.left && previous.top === next.top && previous.bottom === next.bottom
        ? previous
        : next
    ))
  }, [placement])

  React.useLayoutEffect(() => {
    if (menu.render) place()
  }, [menu.render, place])

  React.useEffect(() => {
    if (!menuOpen) return
    const onDown = (event: MouseEvent) => {
      const target = event.target
      if (target instanceof Node && (boxRef.current?.contains(target) || menuRef.current?.contains(target))) return
      setMenuOpen(false)
    }
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setMenuOpen(false)
    }
    document.addEventListener("mousedown", onDown)
    document.addEventListener("keydown", onKey)
    window.addEventListener("resize", place)
    document.addEventListener("scroll", place, true)
    return () => {
      document.removeEventListener("mousedown", onDown)
      document.removeEventListener("keydown", onKey)
      window.removeEventListener("resize", place)
      document.removeEventListener("scroll", place, true)
    }
  }, [menuOpen, place])

  function openProfile() {
    setMenuOpen(false)
    setSettingsTab("profile")
  }

  function openSettings() {
    setMenuOpen(false)
    setSettingsTab("preferences")
  }

  function signOutNow() {
    setMenuOpen(false)
    void signOut()
  }

  return (
    <div ref={boxRef} className={compact ? "relative" : "relative border-t border-sidebar-border p-2"}>
      {menu.render && createPortal(
        <div
          ref={menuRef}
          role="menu"
          style={{
            position: "fixed",
            left: menuPos?.left ?? 0,
            top: menuPos?.top,
            bottom: menuPos?.bottom,
            visibility: menuPos ? "visible" : "hidden",
          }}
          className={cn(
            "z-50 w-56 origin-bottom rounded-lg border border-border bg-popover p-1 shadow-md transition-opacity duration-150 motion-reduce:transition-none",
            placement === "below" && "origin-top",
            menu.shown ? "opacity-100" : "opacity-0",
          )}
        >
          <button type="button" role="menuitem" onClick={openProfile} className="flex w-full cursor-pointer items-center gap-2.5 rounded-md px-3 py-2 text-left text-sm hover:bg-accent">
            <User className="size-4 text-muted-foreground" /> Profile
          </button>
          <button type="button" role="menuitem" onClick={openSettings} className="flex w-full cursor-pointer items-center gap-2.5 rounded-md px-3 py-2 text-left text-sm hover:bg-accent">
            <Settings className="size-4 text-muted-foreground" /> Settings
          </button>
          <div role="separator" className="mx-1 my-1 h-px bg-border/50" />
          <ThemeMenuSection />
          <div role="separator" className="mx-1 my-1 h-px bg-border/50" />
          <button type="button" role="menuitem" onClick={signOutNow} className="flex w-full cursor-pointer items-center gap-2.5 rounded-md px-3 py-2 text-left text-sm text-critical hover:bg-critical-soft">
            <LogOut className="size-4 text-critical" /> Sign out
          </button>
        </div>,
        document.body,
      )}
      <button
        ref={triggerRef}
        type="button"
        onClick={() => setMenuOpen((open) => !open)}
        aria-label={compact ? `Account menu for ${displayName}` : undefined}
        aria-haspopup="menu"
        aria-expanded={menuOpen}
        data-tooltip={compact ? "Account" : undefined}
        className={compact
          ? "inline-flex size-10 cursor-pointer items-center justify-center rounded-full hover:bg-accent"
          : "flex w-full cursor-pointer items-center gap-2.5 rounded-lg px-2 py-1.5 text-left hover:bg-sidebar-accent"}
      >
        <Avatar name={displayName} src={apiAssetUrl(user?.avatar_url)} size="sm" />
        {!compact && (
          <span className="min-w-0 leading-tight">
            <span className="block truncate text-sm font-semibold">{displayName}</span>
            {plan && <span className="block truncate type-caption">{plan.plan.label} plan</span>}
          </span>
        )}
      </button>
    </div>
  )
}
