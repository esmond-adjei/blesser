import * as React from "react"
import { createPortal } from "react-dom"
import { useNavigate } from "react-router-dom"
import { Bell, ChevronsUpDown, Info, LogOut, Settings } from "lucide-react"
import { cn } from "@blesser/ui"
import { useAuth } from "../../lib/auth"
import { accountName, initials } from "../../lib/format"
import { menuKeyTarget } from "../../lib/menu"
import { SITE_URL } from "../../lib/site"
import { THEME_MODES, useTheme } from "../../lib/theme"
import { useOpenTransition } from "../../lib/transition"

export function Avatar({ name, className }: { name: string; className?: string }) {
  return (
    <span
      aria-hidden="true"
      className={cn(
        "grid size-8 shrink-0 place-items-center rounded-full bg-forest-soft text-[13px] font-semibold text-link select-none",
        className,
      )}
    >
      {initials(name)}
    </span>
  )
}

const itemClass =
  "flex h-9 w-full cursor-pointer items-center gap-2.5 rounded-sm px-2.5 text-left text-callout text-ink outline-none hover:bg-surface-sunk focus-visible:bg-surface-sunk [&_svg]:size-4 [&_svg]:shrink-0 [&_svg]:text-ink-secondary"

type Variant = "sidebar" | "compact"

