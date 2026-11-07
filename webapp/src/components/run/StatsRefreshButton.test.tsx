// @vitest-environment jsdom
import { act } from "react"
import { createRoot } from "react-dom/client"
import { expect, it, vi } from "vitest"
import { StatsRefreshButton } from "./StatsRefreshButton"

const { refreshUsage, refreshRefusals } = vi.hoisted(() => ({
  refreshUsage: vi.fn().mockResolvedValue({}),
  refreshRefusals: vi.fn().mockResolvedValue({}),
}))
vi.mock("../../lib/queries", () => ({
  useRunUsage: () => ({ isFetching: false, refetch: refreshUsage }),
  useRunRefusals: () => ({ isFetching: false, refetch: refreshRefusals }),
}))

Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true })

it("refreshes both sources displayed in the stats panel", async () => {
  const host = document.createElement("div")
  document.body.appendChild(host)
  const root = createRoot(host)
  await act(async () => root.render(<StatsRefreshButton runId="run-1" />))
  await act(async () => host.querySelector<HTMLButtonElement>('button[aria-label="Refresh stats"]')?.click())
  expect(refreshUsage).toHaveBeenCalledOnce()
  expect(refreshRefusals).toHaveBeenCalledOnce()
  await act(async () => root.unmount())
  host.remove()
})
