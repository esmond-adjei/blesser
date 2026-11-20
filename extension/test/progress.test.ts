import { describe, expect, it, vi } from "vitest"
import { Actions } from "../src/background/actions"
import type { Api } from "../src/background/api"
import type { Scripting } from "../src/background/fill"
import { cleanProgress, exportForm, startProgress, type FormScripting } from "../src/background/progress"
import { Store, type Area } from "../src/background/store"
import { collectFields } from "../src/content/collect"
import { exportOf, frameSection, progressOf, trackProgress } from "../src/content/progress"
import { countProgress } from "../src/shared/progress"
import type { ExportField, ProgressField } from "../src/shared/types"
import { loadFixture } from "./helpers"

function memory(): Area {
  const data: Record<string, unknown> = {}
  return {
    get: async (key) => (key in data ? { [key]: structuredClone(data[key]) } : {}),
    set: async (items) => void Object.assign(data, structuredClone(items)),
    remove: async (keys) => void [keys].flat().forEach((k) => delete data[k]),
  }
}

const type = (el: HTMLInputElement | HTMLTextAreaElement, value: string) => {
  el.value = value
  el.dispatchEvent(new el.ownerDocument.defaultView!.Event("input", { bubbles: true }))
}

const filledLabels = (fields: ProgressField[]) => fields.filter((f) => f.filled).map((f) => f.label)

describe("progressOf", () => {
  it("counts the fields that hold an answer, by kind", () => {
    const doc = loadFixture("plain-grant.html")
    const fresh = progressOf(collectFields(doc))
    expect(fresh.map((f) => f.label)).toEqual([
      "Applicant name",
      "Date of birth (DD/MM/YYYY)",
      "Phone number",
      "Project title",
      "What will the grant pay for? (up to 100 words)",
      "Is the project led by women?",
    ])
    expect(filledLabels(fresh)).toEqual([])

    ;(doc.querySelector('[name="applicant_name"]') as HTMLInputElement).value = "Ama"
    ;(doc.querySelector('[name="use_of_funds"]') as HTMLTextAreaElement).value = "Two cold rooms"
    ;(doc.querySelector("#wl-no") as HTMLInputElement).checked = true
    ;(doc.querySelector('[name="title"]') as HTMLInputElement).value = "   "
    const after = progressOf(collectFields(doc))
    expect(filledLabels(after)).toEqual(["Applicant name", "What will the grant pay for? (up to 100 words)", "Is the project led by women?"])
    expect(after.find((f) => f.label === "Applicant name")?.section).toBe("Applicant")
  })

  it("treats an unticked single checkbox as unanswered and reads ARIA widgets", () => {
    const doc = loadFixture("google-forms.html")
    const count = () => filledLabels(progressOf(collectFields(doc)))
    expect(count()).toEqual([])
    doc.querySelector('[role="radio"][data-value="Prototype"]')!.setAttribute("aria-checked", "true")
    doc.querySelector('[role="checkbox"][aria-label="Health"]')!.setAttribute("aria-checked", "true")
    expect(count()).toEqual(["Stage of your venture", "Sectors"])
    const options = doc.querySelectorAll('[role="listbox"] [role="option"]')
    options[0].setAttribute("aria-selected", "false")
    options[1].setAttribute("aria-selected", "true")
    expect(count()).toContain("Country")
  })

  it("only counts a ticked single checkbox", () => {
    const doc = loadFixture("plain-grant.html")
    doc.querySelector("form")!.insertAdjacentHTML("beforeend", '<label><input type="checkbox" name="agree" required> I agree to the terms</label>')
    const agree = () => progressOf(collectFields(doc)).find((f) => f.label === "I agree to the terms")!
    expect(agree()).toMatchObject({ required: true, filled: false })
    ;(doc.querySelector('[name="agree"]') as HTMLInputElement).checked = true
    expect(agree().filled).toBe(true)
  })
})

describe("exportOf", () => {
  it("carries each field's answer and drops empty ones", () => {
    const doc = loadFixture("plain-grant.html")
    ;(doc.querySelector('[name="applicant_name"]') as HTMLInputElement).value = "Ama Mensah"
    ;(doc.querySelector("#wl-yes") as HTMLInputElement).checked = true
    const fields = exportOf(collectFields(doc))
    expect(fields.find((f) => f.label === "Applicant name")?.value).toBe("Ama Mensah")
    expect(fields.find((f) => f.label === "Is the project led by women?")?.value).toBe("Yes")
    expect(fields.find((f) => f.label === "Project title")?.value).toBeNull()
    expect(fields.every((f) => !("custom" in f))).toBe(true)
  })
})

describe("trackProgress", () => {
  it("reports after typing settles, and stays quiet when nothing changed", async () => {
    vi.useFakeTimers()
    try {
      const doc = loadFixture("plain-grant.html")
      const reports: ProgressField[][] = []
      const tracker = trackProgress(doc, (fields) => reports.push(fields), { delay: 50, layout: false })
      expect(filledLabels(tracker.snapshot())).toEqual([])

      const name = doc.querySelector('[name="applicant_name"]') as HTMLInputElement
      type(name, "A")
      type(name, "Am")
      await vi.advanceTimersByTimeAsync(60)
      expect(reports).toHaveLength(1)
      expect(filledLabels(reports[0])).toEqual(["Applicant name"])

      type(name, "Ama")
      await vi.advanceTimersByTimeAsync(60)
      expect(reports).toHaveLength(1)

      doc.querySelector("form")!.insertAdjacentHTML("beforeend", '<p>City</p><input name="city" type="text">')
      await vi.advanceTimersByTimeAsync(60)
      expect(reports).toHaveLength(2)
      expect(reports[1].map((f) => f.label)).toContain("City")

      tracker.stop()
      type(name, "")
      await vi.advanceTimersByTimeAsync(60)
      expect(reports).toHaveLength(2)
    } finally {
      vi.useRealTimers()
    }
  })
})

