import type { CollectedField, FieldOption, FieldTag } from "../shared/types"
import { isForbidden } from "./guards"
import { cleanLabel, parseWordLimit, REQUIRED_MARK, squash, textOf } from "./text"

export const OVERLAY_ID = "blesser-overlay"

export interface Collected {
  fields: CollectedField[]
  controls: Map<string, Element[]>
  targets: Map<string, Element>
}

export interface CollectOptions {
  /** Real browsers: also drop zero-size controls (honeypots, collapsed sections). jsdom has no layout. */
  layout?: boolean
}

type Kind = "single" | "radio" | "checkbox" | "aria-radio" | "aria-checkbox" | "aria-listbox" | "aria-combobox"

interface Group {
  kind: Kind
  controls: Element[]
  root: Element
}

const CANDIDATES =
  'input, textarea, select, [contenteditable=""], [contenteditable="true"], [contenteditable="plaintext-only"], [role="radiogroup"], [role="listbox"], [role="combobox"], [role="checkbox"]'
const SKIP_TYPES = new Set(["hidden", "submit", "button", "reset", "image", "password", "search"])
const HEADINGS = 'h1, h2, h3, h4, h5, h6, [role="heading"]'

const tagOf = (el: Element) => el.tagName.toLowerCase()
const isNative = (el: Element) => ["input", "textarea", "select"].includes(tagOf(el))
const inputType = (el: Element) => (tagOf(el) === "input" ? ((el as HTMLInputElement).type || "text").toLowerCase() : "")

function isHiddenEl(el: Element): boolean {
  const view = el.ownerDocument.defaultView
  for (let node: Element | null = el; node; node = node.parentElement) {
    if (node.hasAttribute("hidden") || node.getAttribute("aria-hidden") === "true") return true
    const style = view?.getComputedStyle(node)
    if (style && style.display === "none") return true
    if (node === el && style && style.visibility === "hidden") return true
  }
  return false
}

function zeroSize(el: Element): boolean {
  const rect = el.getBoundingClientRect()
  return rect.width === 0 && rect.height === 0
}

function labelsOf(el: Element): Element[] {
  const labels = (el as HTMLInputElement).labels
  return labels ? Array.from(labels) : []
}

function isVisible(el: Element, layout: boolean): boolean {
  const type = inputType(el)
  if (type === "file") return true
  const shown = (node: Element) => !isHiddenEl(node) && !(layout && zeroSize(node))
  if (shown(el)) return true
  // Styled radios and checkboxes hide the native input behind a visible label.
  return (type === "radio" || type === "checkbox") && labelsOf(el).some(shown)
}

function referenced(el: Element, attr: string): Element[] {
  const ids = (el.getAttribute(attr) ?? "").split(/\s+/).filter(Boolean)
  return ids.map((id) => el.ownerDocument.getElementById(id)).filter((n): n is HTMLElement => !!n)
}

function ownLabelText(el: Element): string {
  const by = referenced(el, "aria-labelledby")
  if (by.length) return by.map((n) => textOf(n)).join(" ")
  // Wrapping labels often hold the whole field; skip the branch that contains the control.
  const labels = labelsOf(el).map((l) => textOf(l, (n) => n !== l && n.contains(el))).filter(Boolean)
  if (labels.length) return labels.join(" ")
  return el.getAttribute("aria-label") ?? ""
}

function optionLabel(el: Element): string {
  const own = ownLabelText(el)
  if (own.trim()) return cleanLabel(own)
  let next = el.nextSibling
  while (next && next.nodeType === 3 && !next.nodeValue?.trim()) next = next.nextSibling
  if (next && (next.nodeType === 3 || (next.nodeType === 1 && !isNative(next as Element)))) {
    const text = next.nodeType === 3 ? (next.nodeValue ?? "") : textOf(next)
    if (text.trim()) return cleanLabel(text)
  }
  return el.getAttribute("data-value") ?? (el as HTMLInputElement).value ?? ""
}

function commonAncestor(nodes: Element[]): Element {
  let anc: Element = nodes[0]
  while (anc.parentElement && !nodes.every((n) => anc.contains(n))) anc = anc.parentElement
  return anc
}

