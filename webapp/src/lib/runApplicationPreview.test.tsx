// @vitest-environment jsdom
import { act } from "react"
import { createRoot } from "react-dom/client"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { expect, it, vi } from "vitest"
import { useRunPreviewItem } from "./queries"

vi.mock("./api", async (original) => ({
  ...await original<typeof import("./api")>(),
  listRunCandidates: vi.fn().mockResolvedValue({ items: [], total: 0 }),
  listRunDrafts: vi.fn().mockResolvedValue([]),
  listRunSchools: vi.fn().mockResolvedValue([]),
  listApplications: vi.fn().mockResolvedValue([{ id: "a1", school: "MIT", program: "PhD in CS" }]),
  getProfessor: vi.fn().mockRejectedValue(new Error("not a professor")),
}))

Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true })

function PreviewProbe() {
  const { item } = useRunPreviewItem("r1", "a1")
  return <span>{item?.kind === "application" ? `${item.applicationId}: ${item.name}` : "Loading"}</span>
}

it("resolves a saved application id into a run preview", async () => {
  const host = document.createElement("div")
  document.body.appendChild(host)
  const root = createRoot(host)
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  await act(async () => root.render(<QueryClientProvider client={client}><PreviewProbe /></QueryClientProvider>))
  for (let i = 0; i < 20 && host.textContent !== "a1: PhD in CS"; i++) {
    await act(async () => { await new Promise((resolve) => setTimeout(resolve, 10)) })
  }
  expect(host.textContent).toBe("a1: PhD in CS")
  await act(async () => root.unmount())
  client.clear()
  host.remove()
})
