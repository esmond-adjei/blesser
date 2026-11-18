import * as React from "react"
import { Link, NavLink, Outlet, useLocation, useNavigate } from "react-router-dom"
import { Backpack, Bell, ClipboardList, ListTodo, MessageCircle, Radar, Sparkles } from "lucide-react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import * as api from "../../lib/api"
import { browserTimezone } from "../../lib/push"
import { formatAgo } from "../../lib/format"
import { Logo, Wordmark, cn } from "@blesser/ui"
import { ErrorBoundary } from "../feedback/ErrorBoundary"
import { LoadingScreen } from "../feedback/LoadingScreen"
import { AccountMenu } from "./AccountMenu"
import { Popover, PopoverContent, PopoverTrigger } from "../ui/popover"
import { Sidebar, SidebarContent, SidebarFooter, SidebarHeader, SidebarInset, SidebarMenu, SidebarMenuButton, SidebarMenuItem, SidebarProvider, SidebarRail, SidebarTrigger, useSidebar } from "../ui/sidebar"

const NAV = [
  { to: "/opportunities", label: "Opportunities", icon: Sparkles },
  { to: "/applications", label: "Applications", icon: ClipboardList },
  { to: "/todos", label: "To-dos", icon: ListTodo },
  { to: "/kit", label: "Apply kit", icon: Backpack },
  { to: "/scans", label: "Scans", icon: Radar },
  { to: "/assistant", label: "Assistant", icon: MessageCircle },
]

const TITLES: Record<string, string> = {
  "/opportunities": "Opportunities",
  "/applications": "Applications",
  "/todos": "To-dos",
  "/kit": "Apply kit",
  "/scans": "Scans",
  "/assistant": "Assistant",
  "/settings": "Settings",
}

function useDocumentTitle() {
  const { pathname } = useLocation()
  React.useEffect(() => {
    const key = Object.keys(TITLES).find((p) => pathname === p || pathname.startsWith(`${p}/`))
    document.title = key ? `${TITLES[key]} | Blesser` : "Blesser"
  }, [pathname])
}

export function Shell() {
  useDocumentTitle()
  return (
    <SidebarProvider defaultOpen={document.cookie.split("; ").find((entry) => entry.startsWith("sidebar_state=")) !== "sidebar_state=false"} className="h-dvh min-h-0 bg-canvas">
      <AppSidebar />
      <SidebarInset className="min-h-0 min-w-0 bg-canvas">
        <header className="flex h-14 shrink-0 items-center gap-3 border-b border-separator px-4">
          <SidebarTrigger />
          <span aria-hidden="true" className="h-4 w-px bg-separator" />
          <ShellTitle />
          <div className="ml-auto"><NotificationBell /></div>
        </header>
        <div className="nice-scroll min-h-0 flex-1 overflow-y-auto">
          <div className="mx-auto w-full max-w-content px-4 pt-5 pb-12 sm:px-8 md:pt-8">
            <React.Suspense fallback={<LoadingScreen />}>
              <ErrorBoundary><RouteFade><Outlet /></RouteFade></ErrorBoundary>
            </React.Suspense>
          </div>
        </div>
      </SidebarInset>
    </SidebarProvider>
  )
}

/** Replays the enter animation whenever the top-level section changes. */
function RouteFade({ children }: { children: React.ReactNode }) {
  const section = useLocation().pathname.split("/")[1]
  return <div key={section} className="bl-enter">{children}</div>
}

function ShellTitle() {
  const { pathname } = useLocation()
  const key = Object.keys(TITLES).find((path) => pathname === path || pathname.startsWith(`${path}/`))
  return <span className="text-callout font-medium text-ink-secondary">{key ? TITLES[key] : "Blesser"}</span>
}

function AppSidebar() {
  const { state, isMobile, setOpenMobile } = useSidebar()
  const { pathname } = useLocation()
  const compact = state === "collapsed" && !isMobile
  return (
    <Sidebar collapsible="icon" className="border-separator">
      <SidebarHeader className="h-14 justify-center border-b border-separator">
        <Link to="/opportunities" aria-label="Blesser home" onClick={() => setOpenMobile(false)} className="flex items-center gap-1 overflow-hidden px-1.5">
          <Logo title="" className="size-7 shrink-0" />
          {!compact && <Wordmark className="text-[23px]" />}
        </Link>
      </SidebarHeader>
      <SidebarContent className="p-2">
        <nav aria-label="App">
          <SidebarMenu>
            {NAV.map((item) => (
              <SidebarMenuItem key={item.to}>
                <SidebarMenuButton asChild tooltip={item.label} className="data-[active=true]:bg-forest-soft data-[active=true]:text-link data-[active=true]:[&>svg]:text-link" isActive={pathname === item.to || pathname.startsWith(`${item.to}/`)}>
                  <NavLink to={item.to} onClick={() => setOpenMobile(false)} aria-label={item.label}>
                    <item.icon strokeWidth={1.75} /><span>{item.label}</span>
                  </NavLink>
                </SidebarMenuButton>
              </SidebarMenuItem>
            ))}
          </SidebarMenu>
        </nav>
      </SidebarContent>
      <SidebarFooter className="border-t border-separator">
        <AccountMenu variant={compact ? "compact" : "sidebar"} />
      </SidebarFooter>
      <SidebarRail />
    </Sidebar>
  )
}

function NotificationBell({ align = "right" }: { align?: "left" | "right" }) {
  const [open, setOpen] = React.useState(false)
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

  const unread = inbox.data?.unread ?? 0
  const items = inbox.data?.items ?? []
  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
      <button
        type="button"
        aria-label={unread ? `Notifications, ${unread} unread` : "Notifications"}
        aria-expanded={open}
        className="relative flex size-9 cursor-pointer items-center justify-center rounded-sm text-ink-tertiary hover:bg-highlight hover:text-ink"
      >
        <Bell className="size-[18px]" strokeWidth={1.75} />
        {unread ? <span aria-hidden="true" className="absolute top-2 right-2 size-2 rounded-full bg-bloom ring-2 ring-canvas" /> : null}
      </button>
      </PopoverTrigger>
        <PopoverContent align={align === "left" ? "start" : "end"} className="w-80 max-w-[calc(100vw-2rem)] overflow-hidden">
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
                    className="block w-full px-3 py-2.5 text-left hover:bg-highlight"
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
        </PopoverContent>
    </Popover>
  )
}
