// @vitest-environment jsdom
import { act } from "react"
import { createRoot, type Root } from "react-dom/client"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import type { CvDocumentDetail } from "../../lib/types"
import { type NewDocument, useDocumentSync } from "./useDocumentSync"

vi.mock("../../lib/api", async (orig) => ({
  ...(await orig<typeof import("../../lib/api")>()),
  createCvFromText: vi.fn(),
  saveCvDocument: vi.fn(),
}))
const api = await import("../../lib/api")

;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true

let host: HTMLDivElement
let root: Root

beforeEach(() => {
  host = document.createElement("div")
  document.body.appendChild(host)
  root = createRoot(host)
  vi.mocked(api.createCvFromText).mockReset()
  vi.mocked(api.saveCvDocument).mockReset()
})
afterEach(() => {
  act(() => root.unmount())
  host.remove()
  localStorage.clear()
})

function created(markdown: string, title = "My CV"): CvDocumentDetail {
  return {
    id: "d1", title, kind: "cv", folder_id: "f1", word_limit: null, page_limit: null, format: "md",
    size_bytes: 0, has_original: false, revision: 1, version_count: 0, created_at: null, updated_at: null,
    versions: [], markdown,
  }
}

function open(onCreated = vi.fn()) {
  const blank: NewDocument = { documentKind: "cv", folderId: "f1", title: "My CV", markdown: "# Your Name\n", onCreated }
  const out: { current: ReturnType<typeof useDocumentSync> | null } = { current: null }
  function Probe() {
    out.current = useDocumentSync("u1", { kind: "new", blank })
    return null
  }
  act(() =>
    root.render(
      <QueryClientProvider client={new QueryClient()}>
        <Probe />
      </QueryClientProvider>,
    ),
  )
  return out
}

describe("a new document", () => {
  it("is not created until something is written in it", async () => {
    const sync = open()
    expect(sync.current?.status).toBe("new")
    await act(async () => {
      await sync.current?.flush()
    })
    act(() => root.unmount())
    root = createRoot(host)
    expect(api.createCvFromText).not.toHaveBeenCalled()
  })

  it("is created by the first edit, in its folder, then syncs to that row", async () => {
    const onCreated = vi.fn()
    vi.mocked(api.createCvFromText).mockResolvedValue(created("# Ada\n"))
    const sync = open(onCreated)
    await act(async () => {
      sync.current?.edit("# Ada\n")
      await Promise.resolve()
    })
    expect(api.createCvFromText).toHaveBeenCalledTimes(1)
    expect(api.createCvFromText).toHaveBeenCalledWith({ title: "My CV", markdown: "# Ada\n", kind: "cv", folder_id: "f1" })
    expect(onCreated).toHaveBeenCalledWith(expect.objectContaining({ id: "d1" }))
    expect(sync.current?.status).toBe("saved")

    vi.mocked(api.saveCvDocument).mockResolvedValue({ ...created("# Ada Lovelace\n"), revision: 2 })
    await act(async () => {
      sync.current?.edit("# Ada Lovelace\n")
      await sync.current?.flush()
    })
    expect(api.createCvFromText).toHaveBeenCalledTimes(1)
    expect(api.saveCvDocument).toHaveBeenCalledWith("d1", { base_revision: 1, markdown: "# Ada Lovelace\n" })
  })

  it("is created by a rename alone", async () => {
    vi.mocked(api.createCvFromText).mockResolvedValue(created("# Your Name\n", "Industry CV"))
    const sync = open()
    await act(async () => {
      sync.current?.rename("Industry CV")
      await Promise.resolve()
    })
    expect(api.createCvFromText).toHaveBeenCalledWith(expect.objectContaining({ title: "Industry CV", markdown: "# Your Name\n" }))
  })
})
