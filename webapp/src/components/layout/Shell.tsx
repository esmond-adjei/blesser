import * as React from "react"
import { Link, NavLink, Outlet, useLocation } from "react-router-dom"
import { Search } from "lucide-react"
import { useQuery } from "@tanstack/react-query"
import * as api from "../../lib/api"
import { browserTimezone } from "../../lib/push"
import { Logo, Wordmark, cn } from "@blesser/ui"
import { ErrorBoundary } from "../feedback/ErrorBoundary"
import { LoadingScreen } from "../feedback/LoadingScreen"
import { ChatSkeleton } from "../assistant/ChatSkeleton"
import { AssistantDock, AssistantDockProvider, AssistantHeaderMascot, AssistantMascot, AssistantPanel } from "../assistant/AssistantHost"
import { PageContextProvider } from "../assistant/PageContextProvider"
import { SelectionPrompt } from "../assistant/SelectionPrompt"
import { AccountMenu } from "./AccountMenu"
import { ShellHeaderContext, type ShellHeader } from "./shellHeader"
import { NAV_GROUPS } from "./nav"
import { GlobalSearch, useSearchShortcut } from "../search/GlobalSearch"
import { Sidebar, SidebarContent, SidebarFooter, SidebarGroup, SidebarGroupContent, SidebarGroupLabel, SidebarHeader, SidebarInset, SidebarMenu, SidebarMenuBadge, SidebarMenuButton, SidebarMenuItem, SidebarProvider, SidebarRail, SidebarTrigger, useSidebar } from "../ui/sidebar"

const TITLES: Record<string, string> = {
  "/opportunities": "Opportunities",
  "/applications": "Applications",
  "/calendar": "Calendar",
  "/kit": "Apply kit",
  "/scans": "Scans",
  "/assistant": "Assistant",
  "/notifications": "Notifications",
  "/settings": "Settings",
}

function useDocumentTitle() {
  const { pathname } = useLocation()
  React.useEffect(() => {
    const key = Object.keys(TITLES).find((p) => pathname === p || pathname.startsWith(`${p}/`))
    document.title = key ? `${TITLES[key]} | Blesser` : "Blesser"
  }, [pathname])
}

// Pages that manage their own scrolling, like the Assistant's pinned composer.
const FULL_BLEED = ["/assistant"]
const FULL_BLEED_EXACT = ["/scans", "/calendar", "/applications"]

export function Shell() {
  useDocumentTitle()
  const { pathname } = useLocation()
  const fullBleed = FULL_BLEED_EXACT.includes(pathname) || FULL_BLEED.some((p) => pathname === p || pathname.startsWith(`${p}/`))
  const [pageHeader, setPageHeader] = React.useState<ShellHeader | null>(null)
  return (
    <AssistantDockProvider>
    <PageContextProvider>
    <SidebarProvider defaultOpen={document.cookie.split("; ").find((entry) => entry.startsWith("sidebar_state=")) !== "sidebar_state=false"} className="h-dvh min-h-0 bg-canvas">
      <AppSidebar />
      <SidebarInset className="min-h-0 min-w-0 bg-canvas">
        <header className="flex h-14 shrink-0 items-center gap-3 border-b border-separator px-4">
          <SidebarTrigger className="md:hidden" />
          {pageHeader ? (
            <h1 className="min-w-0 truncate text-callout font-semibold text-ink">{pageHeader.title}</h1>
          ) : <ShellTitle />}
          <div className="ml-auto flex shrink-0 items-center gap-1">
            {pageHeader?.actions}
            <AssistantHeaderMascot className="sm:hidden" />
          </div>
        </header>
        <ShellHeaderContext.Provider value={setPageHeader}>
        {fullBleed ? (
          <div className="flex min-h-0 flex-1 flex-col overflow-clip">
            <React.Suspense fallback={pathname.startsWith("/assistant/") ? <ChatSkeleton /> : <LoadingScreen fill />}>
              <ErrorBoundary className="min-h-0 flex-1"><RouteFade className="flex min-h-0 flex-1 flex-col"><Outlet /></RouteFade></ErrorBoundary>
            </React.Suspense>
          </div>
        ) : (
          <div className="nice-scroll min-h-0 flex-1 overflow-y-auto">
            <div className="mx-auto flex min-h-full w-full max-w-content flex-col overflow-clip">
              <React.Suspense fallback={<LoadingScreen fill />}>
                <ErrorBoundary className="min-h-0 flex-1">
                  <RouteFade className="px-4 pt-5 pb-12 sm:px-8 md:pt-8"><Outlet /></RouteFade>
                </ErrorBoundary>
              </React.Suspense>
            </div>
          </div>
        )}
        </ShellHeaderContext.Provider>
      </SidebarInset>
      <AssistantPanel />
    </SidebarProvider>
    <AssistantMascot />
    <AssistantDock />
    <SelectionPrompt />
    </PageContextProvider>
    </AssistantDockProvider>
  )
}

/** Replays the enter animation whenever the top-level section changes. */
function RouteFade({ children, className }: { children: React.ReactNode; className?: string }) {
  const section = useLocation().pathname.split("/")[1]
  return <div key={section} className={cn("bl-enter", className)}>{children}</div>
}