function gather(doc: Document, layout: boolean): Group[] {
  const groups: Group[] = []
  const byName = new Map<string, Group>()
  const seen = new Set<Element>()
  const overlay = doc.getElementById(OVERLAY_ID)

  for (const el of Array.from(doc.querySelectorAll(CANDIDATES))) {
    if (seen.has(el) || (overlay && overlay.contains(el))) continue
    const tag = tagOf(el)
    const role = el.getAttribute("role")

    if (tag === "input") {
      const type = inputType(el)
      const input = el as HTMLInputElement
      if (SKIP_TYPES.has(type) || input.disabled || (input.readOnly && type !== "file")) continue
      if (!isVisible(el, layout)) continue
      if (role === "combobox" || input.getAttribute("aria-autocomplete") === "list") {
        groups.push({ kind: "aria-combobox", controls: [el], root: el })
        continue
      }
      if ((type === "radio" || type === "checkbox") && input.name) {
        const groupKey = `${type}|${input.form ? Array.from(doc.forms).indexOf(input.form) : -1}|${input.name}`
        const existing = byName.get(groupKey)
        if (existing) {
          existing.controls.push(el)
          continue
        }
        const group: Group = { kind: type, controls: [el], root: el }
        byName.set(groupKey, group)
        groups.push(group)
        continue
      }
      groups.push({ kind: type === "radio" ? "radio" : "single", controls: [el], root: el })
      continue
    }
    if (tag === "textarea" || tag === "select") {
      const control = el as HTMLTextAreaElement | HTMLSelectElement
      if (control.disabled || (tag === "textarea" && (control as HTMLTextAreaElement).readOnly)) continue
      if (!isVisible(el, layout)) continue
      groups.push({ kind: "single", controls: [el], root: el })
      continue
    }
    if (el.hasAttribute("contenteditable") && (!role || role === "textbox")) {
      if (el.parentElement?.closest('[contenteditable=""], [contenteditable="true"], [contenteditable="plaintext-only"]')) continue
      if (!isVisible(el, layout)) continue
      groups.push({ kind: "single", controls: [el], root: el })
      continue
    }
    if (el.closest("select") || !isVisible(el, layout) || el.getAttribute("aria-disabled") === "true") continue
    if (role === "radiogroup") {
      const radios = Array.from(el.querySelectorAll('[role="radio"]')).filter((r) => !isNative(r))
      if (!radios.length) continue
      radios.forEach((r) => seen.add(r))
      groups.push({ kind: "aria-radio", controls: radios, root: el })
    } else if (role === "listbox" || role === "combobox") {
      el.querySelectorAll('[role="listbox"], [role="combobox"]').forEach((n) => seen.add(n))
      groups.push({ kind: role === "listbox" ? "aria-listbox" : "aria-combobox", controls: [el], root: el })
    } else if (role === "checkbox") {
      const holder = el.parentElement?.closest('[role="list"], [role="group"], fieldset') ?? null
      const siblings = holder
        ? Array.from(holder.querySelectorAll('[role="checkbox"]')).filter((c) => !isNative(c) && c.closest('[role="list"], [role="group"], fieldset') === holder)
        : [el]
      siblings.forEach((c) => seen.add(c))
      groups.push({ kind: "aria-checkbox", controls: siblings, root: siblings.length > 1 && holder ? holder : el })
    }
  }

  for (const group of groups) {
    if (group.kind === "checkbox" && group.controls.length === 1) group.kind = "single"
    if ((group.kind === "radio" || group.kind === "checkbox") && group.controls.length > 1) {
      const fieldset = group.controls[0].closest("fieldset")
      group.root = fieldset && group.controls.every((c) => fieldset.contains(c)) ? fieldset : commonAncestor(group.controls)
    }
  }
  return groups
}

function containerOf(group: Group, groups: Group[]): Element {
  let node = group.root
  const stop = new Set(["FORM", "BODY", "HTML"])
  while (node.parentElement && !stop.has(node.parentElement.tagName.toUpperCase())) {
    const parent = node.parentElement
    if (groups.some((other) => other !== group && other.controls.some((c) => parent.contains(c)))) break
    node = parent
  }
  return node
}

interface Blocks {
  before: string[]
  after: string[]
}

