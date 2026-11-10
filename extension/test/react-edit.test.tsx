// @vitest-environment jsdom
import * as React from "react"
import { act } from "react"
import { createRoot } from "react-dom/client"
import { afterEach, describe, expect, it } from "vitest"
import { collectFields } from "../src/content/collect"
import { writeField } from "../src/content/fill"
import { byLabel } from "./helpers"

;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true

function Controlled() {
  const [country, setCountry] = React.useState("")
  const [name, setName] = React.useState("")
  return (
    <form>
      <label htmlFor="c">Country of birth</label>
      <select id="c" value={country} onChange={(e) => setCountry(e.target.value)}>
        <option value="">Choose</option>
        <option value="GH">Ghana</option>
        <option value="CI">Côte d'Ivoire</option>
      </select>
      <label htmlFor="n">Name</label>
      <input id="n" value={name} onChange={(e) => setName(e.target.value)} />
      <output data-testid="state">{`${country}|${name}`}</output>
    </form>
  )
}

let container: HTMLDivElement | null = null
afterEach(() => {
  container?.remove()
  container = null
})

describe("edit in place on a React-controlled form", () => {
  it("reaches React state like a fill does", async () => {
    container = document.createElement("div")
    document.body.appendChild(container)
    const root = createRoot(container)
    await act(async () => root.render(<Controlled />))
    const collected = collectFields(document)
    const key = (label: string) => byLabel(collected.fields, label).key
    await act(async () => {
      writeField(collected, key("Country of birth"), "Côte d'Ivoire")
      writeField(collected, key("Name"), "Ama")
    })
    await act(async () => root.render(<Controlled />))
    expect(container.querySelector('[data-testid="state"]')!.textContent).toBe("CI|Ama")
    await act(async () => root.unmount())
  })
})
