import { renderToStaticMarkup } from "react-dom/server"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { expect, it, vi } from "vitest"
import { TaskBoard } from "./TaskBoard"

vi.mock("../../lib/queries", () => ({
  useRunBoard: () => ({ data: {}, isLoading: false, isError: false }),
  useTask: () => ({}),
  useRun: () => ({ data: { max_professors_per_program: 5, max_professors: 60 } }),
}))

it("explains why tasks wait and what the other columns mean", () => {
  const html = renderToStaticMarkup(
    <QueryClientProvider client={new QueryClient()}>
      <TaskBoard runId="r1" counts={{ deferred: 1 }} fallbackPoll={false} onViewAll={() => {}} />
    </QueryClientProvider>,
  )
  expect(html).toContain("Held until research limits allow; may remain after the run ends.")
  expect(html).toContain("Queued for a worker or waiting for a retry.")
  expect(html).toContain("Finished, including tasks with no match.")
  expect(html).toContain("at most 5 professors researched")
})
