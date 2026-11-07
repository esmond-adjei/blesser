import * as React from "react"
import { Link, NavLink, Outlet, useLocation, useNavigate } from "react-router-dom"
import { Bell, ClipboardList, ListTodo, LogOut, Radar, Settings, Sparkles } from "lucide-react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import * as api from "../../lib/api"
import { useAuth } from "../../lib/auth"
import { browserTimezone } from "../../lib/push"
import { formatAgo, identityName } from "../../lib/format"
import { cn } from "../../lib/utils"
import { ErrorBoundary } from "../feedback/ErrorBoundary"
import { LoadingScreen } from "../feedback/LoadingScreen"
import { AppLogo } from "./AppLogo"

const NAV = [
  { to: "/opportunities", label: "Opportunities", icon: Sparkles },
  { to: "/applications", label: "Applications", icon: ClipboardList },
  { to: "/todos", label: "To-dos", icon: ListTodo },
  { to: "/scans", label: "Scans", icon: Radar },
]

const TITLES: Record<string, string> = {
  "/opportunities": "Opportunities",
  "/applications": "Applications",
  "/todos": "To-dos",
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
    "flex h-9 items-center gap-2.5 rounded-md px-2.5 text-sm font-medium transition-colors",
    isActive ? "bg-fill text-label" : "text-label-secondary hover:bg-fill-quiet hover:text-label",
  )

export function Shell() {
  useDocumentTitle()
  const { user, signOut } = useAuth()
  const navigate = useNavigate()
  return (
    <div className="flex h-dvh flex-col bg-background md:flex-row">
      <aside className="hidden w-60 shrink-0 flex-col border-r border-sidebar-border bg-sidebar md:flex">
        <Link to="/opportunities" className="flex items-center gap-2.5 px-4 py-4">
          <AppLogo className="size-7" />
          <span className="text-[17px] font-semibold tracking-[-0.02em] text-label">Blesser</span>
        </Link>
        <nav aria-label="App" className="flex-1 space-y-0.5 px-3">
          {NAV.map((item) => (
            <NavLink key={item.to} to={item.to} className={navClass}>
              <item.icon className="size-4" />
              {item.label}
            </NavLink>
          ))}
        </nav>
        <div className="space-y-0.5 border-t border-sidebar-border p-3">
          <NavLink to="/settings" className={navClass}>
            <Settings className="size-4" />
            Settings
          </NavLink>
          <button
            type="button"
            onClick={async () => {
              await signOut()
              navigate("/opportunities")
            }}
            className="flex h-9 w-full items-center gap-2.5 rounded-md px-2.5 text-sm font-medium text-label-secondary hover:bg-fill-quiet hover:text-label"
          >
            <LogOut className="size-4" />
            Sign out
          </button>
          <p className="truncate px-2.5 pt-1 text-xs text-label-tertiary">{identityName(user)}</p>
        </div>
      </aside>

      <div className="flex min-h-0 min-w-0 flex-1 flex-col">
        <header className="flex items-center gap-2 border-b border-border bg-surface px-3 py-2 md:px-6">
          <Link to="/opportunities" className="flex items-center gap-2 md:hidden">
            <AppLogo className="size-7" />
          </Link>
          <nav aria-label="App" className="flex items-center gap-1 md:hidden">
            {NAV.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                aria-label={item.label}
                className={({ isActive }) =>
                  cn("rounded-md p-2", isActive ? "bg-fill text-label" : "text-label-secondary")
                }
              >
                <item.icon className="size-4" />
              </NavLink>
            ))}
          </nav>
          <div className="ml-auto flex items-center gap-1">
            <NotificationBell />
            <NavLink
              to="/settings"
              aria-label="Settings"
              className={({ isActive }) =>
                cn("rounded-md p-2 md:hidden", isActive ? "bg-fill text-label" : "text-label-secondary")
              }
            >
              <Settings className="size-4" />
            </NavLink>
          </div>
        </header>
        <main className="nice-scroll min-h-0 flex-1 overflow-y-auto">
          <div className="mx-auto w-full max-w-[1080px] px-4 py-6 sm:px-6">
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

function NotificationBell() {
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
        className="relative rounded-md p-2 text-label-secondary hover:bg-fill-quiet hover:text-label"
      >
        <Bell className="size-4" />
        {unread ? (
          <span className="absolute top-1 right-1 flex size-4 items-center justify-center rounded-full bg-critical text-[10px] font-semibold text-white">
            {unread > 9 ? "9+" : unread}
          </span>
        ) : null}
      </button>
      {open ? (
        <div className="absolute right-0 z-30 mt-1 w-80 max-w-[calc(100vw-2rem)] overflow-hidden rounded-lg border border-border bg-surface-raised shadow-lg">
          <div className="flex items-center justify-between border-b border-border px-3 py-2">
            <span className="text-sm font-semibold text-label">Notifications</span>
            {unread ? (
              <button type="button" className="text-xs text-tint hover:underline" onClick={() => readAll.mutate()}>
                Mark all read
              </button>
            ) : null}
          </div>
          <ul className="max-h-96 overflow-y-auto">
            {items.length === 0 ? (
              <li className="px-3 py-6 text-center text-sm text-label-secondary">Nothing yet.</li>
            ) : (
              items.map((n) => (
                <li key={n.id}>
                  <button
                    type="button"
                    className="block w-full px-3 py-2.5 text-left hover:bg-fill-quiet"
                    onClick={async () => {
                      setOpen(false)
                      if (!n.read_at) {
                        await api.markNotificationRead(n.id).catch(() => undefined)
                        void client.invalidateQueries({ queryKey: ["notifications"] })
                      }
                      navigate(n.link)
                    }}
                  >
                    <span className={cn("block text-sm", n.read_at ? "text-label-secondary" : "font-semibold text-label")}>
                      {n.title}
                    </span>
                    <span className="block text-xs text-label-secondary">{n.body}</span>
                    <span className="block text-xs text-label-tertiary">{formatAgo(n.created_at)}</span>
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
