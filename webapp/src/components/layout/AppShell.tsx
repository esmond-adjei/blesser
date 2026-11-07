import * as React from "react"
import { Link, NavLink, Outlet, useLocation, useMatch, useNavigate, useParams } from "react-router-dom"
import { ErrorBoundary } from "../feedback/ErrorBoundary"
import { Activity, ContactRound, FileText, GraduationCap, Landmark, Menu, Plus, Send, SquareKanban, X } from "lucide-react"
import { useHealth, useReady, useRuns, useWorkers } from "../../lib/queries"
import { formatDuration, runTitle } from "../../lib/format"
import { useNow } from "../../lib/useNow"
import { Alert, AlertDescription, AlertTitle, PageSkeleton } from "../ui/feedback"
import { Badge } from "../ui/badge"
import { Button, buttonVariants } from "../ui/button"
import { cn } from "../../lib/utils"
import { Sidebar, SIDEBAR_NAV, GradisNavLink } from "./Sidebar"
import { AppLogo } from "./AppLogo"
import { GradisHost } from "../gradis/GradisHost"
import { GradisNewChatButton } from "../gradis/GradisChat"
import { GradisProvider } from "../gradis/GradisProvider"
import { GlobalSettingsDialog } from "../dialogs/SettingsDialog"
import { DetailPanelProvider, DetailPanelToggle, DetailRail, DetailPanelEmptyState, useDetailPanel } from "./DetailPanel"
import { DocumentTitle } from "./DocumentTitle"
import { SidebarProvider, SidebarToggle, useSidebar } from "./SidebarContext"
import { Breadcrumbs } from "./Breadcrumbs"
import { SidebarListings } from "./SidebarListings"
import { GlobalSearch } from "../filters/GlobalSearch"
import { useOpenTransition } from "../../lib/transition"
import { VerifyEmailBanner } from "./VerifyEmailBanner"
import { NotificationBell } from "./NotificationBell"
import { UpgradePrompt } from "../billing/UpgradePrompt"
import { useDismiss } from "../../lib/useDismiss"

/** Only visible when the sidebar is closed, so one toggle shows at a time. */
function HeaderSidebarToggle() {
  const { open } = useSidebar()
  if (open) return null
  return <SidebarToggle />
}

function HeaderDetailToggle() {
  const { panel, railVisible, setPanel, setRailVisible } = useDetailPanel()
  if (railVisible) return null
  function onOpen() {
    // Flipping visibility alone reveals nothing when no page has published a
    // panel, so publish the empty state instead (setPanel also flips visibility).
    if (panel) setRailVisible(true)
    else setPanel(<DetailPanelEmptyState key="empty" />, { title: "Details" })
  }
  return <DetailPanelToggle onClick={onOpen} />
}

function HeaderChatActions() {
  const chatPage = useMatch("/chat/*")
  return chatPage ? <GradisNewChatButton /> : null
}

