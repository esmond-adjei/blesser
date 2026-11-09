import * as React from "react"
import { Link, NavLink, Outlet, useLocation, useNavigate } from "react-router-dom"
import { Backpack, Bell, ClipboardList, ListTodo, Radar, Sparkles } from "lucide-react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import * as api from "../../lib/api"
import { browserTimezone } from "../../lib/push"
import { formatAgo } from "../../lib/format"
import { Logo, cn } from "@blesser/ui"
import { ErrorBoundary } from "../feedback/ErrorBoundary"
import { LoadingScreen } from "../feedback/LoadingScreen"
import { AccountMenu } from "./AccountMenu"

const NAV = [
  { to: "/opportunities", label: "Opportunities", icon: Sparkles },
  { to: "/applications", label: "Applications", icon: ClipboardList },
  { to: "/todos", label: "To-dos", icon: ListTodo },
  { to: "/kit", label: "Apply kit", icon: Backpack },
  { to: "/scans", label: "Scans", icon: Radar },
]

const TITLES: Record<string, string> = {
  "/opportunities": "Opportunities",
  "/applications": "Applications",
  "/todos": "To-dos",
  "/kit": "Apply kit",
  "/scans": "Scans",
  "/settings": "Settings",
}

function useDocumentTitle() {
  const { pathname } = useLocation()
  React.useEffect(() => {
    const key = Object.keys(TITLES).find((p) => pathname === p || pathname.startsWith(`${p}/`))
    document.title = key ? `${TITLES[key]} | Blesser` : "Blesser"
  }, [pathname])
}

const navClass = ({ isActive }: { isActive: boolean }) =>
  cn(
    "flex h-8 items-center gap-2.5 rounded-sm px-2.5 text-callout transition-colors duration-160 [&_svg]:size-4",
    isActive ? "bg-surface-sunk font-semibold text-ink" : "font-medium text-ink-secondary hover:bg-surface-sunk hover:text-ink",
  )

const mobileNavClass = ({ isActive }: { isActive: boolean }) =>
  cn(
    "flex size-9 items-center justify-center rounded-sm [&_svg]:size-5",
    isActive ? "bg-surface-sunk text-ink" : "text-ink-tertiary hover:bg-surface-sunk hover:text-ink",
  )

export function Shell() {
  useDocumentTitle()
  return (
    <div className="flex h-dvh flex-col bg-canvas md:flex-row">
      <aside className="hidden w-56 shrink-0 flex-col border-r border-separator bg-canvas md:flex">
        <div className="flex items-center justify-between gap-2 pt-3 pr-2 pb-4 pl-4">
          <Link to="/opportunities" className="flex items-center gap-2">
            <Logo title="" className="size-6" />
            <span className="font-display text-base font-semibold tracking-[-0.01em] text-ink">Blesser</span>
          </Link>
          <NotificationBell align="left" />
        </div>
        <nav aria-label="App" className="flex-1 space-y-0.5 px-2">
          {NAV.map((item) => (
            <NavLink key={item.to} to={item.to} className={navClass}>
              <item.icon strokeWidth={1.75} />
              {item.label}
            </NavLink>
          ))}
        </nav>
        <div className="border-t border-separator p-2">
          <AccountMenu />
        </div>
      </aside>

      <div className="flex min-h-0 min-w-0 flex-1 flex-col">
        <header className="flex items-center gap-2 border-b border-separator bg-canvas px-3 py-1.5 md:hidden">
          <Link to="/opportunities" aria-label="Blesser home" className="mr-1 flex items-center md:hidden">
            <Logo title="" className="size-7" />
          </Link>
          <nav aria-label="App" className="flex items-center gap-1 md:hidden">
            {NAV.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                aria-label={item.label}
                className={mobileNavClass}
              >
                <item.icon strokeWidth={1.75} />
              </NavLink>
            ))}
          </nav>
          <div className="ml-auto flex items-center gap-1">
            <NotificationBell />
            <AccountMenu variant="compact" />
          </div>
        </header>
        <main className="nice-scroll min-h-0 flex-1 overflow-y-auto">
          <div className="mx-auto w-full max-w-content px-4 pt-5 pb-12 sm:px-8 md:pt-8">
            <React.Suspense fallback={<LoadingScreen />}>
              <ErrorBoundary>
                <Outlet />
              </ErrorBoundary>
            </React.Suspense>
          </div>
        </main>
      </div>
    </div>
  )
}

