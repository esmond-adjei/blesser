// @vitest-environment jsdom
import * as React from "react"
import { act } from "react"
import { createRoot } from "react-dom/client"
import { afterEach, describe, expect, it } from "vitest"
import { collectFields } from "../src/content/collect"
import { applyFills } from "../src/content/fill"
import { byLabel } from "./helpers"

;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true

const seen: { current: Record<string, unknown> } = { current: {} }

function ControlledForm() {
  const [name, setName] = React.useState("")
  const [bio, setBio] = React.useState("")
  const [country, setCountry] = React.useState("")
  const [stage, setStage] = React.useState("")
  const [agree, setAgree] = React.useState(false)
  React.useEffect(() => {
    seen.current = { name, bio, country, stage, agree }
  })
  return (
    <form onSubmit={(e) => e.preventDefault()}>
      <label htmlFor="name">Startup name</label>
      <input id="name" value={name} onChange={(e) => setName(e.target.value)} />
      <label htmlFor="bio">Short bio</label>
      <textarea id="bio" value={bio} onChange={(e) => setBio(e.target.value)} />
      <label htmlFor="country">Country</label>
      <select id="country" value={country} onChange={(e) => setCountry(e.target.value)}>
        <option value="">Choose</option>
        <option value="gh">Ghana</option>
        <option value="ke">Kenya</option>
      </select>
      <fieldset>
        <legend>Stage</legend>
        {["idea", "prototype"].map((s) => (
          <label key={s}>
            <input type="radio" name="stage" value={s} checked={stage === s} onChange={() => setStage(s)} /> {s}
          </label>
        ))}
      </fieldset>
      <label>
        <input type="checkbox" checked={agree} onChange={(e) => setAgree(e.target.checked)} /> I agree to the terms
      </label>
      <p data-testid="echo">{name}</p>
      <button type="submit">Send</button>
    </form>
  )
}

let container: HTMLDivElement | null = null
afterEach(() => {
  container?.remove()
  container = null
})

describe("React-controlled forms", () => {
  it("keep the filled values through re-renders", async () => {
    container = document.createElement("div")
    document.body.appendChild(container)
    const root = createRoot(container)
    await act(async () => root.render(<ControlledForm />))

    const collected = collectFields(document)
    const key = (label: string) => byLabel(collected.fields, label).key
    let outcomes: ReturnType<typeof applyFills> = []
    await act(async () => {
      outcomes = applyFills(collected, [
        { key: key("Startup name"), value: "Siwa", drafted: false, file: null },
        { key: key("Short bio"), value: "Solar cold rooms for market traders.", drafted: true, file: null },
        { key: key("Country"), value: "Ghana", drafted: false, file: null },
        { key: key("Stage"), value: "prototype", drafted: false, file: null },
        { key: key("I agree to the terms"), value: "true", drafted: false, file: null },
      ])
    })
    expect(outcomes.map((o) => o.status)).toEqual(["filled", "drafted", "filled", "filled", "filled"])
    expect(seen.current).toEqual({ name: "Siwa", bio: "Solar cold rooms for market traders.", country: "gh", stage: "prototype", agree: true })

    await act(async () => root.render(<ControlledForm />))
    expect((document.getElementById("name") as HTMLInputElement).value).toBe("Siwa")
    expect((document.getElementById("country") as HTMLSelectElement).value).toBe("gh")
    expect(container.querySelector('[data-testid="echo"]')!.textContent).toBe("Siwa")
    expect((container.querySelectorAll('input[type="radio"]')[1] as HTMLInputElement).checked).toBe(true)
    await act(async () => root.unmount())
  })

  it("would lose a plain property assignment, which is why fills go through the native setter", async () => {
    container = document.createElement("div")
    document.body.appendChild(container)
    const root = createRoot(container)
    await act(async () => root.render(<ControlledForm />))
    const input = document.getElementById("name") as HTMLInputElement
    await act(async () => {
      input.value = "Lost"
      input.dispatchEvent(new Event("input", { bubbles: true }))
    })
    expect(seen.current.name).toBe("")
    await act(async () => root.unmount())
  })
})