function HealthDot() {
  // Liveness is the public /ready probe: the authed /health + /workers
  // reads 401 during a session lapse, which is not "api down".
  const { isError: apiDown } = useReady()
  const { data, dataUpdatedAt } = useHealth()
  const { data: workers } = useWorkers()
  const [open, setOpen] = React.useState(false)
  const etaSeconds = data?.queue?.eta_seconds ?? null
  const now = useNow(etaSeconds !== null)
  const eta = etaSeconds === null ? null : Math.max(0, etaSeconds - Math.max(0, now - dataUpdatedAt) / 1000)
  const etaLabel = eta === null ? null : eta < 30 ? "almost done" : `ETA ${formatDuration(eta)}`
  const { data: runs } = useRuns()
  // The run being viewed first: its board is the likeliest one wanted.
  const here = useMatch("/runs/:runId/*")?.params.runId
  const active = (runs ?? [])
    .filter((r) => (r.tasks?.running ?? 0) + (r.tasks?.pending ?? 0) > 0)
    .sort((a, b) => Number(b.id === here) - Number(a.id === here) || (b.tasks?.running ?? 0) - (a.tasks?.running ?? 0))
  const boxRef = React.useRef<HTMLDivElement>(null)
  const menu = useOpenTransition(open, 150)

  useDismiss(open, boxRef, () => setOpen(false))

  if (apiDown) return <Badge variant="destructive">api down</Badge>
  if (!data) return <Badge variant="secondary">...</Badge>
  const q = data.queue ?? {}
  const degraded = data.status === "degraded"
  if (q.pending === 0 && q.running === 0) return null
  const alive = (workers ?? []).filter((w) => w.alive)
  const stale = (workers ?? []).filter((w) => !w.alive)
  return (
    <div ref={boxRef} className="relative">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-haspopup="dialog"
        aria-expanded={open}
        data-tooltip="Queue and workers"
        className="cursor-pointer"
      >
        <Badge className="gap-1.5 rounded-none">
          <span className={cn("size-1.5 rounded-full bg-current", !degraded && "animate-pulse")} />
          {q.pending ?? 0} pending, {q.running ?? 0} running
          {etaLabel && <span className="tabular-nums opacity-80">· {etaLabel}</span>}
        </Badge>
      </button>
      {menu.render && (
        <div
          role="dialog"
          aria-label="Queue and workers"
          className={cn(
            "absolute right-0 z-50 mt-2 w-72 rounded-lg border border-border bg-popover p-3 shadow-lg origin-top-right transition-all duration-150 motion-reduce:transition-none motion-reduce:transform-none",
            menu.shown ? "scale-100 opacity-100" : "scale-95 opacity-0",
          )}
        >
          <p className="text-xs font-semibold">
            Queue{degraded ? ", degraded" : ""}
          </p>
          <p className="type-caption">
            {q.pending ?? 0} pending, {q.running ?? 0} running
            {q.stale_running ? `, ${q.stale_running} stale` : ""}
            {q.waiting_for_openalex ? `, ${q.waiting_for_openalex} waiting for OpenAlex` : ""}
          </p>
          {eta !== null && (
            <p className="type-caption tabular-nums">
              {eta < 30 ? "Almost done" : `About ${formatDuration(eta)} left`} at the pace tasks have been finishing
              {q.waiting_for_openalex ? ", not counting those waiting for OpenAlex" : ""}.
            </p>
          )}
          {active.length > 0 && (
            <>
              <p className="mt-2 text-xs font-semibold">Task boards</p>
              <ul className="mt-1 max-h-48 space-y-0.5">
                {active.map((r) => (
                  <li key={r.id}>
                    <Link
                      to={`/runs/${r.id}?board=1`}
                      onClick={() => setOpen(false)}
                      className="-mx-1.5 flex items-center gap-2 rounded-md px-1.5 py-1 text-xs hover:bg-accent"
                    >
                      <SquareKanban aria-hidden className="size-3.5 shrink-0 text-muted-foreground" />
                      <span className="min-w-0 flex-1 truncate">{runTitle(r)}</span>
                      <span className="shrink-0 text-muted-foreground">
                        {r.tasks?.running ?? 0} running{r.tasks?.pending ? `, ${r.tasks.pending} pending` : ""}
                      </span>
                    </Link>
                  </li>
                ))}
              </ul>
            </>
          )}
          <p className="mt-2 text-xs font-semibold">
            Workers ({alive.length} alive{stale.length > 0 ? `, ${stale.length} stale` : ""})
          </p>
          {(workers ?? []).length === 0 ? (
            <p className="type-caption">No workers seen yet.</p>
          ) : (
            <ul className="mt-1 space-y-1">
              {(workers ?? []).map((w) => (
                <li key={w.worker_id} className="flex items-center gap-2 text-xs">
                  <span className={cn("size-1.5 shrink-0 rounded-full", w.alive ? "bg-positive" : "bg-muted-foreground")} />
                  <span className="min-w-0 flex-1 truncate font-mono">{w.worker_id.slice(0, 8)}</span>
                  <span className="text-muted-foreground">×{w.concurrency}</span>
                  {w.lag_seconds != null && <span className="text-muted-foreground">{Math.round(w.lag_seconds)}s lag</span>}
                  {!w.alive && <span className="text-muted-foreground">stale</span>}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  )
}

export function Layout() {
  return (
    <DetailPanelProvider>
      <SidebarProvider>
        <DocumentTitle />
        <GradisProvider>
        <div className="flex h-dvh w-full overflow-hidden bg-(--app-main) text-foreground">
          <Sidebar />
          <div className="flex min-w-0 flex-1 flex-col bg-(--app-main)">
            <MobileBar />
            {/* Above the pages' own sticky headers (z-20), so its popovers open over them. */}
            <div className="z-30 flex h-12 flex-none shrink-0 items-center gap-1 border-b border-border bg-(--app-main-material) px-3 backdrop-blur-[var(--blur-thin)] sm:px-4">
              <HeaderSidebarToggle />
              <div className="min-w-0 flex-1">
                <Breadcrumbs />
              </div>

              <HealthDot />

              <NotificationBell />
              <HeaderChatActions />
              <HeaderDetailToggle />
            </div>
            <VerifyEmailBanner />
            <MainArea />
          </div>
          <DetailRail />
          <GradisHost />
          <GlobalSettingsDialog />
          <UpgradePrompt />
        </div>
        </GradisProvider>
      </SidebarProvider>
    </DetailPanelProvider>
  )
}

export { SidebarToggle }

function MainArea() {
  const chatPage = useMatch("/chat/*")
  const newPage = useMatch("/new")
  const page = (
    <React.Suspense fallback={<PageSkeleton />}>
      <RouteBoundary>
        <Outlet />
      </RouteBoundary>
    </React.Suspense>
  )
  if (chatPage) return <main className="flex min-h-0 flex-1 flex-col overflow-hidden">{page}</main>
  if (newPage)
    return (
      <main className="nice-scroll min-h-0 flex-1 overflow-y-auto">
        <div className="flex min-h-full flex-col px-4 py-10 sm:px-6">
          <div className="m-auto w-full max-w-2xl">{page}</div>
        </div>
      </main>
    )
  // A query container (`/main`): a page can use the room beside its
  // column, as the run page's tasks outline does.
  return (
    <main className="@container/main nice-scroll min-h-0 flex-1 overflow-y-auto">
      <div className="mx-auto w-full max-w-[1080px] px-4 py-6 sm:px-6">{page}</div>
    </main>
  )
}

function MobileBar() {
  return (
    <header className="flex items-center gap-2 border-b border-sidebar-border bg-sidebar px-3 py-2 md:hidden">
      <MobileDrawer />
      <Link to="/new" className="flex items-center gap-2">
        <AppLogo className="size-8" />
        <span className="text-sm font-bold tracking-tight">Graduator</span>
      </Link>
      <nav className="ml-auto flex items-center gap-1">
        <NavLink to="/dossier" className={({ isActive }) => cn("rounded-md p-2", isActive ? "bg-sidebar-primary text-sidebar-primary-foreground" : "text-muted-foreground")}>
          <ContactRound className="size-4" />
        </NavLink>
        <NavLink to="/schools" className={({ isActive }) => cn("rounded-md p-2", isActive ? "bg-sidebar-primary text-sidebar-primary-foreground" : "text-muted-foreground")}>
          <Landmark className="size-4" />
        </NavLink>
        <NavLink to="/outbox" className={({ isActive }) => cn("rounded-md p-2", isActive ? "bg-sidebar-primary text-sidebar-primary-foreground" : "text-muted-foreground")}>
          <Send className="size-4" />
        </NavLink>
        <NavLink to="/applications" className={({ isActive }) => cn("rounded-md p-2", isActive ? "bg-sidebar-primary text-sidebar-primary-foreground" : "text-muted-foreground")}>
          <GraduationCap className="size-4" />
        </NavLink>
        <NavLink to="/documents" aria-label="Documents" className={({ isActive }) => cn("rounded-md p-2", isActive ? "bg-sidebar-primary text-sidebar-primary-foreground" : "text-muted-foreground")}>
          <FileText className="size-4" />
        </NavLink>
        <Link to="/new" className={buttonVariants({ size: "sm" }) + " ml-1"}>
          <Plus />
        </Link>
      </nav>
    </header>
  )
}

/** Closes on navigation, backdrop tap or Escape. */
function MobileDrawer() {
  const [open, setOpen] = React.useState(false)
  const { runId } = useParams<{ runId?: string }>()
  const navigate = useNavigate()
  const t = useOpenTransition(open, 200)

  React.useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false)
    }
    document.addEventListener("keydown", onKey)
    const prev = document.body.style.overflow
    document.body.style.overflow = "hidden"
    return () => {
      document.removeEventListener("keydown", onKey)
      document.body.style.overflow = prev
    }
  }, [open ])

  const navClass = ({ isActive }: { isActive: boolean }) => cn(
    "flex items-center gap-2.5 rounded-md px-3 py-2 text-sm font-medium transition-colors",
    isActive ? "bg-sidebar-accent text-sidebar-accent-foreground" : "text-muted-foreground hover:bg-sidebar-accent hover:text-sidebar-accent-foreground",
  )

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        aria-label="Open navigation"
        className="rounded-md p-2 text-muted-foreground hover:bg-sidebar-accent hover:text-sidebar-accent-foreground"
      >
        <Menu className="size-4" />
      </button>
      {t.render && (
        <div className="fixed inset-0 z-50 md:hidden">
          <div
            className={cn(
              "absolute inset-0 bg-scrim transition-opacity duration-200 motion-reduce:transition-none",
              t.shown ? "opacity-100" : "opacity-0",
            )}
            onClick={() => setOpen(false)}
          />
          <div
            role="dialog"
            aria-label="Workspace navigation"
            className={cn(
              "absolute inset-y-0 left-0 flex w-72 max-w-[85vw] flex-col bg-sidebar shadow-xl transition-transform duration-200 motion-reduce:transition-none",
              t.shown ? "translate-x-0" : "-translate-x-full",
            )}
          >
            <div className="flex items-center gap-2 px-4 py-2">
              <AppLogo className="size-8" />
              <span className="text-lg font-bold tracking-tight">Graduator</span>
              <button
                type="button"
                onClick={() => setOpen(false)}
                aria-label="Close navigation"
                className="ml-auto rounded-md p-2 text-muted-foreground hover:bg-sidebar-accent hover:text-sidebar-accent-foreground"
              >
                <X className="size-4" />
              </button>
            </div>
            <div className="space-y-2 px-3" onClick={() => setOpen(false)}>
              <Button data-tooltip="Find programmes and supervisors for your research interests" className="w-full rounded-full" onClick={() => navigate("/new")}>
                <Plus /> New run
              </Button>
            </div>
            <div className="px-3 pt-2">
              <GlobalSearch />
            </div>
            <nav className="space-y-0.5 px-3 py-3" onClick={() => setOpen(false)}>
              {SIDEBAR_NAV.map((item, index) => <React.Fragment key={item.to}>
                {(index === 0 || item.to === "/outbox") && <p className="px-3 py-2 type-group-label">{index === 0 ? "Library" : "Workspace"}</p>}
                {item.to === "/chat" ? (
                  <GradisNavLink key={item.to} className={navClass} />
                ) : (
                  <NavLink key={item.to} to={item.to} end={item.end} className={navClass}>
                    <item.icon className="size-4" />
                    {item.label}
                  </NavLink>
                )}
              </React.Fragment>)}
            </nav>
            <SidebarListings activeRunId={runId ?? null} />
          </div>
        </div>
      )}
    </>
  )
}

const HEALTH_DISMISSED_KEY = "graduator:health-dismissed"

function readDismissed(): string | null {
  try {
    return sessionStorage.getItem(HEALTH_DISMISSED_KEY)
  } catch {
    return null
  }
}

export function HealthBanner() {
  const { data } = useHealth()
  const [dismissed, setDismissed] = React.useState(readDismissed)
  if (!data || data.status !== "degraded") return null
  const q = data.queue ?? {}
  // Closing hides only this exact situation; more failures or a worker
  // stopping bring the banner back.
  const signature = `${data.no_workers ? 1 : 0}:${q.recent_error ?? 0}:${q.stale_running ?? 0}`
  if (dismissed === signature) return null
  const dismiss = () => {
    setDismissed(signature)
    try {
      sessionStorage.setItem(HEALTH_DISMISSED_KEY, signature)
    } catch {
      /* storage unavailable: closed for this page only */
    }
  }
  const waiting = (q.pending ?? 0) + (q.running ?? 0)
  // Plain language first: end users see this on every page. Details are one click away.
  const summary = data.no_workers
    ? `Research is paused: ${waiting} queued task${waiting === 1 ? " is" : "s are"} waiting for the research service to come back. Nothing is lost; work resumes where it left off.`
    : (q.recent_error ?? 0) > 0
      ? `${q.recent_error} research task${q.recent_error === 1 ? "" : "s"} failed recently. You can retry them from the run's Tasks tab.`
      : "Research is running slower than usual."
  return (
    <Alert variant="destructive" className="relative pr-10">
      <button
        type="button"
        onClick={dismiss}
        aria-label="Dismiss research notice"
        data-tooltip="Dismiss"
        className="absolute right-2 top-2 flex size-7 cursor-pointer items-center justify-center rounded-md opacity-70 hover:bg-destructive/10 hover:opacity-100"
      >
        <X className="size-4" />
      </button>
      <AlertTitle className="flex items-center gap-2">
        <Activity className="size-4" /> Research may be delayed
      </AlertTitle>
      <AlertDescription>
        <p>{summary}</p>
        <details className="mt-2 text-xs">
          <summary className="cursor-pointer select-none opacity-80">Details for the operator</summary>
          <div className="mt-1 space-y-1">
            {data.no_workers && (
              <p>
                No research worker is running. Start it (<code>make worker</code>, or the{" "}
                <code>worker</code> service in Docker).
              </p>
            )}
            {(q.stale_running ?? 0) > 0 && (
              <p>
                {q.stale_running} task(s) stuck in <code>running</code> far too long; the worker
                probably stopped.
              </p>
            )}
            {/* recent_error, not error: the latter is a lifetime count. */}
            {(q.recent_error ?? 0) > 0 && (
              <p>
                {q.recent_error} task(s) failed in the last {q.error_window_minutes ?? 60} minutes.
              </p>
            )}
            {q.last_activity_at && <p>Last task activity: {new Date(q.last_activity_at).toLocaleString()}</p>}
          </div>
        </details>
      </AlertDescription>
    </Alert>
  )
}

/** Clears itself when the user navigates. */
function RouteBoundary({ children }: { children: React.ReactNode }) {
  const { pathname } = useLocation()
  return <ErrorBoundary resetKey={pathname}>{children}</ErrorBoundary>
}