function ShellTitle() {
  const { pathname } = useLocation()
  const key = Object.keys(TITLES).find((path) => pathname === path || pathname.startsWith(`${path}/`))
  return <span className="text-callout font-medium text-ink-secondary">{key ? TITLES[key] : "Blesser"}</span>
}

function useInbox() {
  const inbox = useQuery({ queryKey: ["notifications"], queryFn: api.listNotifications, refetchInterval: 60_000 })
  // Reminders fire at 08:00 in the person's timezone: report it once.
  const timezone = inbox.data?.timezone
  const loaded = inbox.isSuccess
  React.useEffect(() => {
    if (!loaded || timezone) return
    void api.updateNotificationPreferences({ timezone: browserTimezone() }).catch(() => undefined)
  }, [loaded, timezone])
  return inbox.data?.unread ?? 0
}

const ACTIVE = "data-[active=true]:bg-forest-soft/33 data-[active=true]:font-semibold data-[active=true]:text-link data-[active=true]:[&>svg]:text-link"

function AppSidebar() {
  const { state, isMobile, setOpenMobile } = useSidebar()
  const { pathname } = useLocation()
  const compact = state === "collapsed" && !isMobile
  const unread = useInbox()
  const [searching, setSearching] = React.useState(false)
  const openSearch = React.useCallback(() => { setOpenMobile(false); setSearching(true) }, [setOpenMobile])
  useSearchShortcut(openSearch)
  const mac = typeof navigator !== "undefined" && /Mac|iPhone|iPad/.test(navigator.platform)
  return (
    <Sidebar collapsible="icon" className="border-separator">
      <SidebarHeader className="h-14 flex-row items-center justify-between border-b border-separator">
        {!compact && (
          <Link to="/opportunities" aria-label="Blesser home" onClick={() => setOpenMobile(false)} className="flex min-w-0 items-center gap-1 overflow-hidden px-1.5">
            <Logo title="" className="size-7 shrink-0" />
            <Wordmark className="text-[23px]" />
          </Link>
        )}
        {compact ? (
          <div className="group/toggle relative size-7 shrink-0">
            <Logo title="" className="pointer-events-none absolute inset-0 size-7 transition-opacity group-hover/toggle:opacity-0 group-focus-within/toggle:opacity-0" />
            <SidebarTrigger className="relative opacity-0 transition-opacity group-hover/toggle:opacity-100 group-focus-within/toggle:opacity-100" />
          </div>
        ) : <SidebarTrigger className="shrink-0" />}
      </SidebarHeader>
      <SidebarContent className="gap-0 px-2 pt-3">
        <SidebarMenu className="px-0">
          <SidebarMenuItem>
            <SidebarMenuButton
              tooltip="Search"
              onClick={openSearch}
              className="border border-separator bg-surface text-ink-tertiary hover:bg-surface hover:text-ink-secondary group-data-[collapsible=icon]:border-0 group-data-[collapsible=icon]:shadow-none"
            >
              <Search strokeWidth={1.75} />
              <span className="flex-1">Search</span>
              <kbd className="rounded-[5px] px-1 font-sans text-caption text-ink-tertiary">{mac ? "⌘K" : "Ctrl K"}</kbd>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
        <nav aria-label="App">
          {NAV_GROUPS.map((group) => (
            <SidebarGroup key={group.label} className="px-0 pt-4 pb-0">
              <SidebarGroupLabel className="h-6 px-2 text-caption text-ink-tertiary">{group.label}</SidebarGroupLabel>
              <SidebarGroupContent>
                <SidebarMenu>
                  {group.items.map((item) => {
                    const count = item.to === "/notifications" ? unread : 0
                    return (
                      <SidebarMenuItem key={item.to}>
                        <SidebarMenuButton asChild tooltip={item.label} className={ACTIVE} isActive={pathname === item.to || pathname.startsWith(`${item.to}/`)}>
                          <NavLink to={item.to} onClick={() => setOpenMobile(false)} aria-label={count ? `${item.label}, ${count} unread` : item.label}>
                            <item.icon strokeWidth={1.75} /><span>{item.label}</span>
                          </NavLink>
                        </SidebarMenuButton>
                        {count ? (
                          <SidebarMenuBadge className="rounded-full bg-sun px-1.5 text-caption text-on-sun tabular-nums peer-hover/menu-button:text-on-sun peer-data-[active=true]/menu-button:text-on-sun">{count > 99 ? "99+" : count}</SidebarMenuBadge>
                        ) : null}
                      </SidebarMenuItem>
                    )
                  })}
                </SidebarMenu>
              </SidebarGroupContent>
            </SidebarGroup>
          ))}
        </nav>
      </SidebarContent>
      <SidebarFooter className="border-t border-separator">
        <AccountMenu variant={compact ? "compact" : "sidebar"} />
      </SidebarFooter>
      <SidebarRail />
      <GlobalSearch open={searching} onOpenChange={setSearching} />
    </Sidebar>
  )
}
