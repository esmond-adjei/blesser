/* eslint-disable react/only-export-components -- dialog + URL hook ship together */
import * as React from "react"
import { ErrorBoundary } from "../feedback/ErrorBoundary"
import { apiAssetUrl, identityName } from "../../lib/format"
import { useSearchParams } from "react-router-dom"
import { BarChart3, Bell, Bot, Cpu, Search, SlidersHorizontal, Workflow } from "lucide-react"
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "../ui/dialog"
import { SkeletonStack } from "../ui/feedback"
import { Avatar } from "../ui/avatar"
import { useAuth } from "../../lib/auth"
import { cn } from "../../lib/utils"

// Panels load on demand; opening the dialog only fetches the shell.
const ProfilePanel = React.lazy(() =>
  import("../settings/ProfilePanel").then((m) => ({ default: m.ProfilePanel })),
)
const PreferencesPanel = React.lazy(() =>
  import("../settings/PreferencesPanel").then((m) => ({ default: m.PreferencesPanel })),
)
const DataProviderPanel = React.lazy(() =>
  import("../settings/PreferencesPanel").then((m) => ({ default: m.DataProviderPanel })),
)
const NotificationsPanel = React.lazy(() =>
  import("../settings/NotificationsPanel").then((m) => ({ default: m.NotificationsPanel })),
)
const ModelsPanel = React.lazy(() =>
  import("../settings/ModelsPanel").then((m) => ({ default: m.ModelsPanel })),
)
const FlowsPanel = React.lazy(() =>
  import("../settings/FlowsPanel").then((m) => ({ default: m.FlowsPanel })),
)
const UsagePanel = React.lazy(() =>
  import("../settings/UsagePanel").then((m) => ({ default: m.UsagePanel })),
)
const AgentsPanel = React.lazy(() =>
  import("../settings/AgentsPanel").then((m) => ({ default: m.AgentsPanel })),
)

export type SettingsTabId = "profile" | "preferences" | "data-providers" | "notifications" | "models" | "agents" | "flows" | "usage"

const TABS: {
  id: SettingsTabId
  label: string
  keywords: string
  group: "Account" | "Workspace"
  Icon: typeof SlidersHorizontal
  /** Reached via its own entry point (the account row), not the nav list. */
  navHidden?: boolean
}[] = [
  { id: "preferences", label: "Preferences", keywords: "preferences appearance theme dark light system", group: "Account", Icon: SlidersHorizontal },
  { id: "data-providers", label: "Data & AI providers", keywords: "data providers ai search embeddings openai anthropic ollama", group: "Account", Icon: Cpu, navHidden: false },
  { id: "notifications", label: "Notifications", keywords: "notifications push email digest reminders deadlines quiet hours inbox alerts", group: "Account", Icon: Bell },
  { id: "models", label: "Models", keywords: "models provider openai anthropic ollama key base url", group: "Workspace", Icon: Cpu },
  { id: "agents", label: "Agents & tools", keywords: "agents tools tasks worker assistant allowlist switches", group: "Workspace", Icon: Bot },
  { id: "flows", label: "Flows", keywords: "flows pipeline steps custom workflow instructions research", group: "Workspace", Icon: Workflow },
  { id: "usage", label: "Usage", keywords: "usage tokens calls cost metering consumption billing", group: "Workspace", Icon: BarChart3 },
]

function PanelFallback() {
  return <SkeletonStack className="space-y-3" aria-label="Loading settings" blocks={["h-7 w-40", "h-4 w-full", "h-32", "h-32"]} />
}

