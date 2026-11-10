const SKIP_TEXT = new Set(["SCRIPT", "STYLE", "NOSCRIPT", "TEMPLATE", "SELECT", "OPTION", "TEXTAREA", "INPUT", "BUTTON", "SVG"])

export const squash = (text: string) => text.replace(/\s+/g, " ").trim()

/** Lowercase, accents and punctuation dropped: the key option matching compares. */
export function normalize(text: string): string {
  return squash(text.normalize("NFKD").replace(/[̀-ͯ]/g, "").toLowerCase().replace(/[^a-z0-9]+/g, " "))
}

export const REQUIRED_MARK = /\s*(?:\*|✱|\(required\)|\(obligatoire\))\s*$/i

// Form builders (Microsoft Forms, numbered PDFs turned forms) prefix question numbers.
const QUESTION_NUMBER = /^(?:q(?:uestion)?\s*)?\d{1,3}\s*[.):]\s+/i

export function cleanLabel(text: string): string {
  let out = squash(text).replace(QUESTION_NUMBER, "")
  while (REQUIRED_MARK.test(out)) out = out.replace(REQUIRED_MARK, "")
  return out.replace(/[:\s]+$/, "")
}

/** Visible-ish text of a subtree, skipping controls, scripts and anything in `exclude`. */
export function textOf(root: Node, exclude: (el: Element) => boolean = () => false): string {
  const parts: string[] = []
  const walk = (node: Node) => {
    if (node.nodeType === 3) {
      parts.push(node.nodeValue ?? "")
      return
    }
    if (node.nodeType !== 1) return
    const el = node as Element
    // Like the accessible name: aria-hidden parts are skipped unless the label points at them directly.
    if (el !== root && el.getAttribute("aria-hidden") === "true") return
    if (SKIP_TEXT.has(el.tagName.toUpperCase()) || el.hasAttribute("hidden") || exclude(el)) return
    const block = isBlock(el)
    if (block) parts.push(" ")
    for (const child of Array.from(el.childNodes)) walk(child)
    if (block) parts.push(" ")
  }
  walk(root)
  return squash(parts.join(""))
}

const BLOCKS = new Set(["DIV", "P", "LI", "UL", "OL", "LABEL", "LEGEND", "H1", "H2", "H3", "H4", "H5", "H6", "SPAN", "SMALL", "BR", "FIELDSET", "SECTION", "TD", "TH"])
const isBlock = (el: Element) => BLOCKS.has(el.tagName.toUpperCase())

const WORD_LIMITS = [
  /(?:max(?:imum)?\.?|up to|no more than|not (?:to )?exceed(?:ing)?|limit(?:ed)? to|at most|less than|fewer than|within)\s*(?:of\s*)?(\d[\d,]*)\s*words?/i,
  /(\d[\d,]*)\s*words?\s*(?:max(?:imum)?|or less|or fewer|limit|maximum)/i,
  /(\d[\d,]*)[\s-]*words?\b/i,
]

export function parseWordLimit(...texts: string[]): number | null {
  const text = texts.join(" ")
  for (const pattern of WORD_LIMITS) {
    const match = pattern.exec(text)
    if (match) {
      const value = Number(match[1].replace(/,/g, ""))
      if (value > 0 && value < 20000) return value
    }
  }
  return null
}

export const wordCount = (text: string) => (text.trim() ? text.trim().split(/\s+/).length : 0)

/** Index of the option best matching `wanted` by value, then label, then containment; -1 when none is clear. */
export function matchOption(options: { value: string; label: string }[], wanted: string): number {
  const exact = options.findIndex((o) => o.value === wanted)
  if (exact >= 0) return exact
  const target = normalize(wanted)
  if (!target) return -1
  const byLabel = options.findIndex((o) => normalize(o.label) === target)
  if (byLabel >= 0) return byLabel
  const byValue = options.findIndex((o) => normalize(o.value) === target)
  if (byValue >= 0) return byValue
  const partial = options
    .map((o, i) => ({ i, label: normalize(o.label) }))
    .filter(({ label }) => label && (label.startsWith(target) || target.startsWith(label) || label.includes(` ${target} `)))
  return partial.length === 1 ? partial[0].i : -1
}

const TRUTHY = new Set(["true", "yes", "y", "on", "1", "checked", "agree", "i agree"])
const FALSY = new Set(["false", "no", "n", "off", "0", "unchecked", ""])

export function truthy(value: string): boolean | null {
  const key = normalize(value)
  if (TRUTHY.has(key)) return true
  if (FALSY.has(key)) return false
  return null
}
