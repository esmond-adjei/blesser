import { describe, expect, it, vi } from "vitest"
import { collectFields, type Collected } from "../src/content/collect"
import { accepts, applyFills } from "../src/content/fill"
import type { FillInstruction } from "../src/shared/types"
import { byLabel, loadFixture } from "./helpers"

const answer = (key: string, value: string | string[] | null, extra: Partial<FillInstruction> = {}): FillInstruction => ({
  key,
  value,
  drafted: false,
  file: null,
  ...extra,
})

function setup(name: string) {
  const doc = loadFixture(name)
  const collected = collectFields(doc)
  const key = (label: string) => byLabel(collected.fields, label).key
  const control = <T extends Element>(label: string) => collected.controls.get(key(label))![0] as T
  return { doc, collected, key, control }
}

function record(el: Element) {
  const seen: string[] = []
  for (const type of ["focus", "input", "change", "blur", "click"]) el.addEventListener(type, () => seen.push(type))
  return seen
}

describe("applyFills", () => {
  it("fills Greenhouse text, select and checkbox groups with input, change and blur events", () => {
    const { collected, key, control } = setup("greenhouse.html")
    const first = control<HTMLInputElement>("First Name")
    const events = record(first)
    const marked: string[] = []
    const outcomes = applyFills(
      collected,
      [
        answer(key("First Name"), "Ama"),
        answer(key("Are you legally authorized to work in Ghana?"), "Yes"),
        answer(key("Which programmes interest you?"), ["Accelerator", "Grants"]),
        answer(key("Why do you want to work with us? (300 words max)"), "Because.", { drafted: true }),
      ],
      (k, _target, drafted) => marked.push(`${k}:${drafted}`),
    )
    expect(outcomes.map((o) => o.status)).toEqual(["filled", "filled", "filled", "drafted"])
    expect(first.value).toBe("Ama")
    expect(events).toEqual(["focus", "input", "change", "blur"])
    expect(control<HTMLSelectElement>("Are you legally authorized to work in Ghana?").value).toBe("1")
    const boxes = collected.controls.get(key("Which programmes interest you?")) as HTMLInputElement[]
    expect(boxes.map((b) => b.checked)).toEqual([false, true, true])
    expect(marked).toHaveLength(4)
    expect(marked[3]).toMatch(/:true$/)
  })

  it("never clicks the submit button or submits the form", () => {
    const { doc, collected, key } = setup("greenhouse.html")
    const submit = vi.fn((e: Event) => e.preventDefault())
    doc.querySelector("form")!.addEventListener("submit", submit)
    const clicks = vi.fn()
    doc.querySelector("#submit_app")!.addEventListener("click", clicks)
    applyFills(collected, collected.fields.map((f) => answer(f.key, f.type === "checkbox" ? ["Fellowship"] : "x")))
    expect(submit).not.toHaveBeenCalled()
    expect(clicks).not.toHaveBeenCalled()
    expect(key("Email")).toBeTruthy()
  })

  it("picks Lever radios by label and leaves what the member already typed", () => {
    const { collected, key, control } = setup("lever.html")
    control<HTMLInputElement>("Email").value = "typed@me.org"
    const outcomes = applyFills(collected, [
      answer(key("Will you need visa sponsorship?"), "no"),
      answer(key("Email"), "ama@example.org"),
      answer(key("Current company"), null),
    ])
    const radios = collected.controls.get(key("Will you need visa sponsorship?")) as HTMLInputElement[]
    expect(radios.map((r) => r.checked)).toEqual([false, true])
    expect(outcomes[1]).toMatchObject({ status: "skipped", reason: "Already has your answer" })
    expect(control<HTMLInputElement>("Email").value).toBe("typed@me.org")
    expect(outcomes[2]).toMatchObject({ status: "skipped", reason: "No answer in your kit" })
  })

  it("refills its own answers on a second run", () => {
    const { collected, key, control } = setup("lever.html")
    applyFills(collected, [answer(key("Full name"), "Ama Mensah")])
    const again = applyFills(collected, [answer(key("Full name"), "Ama K. Mensah")])
    expect(again[0].status).toBe("filled")
    expect(control<HTMLInputElement>("Full name").value).toBe("Ama K. Mensah")
  })

  it("converts dates, matches country options by label, respects maxlength and ticks consent", () => {
    const { collected, key, control } = setup("workable.html")
    const long = "a".repeat(600)
    const outcomes = applyFills(collected, [
      answer(key("Date of birth"), "1998-04-07"),
      answer(key("Country"), "Ghana"),
      answer(key("Summary"), long),
      answer(key("I agree to the processing of my data"), "yes"),
    ])
    expect(outcomes.every((o) => o.status === "filled")).toBe(true)
    expect(control<HTMLInputElement>("Date of birth").value).toBe("1998-04-07")
    expect(control<HTMLSelectElement>("Country").value).toBe("GH")
    expect(control<HTMLTextAreaElement>("Summary").value).toHaveLength(500)
    expect(control<HTMLInputElement>("I agree to the processing of my data").checked).toBe(true)
  })

  it("writes rich text into contenteditable editors", () => {
    const { collected, key, control } = setup("submittable.html")
    const editor = control<HTMLElement>("Project summary")
    const events = record(editor)
    const [outcome] = applyFills(collected, [answer(key("Project summary"), "Siwa brings solar cold storage to market women.", { drafted: true })])
    expect(outcome.status).toBe("drafted")
    expect(editor.textContent).toBe("Siwa brings solar cold storage to market women.")
    expect(events).toContain("input")
  })

  it("attaches documents through DataTransfer when the input accepts them", () => {
    const { doc, collected, key, control } = setup("submittable.html")
    const view = doc.defaultView as unknown as Record<string, unknown>
    class FakeTransfer {
      list: File[] = []
      items = { add: (f: File) => this.list.push(f) }
      get files() {
        return this.list
      }
    }
    view.DataTransfer = FakeTransfer
    const input = control<HTMLInputElement>("Budget")
    let files: File[] = []
    Object.defineProperty(input, "files", { get: () => files, set: (v: File[]) => {
        files = v
      }, configurable: true })
    const changed = vi.fn()
    input.addEventListener("change", changed)
    const pdf = { name: "budget.pdf", type: "application/pdf", base64: btoa("%PDF-1.4 test") }
    const docx = { name: "budget.docx", type: "application/vnd.openxmlformats-officedocument.wordprocessingml.document", base64: btoa("x") }
    const [bad] = applyFills(collected, [answer(key("Budget"), null, { file: docx })])
    expect(bad.status).toBe("skipped")
    const [good] = applyFills(collected, [answer(key("Budget"), null, { file: pdf })])
    expect(good.status).toBe("filled")
    expect(files[0].name).toBe("budget.pdf")
    expect(changed).toHaveBeenCalledOnce()
  })

  it("refuses fields that disappeared or were never collected", () => {
    const { doc, collected } = setup("plain-grant.html")
    const outcomes = applyFills(collected, [answer("999", "secret")])
    expect(outcomes[0].status).toBe("skipped")
    expect((doc.querySelector('input[type="password"]') as HTMLInputElement).value).toBe("")
  })

  it("reports custom widgets as things to pick by hand, with the suggestion", () => {
    const { collected, key } = setup("google-forms.html")
    const [outcome] = applyFills(collected as Collected, [answer(key("Stage of your venture"), "Prototype")])
    expect(outcome).toMatchObject({ status: "skipped", reason: "Pick this one yourself. Suggested: Prototype" })
  })
})

describe("accepts", () => {
  it("checks extensions and MIME patterns", () => {
    expect(accepts("", { name: "a.pdf", type: "application/pdf" })).toBe(true)
    expect(accepts(".pdf,.doc", { name: "CV.PDF", type: "application/pdf" })).toBe(true)
    expect(accepts("image/*", { name: "logo.png", type: "image/png" })).toBe(true)
    expect(accepts("application/pdf", { name: "a.docx", type: "application/msword" })).toBe(false)
  })
})