function SettingsDialog({  open,
  onOpenChange,
  initialTab = "preferences",
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  initialTab?: SettingsTabId
}) {
  const { user } = useAuth()
  const [active, setActive] = React.useState<SettingsTabId>(initialTab)
  const [query, setQuery] = React.useState("")
  const close = () => onOpenChange(false)

  React.useEffect(() => {
    if (open) {
      setActive(initialTab)
      setQuery("")
    }
  }, [open, initialTab])

  const q = query.trim().toLowerCase()
  const visible = TABS.filter((t) => !t.navHidden)
  const filtered = q
    ? visible.filter(
        (t) => t.label.toLowerCase().includes(q) || t.keywords.includes(q),
      )
    : visible

  // RequireAuth guarantees a session before settings can open; the
  // fallback only covers the boot frame.
  const displayName = identityName(user) || "Signing in…"

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        onClose={close}
        className="h-[82dvh] max-w-6xl"
      >
        <DialogHeader className="border-b border-separator pb-4">
          <DialogTitle>Settings</DialogTitle>
          <DialogDescription>Account, models and workspace preferences.</DialogDescription>
        </DialogHeader>

        <div className="flex min-h-0 flex-1 flex-col sm:flex-row">
          <aside className="flex max-h-[42%] w-full shrink-0 flex-col border-b border-border bg-(--app-main) sm:h-full sm:max-h-none sm:w-60 sm:border-b-0 sm:border-r">
            <div className="p-2 pt-3">
              <label className="flex items-center gap-2 rounded-md border border-input bg-background px-2.5 py-1.5 focus-within:ring-2 focus-within:ring-ring">
                <Search className="size-3.5 shrink-0 text-muted-foreground" />
                <input
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="Search settings"
                  aria-label="Search settings"
                  className="w-full bg-transparent text-sm outline-none placeholder:text-muted-foreground"
                />
              </label>
            </div>

            <nav aria-label="Settings sections" className="nice-scroll min-h-0 flex-1 space-y-1 overflow-y-auto px-2 pb-3">
              <p className="px-2 pb-1 pt-2 text-xs font-medium text-muted-foreground">Account</p>
              <button
                type="button"
                role="tab"
                aria-selected={active === "profile"}
                aria-label="Profile settings"
                data-tooltip="Profile settings"
                onClick={() => setActive("profile")}
                className={cn(
                  "flex w-full cursor-pointer items-center gap-2 rounded-md px-2 py-1.5 text-left text-sm transition-colors",
                  active === "profile"
                    ? "bg-accent font-medium text-accent-foreground"
                    : "text-muted-foreground hover:bg-accent/60 hover:text-accent-foreground",
                )}
              >
                <Avatar name={displayName} src={apiAssetUrl(user?.avatar_url)} size="sm" className="size-5 text-xs" />
                <span className="min-w-0 flex-1 truncate">{displayName}</span>
              </button>
              {filtered
                .filter((t) => t.group === "Account")
                .map((t) => (
                  <button
                    key={t.id}
                    type="button"
                    role="tab"
                    aria-selected={active === t.id}
                    onClick={() => setActive(t.id)}
                    className={cn(
                      "flex w-full cursor-pointer items-center gap-2.5 rounded-md px-2 py-1.5 text-left text-sm transition-colors",
                      active === t.id
                        ? "bg-accent font-medium text-accent-foreground"
                        : "text-muted-foreground hover:bg-accent/60 hover:text-accent-foreground",
                    )}
                  >
                    <t.Icon className="size-4 shrink-0" />
                    {t.label}
                  </button>
                ))}

              {(filtered.some((t) => t.group === "Workspace") || !q) && (
                <p className="px-2 pb-1 pt-3 text-xs font-medium text-muted-foreground">Workspace</p>
              )}
              {filtered
                .filter((t) => t.group === "Workspace")
                .map((t) => (
                  <button
                    key={t.id}
                    type="button"
                    role="tab"
                    aria-selected={active === t.id}
                    onClick={() => setActive(t.id)}
                    className={cn(
                      "flex w-full cursor-pointer items-center gap-2.5 rounded-md px-2 py-1.5 text-left text-sm transition-colors",
                      active === t.id
                        ? "bg-accent font-medium text-accent-foreground"
                        : "text-muted-foreground hover:bg-accent/60 hover:text-accent-foreground",
                    )}
                  >
                    <t.Icon className="size-4 shrink-0" />
                    {t.label}
                  </button>
                ))}

              {q && filtered.length === 0 && (
                <p className="px-2 py-4 type-caption">
                  No settings match “{query.trim()}”.
                </p>
              )}
            </nav>
          </aside>

          <section
            role="tabpanel"
            aria-label={TABS.find((t) => t.id === active)?.label ?? "Settings"}
            className="nice-scroll min-h-0 flex-1 overflow-y-auto"
          >
            <div className="mx-auto w-full max-w-2xl px-6 py-6 sm:px-10 sm:py-8">
              <ErrorBoundary resetKey={active}>
              <React.Suspense fallback={<PanelFallback />}>
                {active === "profile" && <ProfilePanel onRequestClose={close} />}
                {active === "preferences" && <PreferencesPanel />}
                {active === "data-providers" && <DataProviderPanel />}
                {active === "notifications" && <NotificationsPanel />}
                {active === "models" && <ModelsPanel />}
                {active === "agents" && <AgentsPanel />}
                {active === "flows" && <FlowsPanel />}
                {active === "usage" && <UsagePanel />}
              </React.Suspense>
              </ErrorBoundary>
            </div>
          </section>
        </div>
      </DialogContent>
    </Dialog>
  )
}

const SETTINGS_PARAM = "settings"
const VALID_TABS: SettingsTabId[] = ["profile", "preferences", "data-providers", "notifications", "models", "agents", "flows", "usage"]

function parseSettingsTab(value: string | null): SettingsTabId | null {
  return VALID_TABS.includes(value as SettingsTabId) ? (value as SettingsTabId) : null
}

/** URL-driven (?settings=models) so the Gradis entry, sidebar menu and pasted links open the same modal. */
export function useSettingsParam(): [SettingsTabId | null, (tab: SettingsTabId | null) => void] {
  const [params, setParams] = useSearchParams()
  const tab = parseSettingsTab(params.get(SETTINGS_PARAM))
  const setTab = React.useCallback(
    (next: SettingsTabId | null) => {
      setParams(
        (prev) => {
          const copy = new URLSearchParams(prev)
          if (next) copy.set(SETTINGS_PARAM, next)
          else copy.delete(SETTINGS_PARAM)
          return copy
        },
        { preventScrollReset: true },
      )
    },
    [setParams],
  )
  return [tab, setTab]
}

/** Mount once in the app shell; opened via URL. */
export function GlobalSettingsDialog() {
  const [tab, setTab] = useSettingsParam()
  return (
    <SettingsDialog
      open={tab !== null}
      onOpenChange={(open) => {
        if (!open) setTab(null)
      }}
      initialTab={tab ?? "preferences"}
    />
  )
}
