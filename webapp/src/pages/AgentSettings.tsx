import { HealthBanner } from "../components/layout/AppShell"
import { AgentsPanel } from "../components/settings/AgentsPanel"

/** Full-page route; the settings modal renders the same panel. */
export function AgentSettings() {
  return (
    <div className="mx-auto w-full max-w-4xl space-y-6 px-4 py-6 sm:px-6">
      <HealthBanner />
      <AgentsPanel />
    </div>
  )
}