function blocksAround(container: Element, first: Element, exclude: (el: Element) => boolean): Blocks {
  const out: Blocks = { before: [], after: [] }
  let buffer = ""
  let passed = false
  const flush = () => {
    const text = squash(buffer)
    if (text) (passed ? out.after : out.before).push(text)
    buffer = ""
  }
  const walk = (node: Node) => {
    if (node === first) {
      flush()
      passed = true
      return
    }
    if (node.nodeType === 3) {
      buffer += node.nodeValue ?? ""
      return
    }
    if (node.nodeType !== 1) return
    const el = node as Element
    const tag = el.tagName.toUpperCase()
    if (["SCRIPT", "STYLE", "NOSCRIPT", "TEMPLATE", "SELECT", "TEXTAREA", "INPUT", "BUTTON", "SVG"].includes(tag)) return
    if (el.hasAttribute("hidden") || exclude(el)) return
    const block = tag !== "SPAN" && tag !== "A" && tag !== "B" && tag !== "STRONG" && tag !== "EM" && tag !== "I"
    if (block) flush()
    el.childNodes.forEach(walk)
    if (block) flush()
  }
  walk(container)
  flush()
  return out
}

function precedingText(el: Element): string {
  let sibling = el.previousElementSibling
  for (let i = 0; sibling && i < 2; i++, sibling = sibling.previousElementSibling) {
    if (sibling.querySelector("input, textarea, select") || isNative(sibling)) return ""
    const text = textOf(sibling)
    if (text) return text
  }
  return ""
}

function sectionOf(control: Element, label: string, groupLabelSource: Element | null, headings: Element[]): string {
  const fieldset = control.closest("fieldset")
  const outer = fieldset && fieldset === groupLabelSource ? fieldset.parentElement?.closest("fieldset") : fieldset
  const legend = outer?.querySelector(":scope > legend")
  if (legend) return cleanLabel(textOf(legend))
  let best: Element | null = null
  for (const heading of headings) {
    if (heading.contains(control) || cleanLabel(textOf(heading)) === label) continue
    if (heading.compareDocumentPosition(control) & 4) best = heading
  }
  return best ? cleanLabel(textOf(best)).slice(0, 200) : ""
}

function groupLabel(group: Group): { text: string; source: Element | null } {
  const root = group.root
  const fieldset = root.tagName.toUpperCase() === "FIELDSET" ? root : null
  const legend = fieldset?.querySelector(":scope > legend")
  if (legend) return { text: textOf(legend), source: fieldset }
  const labelled = group.controls[0].closest('[role="radiogroup"], [role="group"], [role="list"]') ?? (root.getAttribute("role") ? root : null)
  if (labelled) {
    const by = referenced(labelled, "aria-labelledby")
    if (by.length) return { text: by.map((n) => textOf(n)).join(" "), source: labelled }
    const aria = labelled.getAttribute("aria-label")
    if (aria) return { text: aria, source: labelled }
  }
  return { text: "", source: null }
}

