// @vitest-environment jsdom
import { act } from "react"
import { createRoot } from "react-dom/client"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { MemoryRouter } from "react-router-dom"
import { expect, it } from "vitest"
import { Breadcrumbs } from "./Breadcrumbs"
import { DocumentTitle } from "./DocumentTitle"

Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true })

it("shows the professor name and a link to the professor list on a professor detail page", async () => {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: Infinity } } })
  client.setQueryData(["professor", "prof-1"], { id: "prof-1", name: "Ada Lovelace" })
  const host = document.createElement("div")
  document.body.appendChild(host)
  const root = createRoot(host)
  try {
    await act(async () => root.render(
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={["/professors/prof-1"]}>
          <Breadcrumbs />
          <DocumentTitle />
        </MemoryRouter>
      </QueryClientProvider>,
    ))
    const breadcrumb = host.querySelector('nav[aria-label="Breadcrumb"]')
    expect(breadcrumb?.textContent).toContain("Professors")
    expect(breadcrumb?.textContent).toContain("Ada Lovelace")
    expect(breadcrumb?.querySelector('a[href="/professors"]')?.textContent).toBe("Professors")
    expect(document.title).toBe("Ada Lovelace | Graduator")
  } finally {
    await act(async () => root.unmount())
    client.clear()
    host.remove()
  }
})
