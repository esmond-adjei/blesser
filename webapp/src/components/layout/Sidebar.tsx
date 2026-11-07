import * as React from "react"
import { Link, NavLink, useNavigate, useParams } from "react-router-dom"
import {
  ContactRound,
  FileText,
  GraduationCap,
  Landmark,
  Users,
  Mail,
  Plus,
  MessageCircle,
  ArrowUpRight,
} from "lucide-react"
import { useOpenTransition } from "../../lib/transition"
import { usePaneWidth } from "../../lib/paneWidth"
import { Button } from "../ui/button"
import { cn } from "../../lib/utils"
import { SidebarListings } from "./SidebarListings"
import { GlobalSearch } from "../filters/GlobalSearch"
import { AppLogo } from "./AppLogo"
import { AccountMenu } from "./AccountMenu"
import { SidebarToggle, useSidebar } from "./SidebarContext"
import { useGradis } from "../gradis/GradisProvider"

const NAV = [
  { to: "/chat", label: "Gradis", description: "Chat with Gradis about your graduate school search", icon: MessageCircle, end: false, workspace: false },
  { to: "/schools", label: "Schools", description: "Browse saved schools and their programmes", icon: Landmark, end: false, workspace: false },
  { to: "/professors", label: "Professors", description: "Browse every professor your runs have found, matched or not", icon: Users, end: false, workspace: false },

  { to: "/applications", label: "Applications", description: "Track application deadlines, requirements and progress", icon: GraduationCap, end: false, workspace: true },
  { to: "/outbox", label: "Outbox", description: "Review and copy your outreach email drafts", icon: Mail, end: false, workspace: true },
  { to: "/dossier", label: "Matches", description: "Review professors ranked by research fit", icon: ContactRound, end: false, workspace: true },
  { to: "/documents", label: "Documents", description: "Write and tailor your CVs, statements and other documents", icon: FileText, end: false, workspace: true },
]

export const SIDEBAR_NAV = NAV

/** "Gradis" opens a blank chat on every click; a streaming reply stays put. */
export function GradisNavLink({
  className,
}: {
  className: string | ((p: { isActive: boolean }) => string)
}) {
  const { activeId, newChat } = useGradis()
  const navigate = useNavigate()
  return (
    <NavLink
      to="/chat"
      end={false}
      className={className}
      onClick={(e) => {
        e.preventDefault()
        if (newChat()) navigate("/chat")
        else navigate(activeId ? `/chat/${activeId}` : "/chat")
      }}
    >
      <MessageCircle className="size-4" />
      Gradis
    </NavLink>
  )
}

const SIDEBAR_DEFAULT = 264
const SIDEBAR_MIN = 200
const SIDEBAR_MAX = 440
/** Resize-handle width (w-2.5). Lives outside the content box. */
const SIDEBAR_HANDLE_W = 10