function NotificationBell({ align = "right" }: { align?: "left" | "right" }) {
  const [open, setOpen] = React.useState(false)
  const ref = React.useRef<HTMLDivElement | null>(null)
  const client = useQueryClient()
  const navigate = useNavigate()
  const inbox = useQuery({ queryKey: ["notifications"], queryFn: api.listNotifications, refetchInterval: 60_000 })
  const readAll = useMutation({
    mutationFn: api.markAllNotificationsRead,
    onSuccess: () => void client.invalidateQueries({ queryKey: ["notifications"] }),
  })

  // Reminders fire at 08:00 in the person's timezone: report it once.
  const timezone = inbox.data?.timezone
  const loaded = inbox.isSuccess
  React.useEffect(() => {
    if (!loaded || timezone) return
    void api.updateNotificationPreferences({ timezone: browserTimezone() }).catch(() => undefined)
  }, [loaded, timezone])

  React.useEffect(() => {
    if (!open) return
    const onDown = (e: PointerEvent) => {
      if (!ref.current?.contains(e.target as Node)) setOpen(false)
    }
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false)
    document.addEventListener("pointerdown", onDown)
    document.addEventListener("keydown", onKey)
    return () => {
      document.removeEventListener("pointerdown", onDown)
      document.removeEventListener("keydown", onKey)
    }
  }, [open])

  const unread = inbox.data?.unread ?? 0
  const items = inbox.data?.items ?? []
  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        aria-label={unread ? `Notifications, ${unread} unread` : "Notifications"}
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
        className="relative flex size-9 cursor-pointer items-center justify-center rounded-sm text-ink-tertiary hover:bg-surface-sunk hover:text-ink"
      >
        <Bell className="size-[18px]" strokeWidth={1.75} />
        {unread ? <span aria-hidden="true" className="absolute top-2 right-2 size-2 rounded-full bg-bloom ring-2 ring-canvas" /> : null}
      </button>
      {open ? (
        <div className={cn("absolute z-30 mt-1 w-80", align === "left" ? "left-0" : "right-0", "max-w-[calc(100vw-2rem)] overflow-hidden rounded-md border border-separator bg-surface-raised shadow-elevation-2")}>
          <div className="flex items-center justify-between border-b border-separator px-3 py-2">
            <span className="text-headline text-ink">Notifications</span>
            {unread ? (
              <button type="button" className="cursor-pointer text-footnote font-semibold text-link hover:underline" onClick={() => readAll.mutate()}>
                Mark all read
              </button>
            ) : null}
          </div>
          <ul className="max-h-96 overflow-y-auto">
            {items.length === 0 ? (
              <li className="px-3 py-6 text-center text-sm text-ink-secondary">Nothing yet.</li>
            ) : (
              items.map((n) => (
                <li key={n.id}>
                  <button
                    type="button"
                    className="block w-full px-3 py-2.5 text-left hover:bg-surface-sunk"
                    onClick={async () => {
                      setOpen(false)
                      if (!n.read_at) {
                        await api.markNotificationRead(n.id).catch(() => undefined)
                        void client.invalidateQueries({ queryKey: ["notifications"] })
                      }
                      navigate(n.link)
                    }}
                  >
                    <span className={cn("block text-sm", n.read_at ? "text-ink-secondary" : "font-semibold text-ink")}>
                      {n.title}
                    </span>
                    <span className="block text-xs text-ink-secondary">{n.body}</span>
                    <span className="block text-xs text-ink-tertiary">{formatAgo(n.created_at)}</span>
                  </button>
                </li>
              ))
            )}
          </ul>
        </div>
      ) : null}
    </div>
  )
}