function describe(group: Group, groups: Group[], key: string, headings: Element[]): CollectedField {
  const first = group.controls[0]
  const multi = group.kind !== "single" && group.kind !== "aria-combobox" && group.kind !== "aria-listbox"
  const container = containerOf(group, groups)
  const options: FieldOption[] = []
  const optionEls = new Set<Element>()

  if (multi) {
    for (const control of group.controls) {
      const label = optionLabel(control)
      const value = isNative(control) ? (control as HTMLInputElement).value : (control.getAttribute("data-value") ?? control.getAttribute("data-answer-value") ?? label)
      options.push({ value, label })
      labelsOf(control).forEach((l) => optionEls.add(l))
      referenced(control, "aria-labelledby").forEach((l) => optionEls.add(l))
    }
  } else if (tagOf(first) === "select") {
    for (const option of Array.from((first as HTMLSelectElement).options)) {
      if (option.disabled && !option.value) continue
      const label = squash(option.textContent ?? "")
      if (!option.value && /^(?:select|choose|pick|please|--|—|\s*$)/i.test(label)) continue
      options.push({ value: option.value, label })
    }
  } else if (group.kind === "aria-listbox") {
    first.querySelectorAll('[role="option"]').forEach((o) => {
      const label = squash(o.getAttribute("aria-label") ?? textOf(o))
      if (label) options.push({ value: o.getAttribute("data-value") ?? label, label })
    })
  } else if (inputType(first) === "checkbox") {
    options.push({ value: (first as HTMLInputElement).value || "on", label: cleanLabel(ownLabelText(first)) })
  }

  const own = multi ? groupLabel(group) : { text: ownLabelText(first), source: null }
  const labelEls = new Set<Element>([...(multi ? [] : labelsOf(first)), ...referenced(multi && own.source ? own.source : first, "aria-labelledby")])
  const legend = own.source?.querySelector(":scope > legend")
  if (legend) labelEls.add(legend)
  const exclude = (el: Element) =>
    labelEls.has(el) || optionEls.has(el) || el.id === OVERLAY_ID || ["radio", "checkbox", "option"].includes(el.getAttribute("role") ?? "")
  const blocks = container === first ? { before: [], after: [] } : blocksAround(container, first, exclude)

  let rawLabel = own.text
  let before = blocks.before
  if (!squash(rawLabel)) {
    const index = before.findIndex((b) => cleanLabel(b) !== "")
    if (index >= 0) {
      rawLabel = before.slice(0, index + 1).join(" ")
      before = before.slice(index + 1)
    } else {
      rawLabel = precedingText(container)
    }
  }
  const label = cleanLabel(rawLabel).slice(0, 300)
  const described = referenced(first, "aria-describedby").map((n) => textOf(n))
  const helpParts = [...described, ...before, ...blocks.after]
    .map(squash)
    .filter((t) => t && cleanLabel(t) && cleanLabel(t) !== label && !options.some((o) => o.label === t))
  const help = [...new Set(helpParts)].join(" ").slice(0, 500)

  const placeholder = first.getAttribute("placeholder") ?? first.getAttribute("aria-placeholder") ?? ""
  const required =
    group.controls.some((c) => (c as HTMLInputElement).required === true || c.getAttribute("aria-required") === "true") ||
    (own.source?.getAttribute("aria-required") === "true") ||
    REQUIRED_MARK.test(squash(rawLabel)) ||
    blocks.before.some((b) => /^(?:\*|✱)$/.test(b) || /\brequired\b/i.test(b) && b.length < 20)
  const maxLength = (first as HTMLInputElement).maxLength
  const tag: FieldTag =
    tagOf(first) === "textarea" ? "textarea" : tagOf(first) === "select" || group.kind === "aria-listbox" || group.kind === "aria-combobox" ? "select" : isNative(first) || multi ? "input" : "contenteditable"
  const type =
    group.kind === "aria-radio" || group.kind === "radio" ? "radio"
      : group.kind === "aria-checkbox" || group.kind === "checkbox" ? "checkbox"
        : tag === "textarea" ? "textarea"
          : tag === "select" ? ((first as HTMLSelectElement).multiple ? "select-multiple" : "select")
            : tag === "contenteditable" ? "text"
              : inputType(first)

  return {
    key,
    tag,
    type,
    name: first.getAttribute("name") ?? "",
    id: first.id ?? "",
    autocomplete: first.getAttribute("autocomplete") ?? "",
    label,
    placeholder,
    help_text: help,
    section: sectionOf(first, label, own.source, headings),
    options,
    required,
    max_length: typeof maxLength === "number" && maxLength > 0 ? maxLength : null,
    word_limit: parseWordLimit(label, help, placeholder),
    accept: first.getAttribute("accept") ?? "",
    custom: group.kind.startsWith("aria-"),
  }
}

/** Every fillable field on the page; password, payment and hidden controls are left out. */
export function collectFields(doc: Document, options: CollectOptions = {}): Collected {
  const groups = gather(doc, options.layout ?? false)
  const headings = Array.from(doc.querySelectorAll(HEADINGS))
  const out: Collected = { fields: [], controls: new Map(), targets: new Map() }
  let index = 0
  for (const group of groups) {
    const key = String(index)
    const field = describe(group, groups, key, headings)
    const freeText = field.tag === "textarea" || field.tag === "contenteditable" || (field.tag === "input" && !["radio", "checkbox", "file"].includes(field.type))
    if (group.controls.some((c) => isForbidden(c, freeText ? field.label : ""))) continue
    out.fields.push(field)
    out.controls.set(key, group.controls)
    out.targets.set(key, group.controls.length > 1 ? group.root : group.controls[0])
    index++
  }
  return out
}
