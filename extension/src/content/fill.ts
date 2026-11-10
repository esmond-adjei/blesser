import type { AttachedFile, CollectedField, FillInstruction, FillOutcome } from "../shared/types"
import type { Collected } from "./collect"
import { isForbidden } from "./guards"
import { matchOption, normalize, truthy } from "./text"

type TextControl = HTMLInputElement | HTMLTextAreaElement
type Mark = (key: string, target: Element, drafted: boolean) => void

const ours = new WeakMap<Element, string>()

function fire(el: Element, type: string, init: EventInit = {}) {
  const view = el.ownerDocument.defaultView!
  const event =
    type === "input" ? new view.InputEvent("input", { bubbles: true, inputType: "insertText", ...init })
      : type === "focus" || type === "blur" ? new view.FocusEvent(type)
        : type === "focusin" || type === "focusout" ? new view.FocusEvent(type, { bubbles: true })
          : new view.Event(type, { bubbles: true, ...init })
  el.dispatchEvent(event)
}

/** Writes through the prototype setter so React, Vue and Angular trackers see a real change. */
function setNative(el: Element, prop: "value" | "checked", value: string | boolean) {
  const view = el.ownerDocument.defaultView!
  const proto =
    el.tagName === "TEXTAREA" ? view.HTMLTextAreaElement.prototype
      : el.tagName === "SELECT" ? view.HTMLSelectElement.prototype
        : view.HTMLInputElement.prototype
  const setter = Object.getOwnPropertyDescriptor(proto, prop)?.set
  if (setter) setter.call(el, value)
  else (el as unknown as Record<string, unknown>)[prop] = value
}

function commit(el: Element, write: () => void) {
  fire(el, "focus")
  fire(el, "focusin")
  write()
  fire(el, "input")
  fire(el, "change")
  fire(el, "blur")
  fire(el, "focusout")
}

function toDateValue(type: string, value: string): string | null {
  const iso = /^(\d{4})-(\d{2})(?:-(\d{2}))?/.exec(value)
  let y: string, m: string, d: string
  if (iso) [y, m, d] = [iso[1], iso[2], iso[3] ?? "01"]
  else {
    const parsed = new Date(value)
    if (Number.isNaN(parsed.getTime())) return null
    ;[y, m, d] = [String(parsed.getFullYear()), String(parsed.getMonth() + 1).padStart(2, "0"), String(parsed.getDate()).padStart(2, "0")]
  }
  if (type === "month") return `${y}-${m}`
  if (type === "date") return `${y}-${m}-${d}`
  return value
}

function fillText(el: TextControl, field: CollectedField, value: string): string | null {
  let next = value
  if (["date", "month"].includes(field.type)) {
    const converted = toDateValue(field.type, value)
    if (!converted) return "The date didn't fit this field's format"
    next = converted
  }
  if (field.type === "number" && Number.isNaN(Number(next.replace(/[, ]/g, "")))) return "Needs a number"
  if (field.type === "number") next = next.replace(/[, ]/g, "")
  if (field.max_length && next.length > field.max_length) next = next.slice(0, field.max_length)
  commit(el, () => setNative(el, "value", next))
  return el.value === next || field.type === "number" ? null : "The page didn't accept the value"
}

function fillSelect(el: HTMLSelectElement, value: string | string[]): string | null {
  const options = Array.from(el.options).map((o) => ({ value: o.value, label: o.textContent ?? "" }))
  const wanted = Array.isArray(value) ? value : [value]
  const picks = wanted.map((w) => matchOption(options, w)).filter((i) => i >= 0)
  if (!picks.length) return "None of the options matched"
  commit(el, () => {
    if (el.multiple) Array.from(el.options).forEach((o, i) => (o.selected = picks.includes(i)))
    else setNative(el, "value", options[picks[0]].value)
  })
  return null
}

/** Toggles a radio or checkbox input the way the browser does; the dispatched click lands on the input itself only. */
function setChecked(input: HTMLInputElement, checked: boolean) {
  if (input.checked === checked) return
  const view = input.ownerDocument.defaultView!
  fire(input, "focus")
  input.dispatchEvent(new view.MouseEvent("click", { bubbles: true, cancelable: true }))
  if (input.checked !== checked) commit(input, () => setNative(input, "checked", checked))
  else fire(input, "blur")
}

function fillChoices(controls: Element[], field: CollectedField, value: string | string[]): string | null {
  const inputs = controls as HTMLInputElement[]
  if (field.type === "checkbox" && inputs.length === 1 && !Array.isArray(value)) {
    const yes = truthy(value) ?? (matchOption(field.options, value) === 0 ? true : null)
    if (yes === null) return "Couldn't tell whether to tick this"
    if (yes) setChecked(inputs[0], true)
    return null
  }
  const wanted = Array.isArray(value) ? value : field.type === "checkbox" ? value.split(/\s*[;\n]\s*/) : [value]
  const picks = [...new Set(wanted.map((w) => matchOption(field.options, w)).filter((i) => i >= 0))]
  if (!picks.length) return "None of the options matched"
  if (field.type === "radio") setChecked(inputs[picks[0]], true)
  else picks.forEach((i) => setChecked(inputs[i], true))
  return null
}