export function AccountMenu({ variant = "sidebar" }: { variant?: Variant }) {
  const { user, signOut } = useAuth()
  const { mode, setTheme } = useTheme()
  const navigate = useNavigate()
  const [open, setOpen] = React.useState(false)
  const menu = useOpenTransition(open, 120)
  const triggerRef = React.useRef<HTMLButtonElement>(null)
  const menuRef = React.useRef<HTMLDivElement>(null)
  const focusOnOpen = React.useRef<"first" | "last" | null>(null)
  const [pos, setPos] = React.useState<React.CSSProperties | null>(null)
  const name = accountName(user)
  const compact = variant === "compact"

  const items = () => Array.from(menuRef.current?.querySelectorAll<HTMLElement>('[role^="menuitem"]') ?? [])

  const place = React.useCallback(() => {
    const t = triggerRef.current?.getBoundingClientRect()
    if (!t) return
    const width = menuRef.current?.offsetWidth ?? 256
    if (compact) {
      setPos({ top: t.bottom + 6, left: Math.max(8, Math.min(t.right - width, window.innerWidth - width - 8)) })
    } else {
      setPos({ bottom: window.innerHeight - t.top + 6, left: Math.max(8, t.left) })
    }
  }, [compact])

  React.useLayoutEffect(() => {
    if (menu.render && open) place()
  }, [menu.render, open, place])

  // Focus waits for a position: a visibility-hidden item can't take focus.
  React.useEffect(() => {
    const list = items()
    if (!open || !pos || !focusOnOpen.current || !list.length) return
    list[focusOnOpen.current === "first" ? 0 : list.length - 1].focus()
    focusOnOpen.current = null
  }, [open, pos, menu.render])

  const close = React.useCallback((restoreFocus: boolean) => {
    setOpen(false)
    if (restoreFocus) triggerRef.current?.focus()
  }, [])

  React.useEffect(() => {
    if (!open) return
    const onDown = (e: PointerEvent) => {
      const target = e.target as Node
      if (triggerRef.current?.contains(target) || menuRef.current?.contains(target)) return
      close(false)
    }
    document.addEventListener("pointerdown", onDown)
    window.addEventListener("resize", place)
    return () => {
      document.removeEventListener("pointerdown", onDown)
      window.removeEventListener("resize", place)
    }
  }, [open, place, close])

  const openWith = (where: "first" | "last") => {
    focusOnOpen.current = where
    setOpen(true)
  }

  const onMenuKey = (e: React.KeyboardEvent) => {
    if (e.key === "Escape") {
      e.preventDefault()
      close(true)
      return
    }
    if (e.key === "Tab") {
      close(false)
      return
    }
    const list = items()
    const next = menuKeyTarget(e.key, list.indexOf(document.activeElement as HTMLElement), list.length)
    if (next === null) return
    e.preventDefault()
    list[next]?.focus()
  }

  const go = (to: string) => {
    close(true)
    navigate(to)
  }

  return (
    <>
      <button
        ref={triggerRef}
        type="button"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={compact ? `Account menu for ${name}` : undefined}
        onClick={() => (open ? close(false) : openWith("first"))}
        onKeyDown={(e) => {
          if (e.key === "ArrowDown" || e.key === "ArrowUp") {
            e.preventDefault()
            openWith(e.key === "ArrowDown" ? "first" : "last")
          }
        }}
        className={cn(
          "cursor-pointer transition-colors duration-160",
          compact
            ? "grid size-9 place-items-center rounded-full hover:bg-surface-sunk"
            : "flex w-full min-w-0 items-center gap-2.5 rounded-sm px-2 py-1.5 text-left hover:bg-surface-sunk aria-expanded:bg-surface-sunk",
        )}
      >
        <Avatar name={name} className={compact ? "size-7 text-xs" : undefined} />
        {!compact ? (
          <>
            <span className="min-w-0 flex-1 truncate text-callout font-semibold text-ink">{name}</span>
            <ChevronsUpDown aria-hidden="true" className="size-4 shrink-0 text-ink-tertiary" />
          </>
        ) : null}
      </button>
      {menu.render
        ? createPortal(
            <div
              ref={menuRef}
              role="menu"
              aria-label="Account"
              onKeyDown={onMenuKey}
              style={{ position: "fixed", visibility: pos ? "visible" : "hidden", ...pos }}
              className={cn(
                "z-50 w-64 rounded-md border border-separator bg-surface-raised p-1 shadow-elevation-2 transition-[opacity,translate] duration-120 ease-out motion-reduce:transition-none",
                menu.shown ? "translate-y-0 opacity-100" : cn("opacity-0", compact ? "-translate-y-1" : "translate-y-1"),
              )}
            >
              <div className="flex items-center gap-2.5 px-2.5 pt-2 pb-2.5">
                <Avatar name={name} />
                <div className="min-w-0">
                  <p className="truncate text-callout font-semibold text-ink">{name}</p>
                  <p className="truncate text-footnote text-ink-secondary">{user?.email}</p>
                </div>
              </div>
              <Separator />
              <button type="button" role="menuitem" tabIndex={-1} className={itemClass} onClick={() => go("/settings")}>
                <Settings strokeWidth={1.75} /> Settings
              </button>
              <button type="button" role="menuitem" tabIndex={-1} className={itemClass} onClick={() => go("/settings/notifications")}>
                <Bell strokeWidth={1.75} /> Notifications
              </button>
              <div className="flex h-10 items-center justify-between gap-2 pr-1 pl-2.5">
                <span id="account-menu-theme" className="text-callout text-ink">Theme</span>
                <div role="group" aria-labelledby="account-menu-theme" className="flex items-center gap-0.5 rounded-full bg-surface-sunk p-0.5">
                  {THEME_MODES.map(({ value, label, Icon }) => {
                    const on = mode === value
                    return (
                      <button
                        key={value}
                        type="button"
                        role="menuitemradio"
                        aria-checked={on}
                        aria-label={label}
                        data-tooltip={label}
                        tabIndex={-1}
                        onClick={() => setTheme(value)}
                        className={cn(
                          "grid size-7 cursor-pointer place-items-center rounded-full outline-none transition-colors duration-160 focus-visible:ring-2 focus-visible:ring-focus",
                          on ? "bg-surface text-ink shadow-elevation-1" : "text-ink-tertiary hover:text-ink",
                        )}
                      >
                        <Icon className="size-3.5" strokeWidth={1.75} />
                      </button>
                    )
                  })}
                </div>
              </div>
              {SITE_URL ? (
                <a role="menuitem" tabIndex={-1} href={`${SITE_URL}/about`} target="_blank" rel="noopener" className={itemClass} onClick={() => close(false)}>
                  <Info strokeWidth={1.75} /> About Blesser
                </a>
              ) : null}
              <Separator />
              <button
                type="button"
                role="menuitem"
                tabIndex={-1}
                className={itemClass}
                onClick={async () => {
                  close(false)
                  await signOut()
                  navigate("/login")
                }}
              >
                <LogOut strokeWidth={1.75} /> Sign out
              </button>
            </div>,
            document.body,
          )
        : null}
    </>
  )
}

function Separator() {
  return <div role="separator" className="mx-1 my-1 h-px bg-separator" />
}
