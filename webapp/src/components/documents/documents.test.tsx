// @vitest-environment jsdom
import * as React from "react"
import { act } from "react"
import { createRoot, type Root } from "react-dom/client"
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { CvRedirect } from "../../pages/Documents"
import type { DocumentFolder } from "../../lib/types"
import { FolderRail } from "./FolderRail"
import { kindOf } from "./kinds"

;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true

let host: HTMLDivElement
let root: Root

beforeEach(() => {
  host = document.createElement("div")
  document.body.appendChild(host)
  root = createRoot(host)
})
afterEach(() => {
  act(() => root.unmount())
  host.remove()
})

const render = (el: React.ReactElement) => act(() => root.render(el))
const button = (label: string) =>
  [...host.querySelectorAll("button")].find((b) => b.textContent?.includes(label)) as HTMLButtonElement
const click = (el: HTMLElement) => act(() => el.dispatchEvent(new MouseEvent("click", { bubbles: true })))

function Where() {
  const loc = useLocation()
  return <p data-testid="where">{loc.pathname + loc.search}</p>
}

describe("old CV links", () => {
  it.each([
    ["/cv", "/documents"],
    ["/cv?for=c1", "/documents?for=c1"],
    ["/cv/d1?version=v1", "/documents/d1?version=v1"],
  ])("%s goes to %s", (from, to) => {
    render(
      <MemoryRouter initialEntries={[from]}>
        <Routes>
          <Route path="cv" element={<CvRedirect />} />
          <Route path="cv/:documentId" element={<CvRedirect />} />
          <Route path="documents/*" element={<Where />} />
          <Route path="documents" element={<Where />} />
        </Routes>
      </MemoryRouter>,
    )
    expect(host.querySelector("[data-testid=where]")?.textContent).toBe(to)
  })
})

describe("kinds", () => {
  it("reads an unknown kind as a CV", () => {
    expect(kindOf(undefined)).toBe("cv")
    expect(kindOf("sop")).toBe("sop")
  })
})

describe("FolderRail", () => {
  const folders: DocumentFolder[] = [
    { id: "f1", name: "MIT", sort_order: 1, document_count: 2, created_at: null, updated_at: null },
    { id: "f2", name: "Masters", sort_order: 2, document_count: 0, created_at: null, updated_at: null },
  ]
  const props = () => ({
    folders,
    total: 5,
    selected: null as string | null,
    onSelect: vi.fn(),
    onCreate: vi.fn(),
    onRename: vi.fn(),
    onMove: vi.fn(),
    onDelete: vi.fn(),
  })

  it("lists every folder, then New folder, and selects one", () => {
    const p = props()
    render(<FolderRail {...p} />)
    const names = [...host.querySelectorAll("nav li button")].map((b) => b.textContent)
    expect(names).toEqual(["MIT2", "Masters0", "New folder"])
    click(button("MIT"))
    expect(p.onSelect).toHaveBeenCalledWith("f1")
  })

  it("creates a folder from the inline name box", () => {
    const p = props()
    render(<FolderRail {...p} />)
    click(button("New folder"))
    const input = host.querySelector("input[aria-label='New folder name']") as HTMLInputElement
    act(() => {
      const set = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")?.set
      set?.call(input, "Fall 2027")
      input.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true }))
    })
    expect(p.onCreate).toHaveBeenCalledWith("Fall 2027")
  })

  it("offers the open folder's menu only on that folder", () => {
    render(<FolderRail {...props()} selected="f2" />)
    expect(host.querySelector("button[aria-label='More for Masters']")).not.toBeNull()
    expect(host.querySelector("button[aria-label='More for MIT']")).toBeNull()
  })
})