function fillEditable(el: HTMLElement, value: string): string | null {
  const doc = el.ownerDocument
  el.focus({ preventScroll: true })
  const selection = doc.getSelection()
  if (selection) {
    const range = doc.createRange()
    range.selectNodeContents(el)
    selection.removeAllRanges()
    selection.addRange(range)
  }
  let inserted = false
  try {
    inserted = typeof doc.execCommand === "function" && doc.execCommand("insertText", false, value)
  } catch {
    inserted = false
  }
  if (!inserted || normalize(el.textContent ?? "") !== normalize(value)) {
    el.textContent = value
    fire(el, "input")
  }
  el.blur()
  return null
}

function decode(base64: string): Uint8Array<ArrayBuffer> {
  const binary = atob(base64)
  const bytes = new Uint8Array(binary.length)
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i)
  return bytes
}

export function accepts(accept: string, file: { name: string; type: string }): boolean {
  const rules = accept.split(",").map((r) => r.trim().toLowerCase()).filter(Boolean)
  if (!rules.length) return true
  const name = file.name.toLowerCase()
  const type = file.type.toLowerCase()
  return rules.some((rule) =>
    rule.startsWith(".") ? name.endsWith(rule) : rule.endsWith("/*") ? type.startsWith(rule.slice(0, -1)) : type === rule,
  )
}

function fillFile(el: HTMLInputElement, field: CollectedField, file: AttachedFile): string | null {
  if (!accepts(field.accept, file)) return `This upload doesn't take ${file.name.split(".").pop()?.toUpperCase() ?? "that"} files`
  const view = el.ownerDocument.defaultView!
  if (typeof view.DataTransfer !== "function") return "This browser can't attach files here"
  const transfer = new view.DataTransfer()
  transfer.items.add(new view.File([decode(file.base64)], file.name, { type: file.type }))
  el.files = transfer.files
  fire(el, "input")
  fire(el, "change")
  return el.files?.length ? null : "The page didn't accept the file"
}

function hasMemberValue(controls: Element[], field: CollectedField): boolean {
  const first = controls[0]
  if (field.type === "file") return !!(first as HTMLInputElement).files?.length
  if (field.type === "radio") return (controls as HTMLInputElement[]).some((c) => c.checked && ours.get(c) === undefined)
  if (field.type === "checkbox" || field.tag === "select") return false
  const current = field.tag === "contenteditable" ? (first.textContent ?? "") : (first as TextControl).value
  return current.trim() !== "" && ours.get(first) !== current
}

function fillOne(controls: Element[], field: CollectedField, instruction: FillInstruction): string | null {
  const first = controls[0]
  const value = instruction.value
  if (field.custom) {
    const suggestion = Array.isArray(value) ? value.join(", ") : value
    return suggestion ? `Pick this one yourself. Suggested: ${suggestion}` : "Pick this one yourself"
  }
  if (field.type === "file") return instruction.file ? fillFile(first as HTMLInputElement, field, instruction.file) : "No matching document in your kit"
  if (value === null || (Array.isArray(value) && !value.length) || value === "") return "No answer in your kit"
  if (field.tag === "select") return fillSelect(first as HTMLSelectElement, value)
  if (field.type === "radio" || field.type === "checkbox") return fillChoices(controls, field, value)
  const text = Array.isArray(value) ? value.join(", ") : value
  if (field.tag === "contenteditable") return fillEditable(first as HTMLElement, text)
  return fillText(first as TextControl, field, text)
}

/** Applies the API's answers; never submits, never touches buttons, and leaves what the member typed. */
export function applyFills(collected: Collected, instructions: FillInstruction[], mark: Mark = () => {}): FillOutcome[] {
  const fields = new Map(collected.fields.map((f) => [f.key, f]))
  return instructions.map((instruction) => {
    const field = fields.get(instruction.key)
    const controls = collected.controls.get(instruction.key)
    const skip = (reason: string): FillOutcome => ({ key: instruction.key, status: "skipped", reason })
    if (!field || !controls?.length) return skip("The field is gone from the page")
    if (!controls.every((c) => c.isConnected)) return skip("The field is gone from the page")
    if (controls.some((c) => isForbidden(c, ""))) return skip("Blesser never fills this kind of field")
    if (hasMemberValue(controls, field)) return skip("Already has your answer")
    const problem = fillOne(controls, field, instruction)
    if (problem) return skip(problem)
    controls.forEach((c) => ours.set(c, field.tag === "contenteditable" ? (c.textContent ?? "") : ((c as TextControl).value ?? "")))
    mark(instruction.key, collected.targets.get(instruction.key) ?? controls[0], instruction.drafted)
    return { key: instruction.key, status: instruction.drafted ? "drafted" : "filled", reason: "" }
  })
}