describe("background progress", () => {
  const field = (label: string, filled: boolean, section = "", required = false): ProgressField => ({ key: label, label, section, required, filled })

  it("keeps only well-formed fields from page reports", () => {
    expect(cleanProgress("nope")).toEqual([])
    expect(cleanProgress([null, 3, { key: "1", label: "Name", section: 5, required: "yes", filled: true, value: "Ama" }])).toEqual([
      { key: "1", label: "Name", section: "", required: false, filled: true },
    ])
  })

  it("counts across frames with sections in page order", () => {
    const count = countProgress({
      frames: {
        "12": [field("Referee name", true, "Referee", true)],
        "0": [field("Name", true, "About you", true), field("Email", false, "About you", true), field("Pitch", false, "Venture")],
      },
    })
    expect(count).toMatchObject({ total: 4, filled: 2, required: 3, requiredFilled: 2 })
    expect(count.sections).toEqual([
      { name: "About you", total: 2, filled: 1 },
      { name: "Venture", total: 1, filled: 0 },
      { name: "Referee", total: 1, filled: 1 },
    ])
  })

  it("starts the count in every frame, then merges each frame's updates", async () => {
    const store = new Store(memory(), memory())
    const scripting: FormScripting = {
      track: async () => [
        { frameId: 0, result: [field("Name", false)] },
        { frameId: 7, result: [field("Referee", false)] },
      ],
      snapshot: async () => [],
    }
    await startProgress(scripting, store, { id: 3, url: "https://apply.example.org/form", title: "Apply" })
    await Promise.all([store.updateProgress(3, 0, [field("Name", true)]), store.updateProgress(3, 7, [field("Referee", true)])])
    const stored = await store.progress(3)
    expect(stored?.url).toBe("https://apply.example.org/form")
    expect(countProgress(stored!)).toMatchObject({ total: 2, filled: 2 })
    await store.dropProgress(3)
    expect(await store.progress(3)).toBeUndefined()
  })

  it("stores progress reported by a frame of the page", async () => {
    const store = new Store(memory(), memory())
    const actions = new Actions({} as Api, store, {} as Scripting)
    await actions.fromPage(9, 2, { type: "blesser.progress", fields: [field("Name", true), { junk: true } as unknown as ProgressField] })
    expect((await store.progress(9))?.frames).toEqual({ "2": [field("Name", true)] })
  })

  it("refuses pages it may not read", async () => {
    const scripting: FormScripting = { track: vi.fn(), snapshot: vi.fn() }
    const store = new Store(memory(), memory())
    await expect(startProgress(scripting, store, { id: 1, url: "chrome://settings", title: "" })).rejects.toThrow(/browser pages/)
    await expect(exportForm(scripting, { id: 1, url: "", title: "" })).rejects.toThrow(/hasn't let Blesser/)
    expect(scripting.track).not.toHaveBeenCalled()
  })

  it("exports fields from every frame with frame-scoped keys and clean values", async () => {
    const base: ExportField = {
      key: "0", tag: "input", type: "text", name: "n", id: "", autocomplete: "", label: "Name", placeholder: "", help_text: "",
      section: "", options: [], required: true, max_length: null, word_limit: null, accept: "", value: "Ama",
    }
    const scripting: FormScripting = {
      track: async () => [],
      snapshot: async () => [
        { frameId: 0, result: [{ ...base, extra: "dropped" } as ExportField] },
        { frameId: 4, result: [{ ...base, label: "Sectors", type: "checkbox", value: ["Health", 3] as unknown as string[] }] },
      ],
    }
    const form = await exportForm(scripting, { id: 2, url: "https://apply.example.org/form", title: "Apply" })
    expect(form.fields.map((f) => [f.key, f.value])).toEqual([["0:0", "Ama"], ["4:0", ["Health"]]])
    expect("extra" in form.fields[0]).toBe(false)
    await expect(exportForm({ ...scripting, snapshot: async () => [{ frameId: 0, result: [] }] }, { id: 2, url: "https://a.example/", title: "" })).rejects.toThrow(
      "No form fields found on this page.",
    )
  })
})

describe("frameSection", () => {
  it("names a frame's fields after the frame, and leaves the top page alone", async () => {
    const { JSDOM } = await import("jsdom")
    const dom = new JSDOM('<iframe title="Referee" srcdoc="<p>City</p><input name=city>"></iframe>', { url: "https://apply.example.org/" })
    expect(frameSection(dom.window as unknown as Window)).toBe("")
    const frame = dom.window.document.querySelector("iframe")!.contentWindow as unknown as Window
    expect(frameSection(frame)).toBe("Referee")
    frame.document.body.innerHTML = '<p>City</p><input name="city" type="text">'
    expect(progressOf(collectFields(frame.document), frameSection(frame)).map((f) => f.section)).toEqual(["Referee"])
  })
})