export function Sidebar() {
  const { open } = useSidebar()
  const { runId } = useParams<{ runId?: string }>()
  const navigate = useNavigate()

  const navClass = ({ isActive }: { isActive: boolean }) => cn(
      "flex h-[34px] items-center gap-2.5 rounded-md px-2.5 text-sm font-medium transition-colors",
      isActive ? "bg-fill text-label" : "text-label-secondary hover:bg-fill-quiet hover:text-label",
    )

  const { width, setWidth } = usePaneWidth("graduator.sidebar.width", SIDEBAR_DEFAULT, SIDEBAR_MIN, SIDEBAR_MAX)
  const t = useOpenTransition(open, 200)
  const asideRef = React.useRef<HTMLElement | null>(null)
  const dragging = React.useRef(false)
  const [active, setActive] = React.useState(false)

  function onPointerDown(e: React.PointerEvent<HTMLDivElement>) {
    dragging.current = true
    setActive(true)
    e.currentTarget.setPointerCapture(e.pointerId)
  }

  function onPointerMove(e: React.PointerEvent<HTMLDivElement>) {
    if (!dragging.current || !asideRef.current) return
    setWidth(e.clientX - asideRef.current.getBoundingClientRect().left)
  }

  function endDrag() {
    dragging.current = false
    setActive(false)
  }

  function onKeyDown(e: React.KeyboardEvent<HTMLDivElement>) {
    const step = e.shiftKey ? 64 : 16
    if (e.key === "ArrowLeft") {
      e.preventDefault()
      setWidth(width - step)
    } else if (e.key === "ArrowRight") {
      e.preventDefault()
      setWidth(width + step)
    } else if (e.key === "Home") {
      e.preventDefault()
      setWidth(SIDEBAR_MIN)
    } else if (e.key === "End") {
      e.preventDefault()
      setWidth(SIDEBAR_MAX)
    }
  }

  if (!t.render) return null
  return (
    <aside
      ref={asideRef}
      style={{ width: t.shown ? width + SIDEBAR_HANDLE_W : 0 }}
      className={cn(
        "hidden h-full shrink-0 overflow-hidden motion-reduce:transition-none md:flex",
        active ? "transition-none" : "transition-all duration-200",
        t.shown ? "opacity-100" : "opacity-0",
      )}
    >
      <div style={{ width }} className="h-full shrink-0 bg-sidebar">
        <div className="flex h-full min-w-0 flex-col">
          <div className="flex items-center gap-2.5 px-4 py-2">
            <Link to="/new" className="flex min-w-0 flex-1 items-center gap-2.5 rounded-md">
              <AppLogo className="size-7"/>
              <span className="block text-[17px] leading-[22px] font-semibold tracking-[-0.02em] text-label">Graduator</span>
            </Link>
            <SidebarToggle />
          </div>

          <div className="mt-2 mb-0.5 space-y-2 px-3">
            <Button data-tooltip="Find programmes and supervisors for your research interests" className="w-full rounded-full" onClick={() => navigate("/new")}>
              <Plus /> New run
            </Button>
            <GlobalSearch />
          </div>

          <div className="flex flex-1 flex-col gap-2 nice-scroll overflow-y-auto">
            <nav aria-label="App" className="space-y-0.5 px-3 pb-3">
              {NAV.filter(item => item.workspace === false).map((item) =>
                item.to === "/chat" ? (
                  <GradisNavLink key={item.to} className={navClass} />
                ) :
                 (
                  <NavLink key={item.to} to={item.to} end={item.end} className={navClass}>
                    <item.icon className="size-4" />
                    {item.label}
                  </NavLink>
                ),
              )}
            </nav>

            <div>
              <p className="mx-[22px] mt-2 mb-1 text-xs font-semibold text-label-tertiary">WORKSPACE</p>
              <nav aria-label="Workspace" className="space-y-0.5 px-3 pb-2">
                {NAV.filter(item => item.workspace === true).map(item =>
                  item.to === "/documents" ? (
                    <NavLink
                      key={item.to}
                      to={item.to}
                      target="_blank" rel="noopener noreferrer"
                      className={navClass}
                    >
                      <item.icon className="size-4" />
                      {item.label}
                      <ArrowUpRight className="ml-auto text-muted-foreground/50 size-4"/>
                    </NavLink>
                ) : (
                  <NavLink
                    key={item.to} to={item.to}
                    className={navClass}
                  >
                    <item.icon className="size-4" />
                      {item.label}
                    </NavLink>
                ))}
                </nav>
              <SidebarListings activeRunId={runId ?? null} /></div>
          </div>
          <AccountMenu />
        </div>
      </div>
      <div
        role="separator"
        aria-orientation="vertical"
        aria-label="Resize sidebar"
        aria-valuemin={SIDEBAR_MIN}
        aria-valuemax={SIDEBAR_MAX}
        aria-valuenow={Math.round(width)}
        tabIndex={0}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={endDrag}
        onPointerCancel={endDrag}
        onKeyDown={onKeyDown}
        onDoubleClick={() => setWidth(SIDEBAR_DEFAULT)}
        className="group flex w-2.5 shrink-0 cursor-col-resize touch-none items-center justify-center focus:outline-none bg-transparent border-l border-sidebar-border"
      >
        <span
          className={cn(
            "h-10 w-1 rounded-full transition-colors",
            active ? "bg-ring" : "bg-transparent group-hover:bg-ring group-focus-visible:bg-ring",
          )}
        />
      </div>
    </aside>
  )
}
