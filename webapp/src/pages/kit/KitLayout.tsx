import { NavLink, Outlet } from "react-router-dom"
import { FileText, FolderKanban, MessageSquareText, UserRound } from "lucide-react"
import { cn } from "@blesser/ui"
import { PageHeader } from "../../components/layout/PageHeader"
import { KIT_PITCH } from "../../lib/kit"

const TABS = [
  { to: "/kit/profile", label: "Profile", icon: UserRound },
  { to: "/kit/projects", label: "Projects", icon: FolderKanban },
  { to: "/kit/documents", label: "Documents", icon: FileText },
  { to: "/kit/answers", label: "Answers", icon: MessageSquareText },
]

export function KitLayout() {
  return (
    <div className="space-y-6">
      <PageHeader title="Apply kit" description={KIT_PITCH} />
      <nav aria-label="Apply kit sections" className="nice-scroll -mx-4 overflow-x-auto border-b border-separator px-4 sm:mx-0 sm:px-0">
        <ul className="flex gap-1">
          {TABS.map((t) => (
            <li key={t.to}>
              <NavLink
                to={t.to}
                className={({ isActive }) =>
                  cn(
                    "relative flex h-10 items-center gap-2 rounded-t-sm px-2.5 text-callout whitespace-nowrap transition-colors duration-160 [&_svg]:size-4",
                    "focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-focus",
                    isActive
                      ? "font-semibold text-ink after:absolute after:inset-x-2 after:-bottom-px after:h-0.5 after:rounded-full after:bg-forest"
                      : "font-medium text-ink-secondary hover:text-ink",
                  )
                }
              >
                <t.icon strokeWidth={1.75} aria-hidden="true" className="max-[400px]:hidden" />
                {t.label}
              </NavLink>
            </li>
          ))}
        </ul>
      </nav>
      <Outlet />
    </div>
  )
}
