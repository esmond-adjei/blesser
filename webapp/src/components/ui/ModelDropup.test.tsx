// @vitest-environment jsdom
import { act } from "react"
import { createRoot, type Root } from "react-dom/client"
import { MemoryRouter } from "react-router-dom"
import { afterEach, beforeEach, expect, it, vi } from "vitest"
import { ModelDropup } from "./ModelDropup"

vi.mock("../../lib/providers", async importOriginal => ({
  ...await importOriginal<typeof import("../../lib/providers")>(),
  useProviderConfigs: () => ({ configs: [{ provider: "anthropic", model: "claude-sonnet-4-6", enabled: true }] }),
  useProviderCatalog: () => ({ system: { provider: "openai", model: "gpt-5.6" }, providers: [] }),
}))

Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true })
let host: HTMLDivElement
let root: Root
beforeEach(async () => {
  host = document.createElement("div")
  document.body.appendChild(host)
  root = createRoot(host)
  await act(async () => root.render(<MemoryRouter><ModelDropup value="anthropic" onChange={() => {}} /></MemoryRouter>))
})
afterEach(async () => { await act(async () => root.unmount()); host.remove() })

it("shows provider logos on the selected chip and each model option", async () => {
  expect(host.querySelector('button img[src="/providers/anthropic.svg"]')).not.toBeNull()
  await act(async () => host.querySelector("button")?.click())
  const menu = host.querySelector('[role="menu"]')
  expect(menu?.querySelector('img[src="/providers/openai.svg"]')).not.toBeNull()
  expect(menu?.querySelector('img[src="/providers/anthropic.svg"]')).not.toBeNull()
})
