import { JSDOM } from "jsdom"
import { describe, expect, it } from "vitest"
import { collectFields } from "../src/content/collect"
import { applyFills, readValue, writeField } from "../src/content/fill"
import { watchPage } from "../src/content/watch"
import type { PageMessage } from "../src/shared/types"
import { byLabel, loadFixture } from "./helpers"

const wait = (ms = 20) => new Promise((r) => setTimeout(r, ms))

function setup(name: string) {
  const doc = loadFixture(name)
  const collected = collectFields(doc)
  const key = (label: string) => byLabel(collected.fields, label).key
  const field = (label: string) => byLabel(collected.fields, label)
  const controls = (label: string) => collected.controls.get(key(label))!
  return { doc, collected, key, field, controls }
}

describe("writeField (edit in place)", () => {
  it("overwrites text, selects, radios and checkbox groups, firing the filler's events", () => {
    const { collected, key, field, controls } = setup("greenhouse.html")
    const first = controls("First Name")[0] as HTMLInputElement
    first.value = "Typed by member"
    const seen: string[] = []
    for (const type of ["focus", "input", "change", "blur"]) first.addEventListener(type, () => seen.push(type))
    expect(writeField(collected, key("First Name"), "Ama")).toEqual({ ok: true, reason: "", value: "Ama" })
    expect(first.value).toBe("Ama")
    expect(seen).toEqual(["focus", "input", "change", "blur"])

    const programmes = field("Which programmes interest you?")
    applyFills(collected, [{ key: programmes.key, value: ["Accelerator", "Grants"], drafted: false, file: null }])
    const result = writeField(collected, programmes.key, ["Grants"])
    expect(result.value).toEqual(["Grants"])
    expect((controls("Which programmes interest you?") as HTMLInputElement[]).filter((c) => c.checked)).toHaveLength(1)

    const work = field("Are you legally authorized to work in Ghana?")
    expect(writeField(collected, work.key, "No").value).toBe("No")
    expect(writeField(collected, work.key, "Maybe")).toMatchObject({ ok: false, reason: "None of the options matched" })
  })

  it("clears a field when the value is empty", () => {
    const { collected, key, controls } = setup("greenhouse.html")
    applyFills(collected, [{ key: key("First Name"), value: "Ama", drafted: false, file: null }])
    expect(writeField(collected, key("First Name"), null)).toEqual({ ok: true, reason: "", value: null })
    expect((controls("First Name")[0] as HTMLInputElement).value).toBe("")
  })

  it("reads selects back as option labels", () => {
    const doc = new JSDOM(
      `<form><label for="g">Gender</label><select id="g"><option value="">Choose</option><option value="m">Man</option><option value="w">Woman</option></select></form>`,
    ).window.document
    const collected = collectFields(doc)
    const k = byLabel(collected.fields, "Gender").key
    expect(writeField(collected, k, "w")).toEqual({ ok: true, reason: "", value: "Woman" })
    expect(writeField(collected, k, "Man").value).toBe("Man")
    expect(readValue(collected.controls.get(k)!, collected.fields[0])).toBe("Man")
    expect(writeField(collected, k, "")).toEqual({ ok: true, reason: "", value: null })
  })
})

describe("watchPage", () => {
  it("reports member edits to filled fields, not Blesser's own writes or untouched fields", async () => {
    const { doc, collected, key, controls } = setup("greenhouse.html")
    let member = false
    const seen: PageMessage[] = []
    const watcher = watchPage(doc, () => collected, (m) => seen.push(m), { trusted: () => member, editDelay: 5, stepDelay: 5, layout: false })
    applyFills(collected, [{ key: key("First Name"), value: "Ama", drafted: false, file: null }])
    await wait()
    expect(seen.filter((m) => m.type === "blesser.edited")).toEqual([])

    member = true
    const first = controls("First Name")[0] as HTMLInputElement
    first.value = "Ama Serwaa"
    first.dispatchEvent(new doc.defaultView!.Event("input", { bubbles: true }))
    const last = controls("Last Name")[0] as HTMLInputElement
    last.value = "Mensah"
    last.dispatchEvent(new doc.defaultView!.Event("input", { bubbles: true }))
    await wait()
    expect(seen.filter((m) => m.type === "blesser.edited")).toEqual([{ type: "blesser.edited", key: key("First Name"), value: "Ama Serwaa" }])
    watcher.stop()
  })

  it("notices a new form step once", async () => {
    const { doc, collected } = setup("plain-grant.html")
    const seen: PageMessage[] = []
    const watcher = watchPage(doc, () => collected, (m) => seen.push(m), { stepDelay: 5, layout: false })
    const step = doc.createElement("div")
    step.innerHTML = `<label for="cob">Country of birth</label><input id="cob" name="country_of_birth"><label for="pob">Place of birth</label><input id="pob" name="place_of_birth">`
    doc.querySelector("form")!.appendChild(step)
    await wait()
    expect(seen).toEqual([{ type: "blesser.step", added: 2 }])
    doc.body.appendChild(doc.createElement("p"))
    await wait()
    expect(seen).toHaveLength(1)
    watcher.stop()
  })
})
