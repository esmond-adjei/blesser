import { OVERLAY_ID } from "./collect"

const STYLE_ID = "blesser-fill-style"
const ATTR = "data-blesser-fill"
const CSS = `
[${ATTR}="filled"] { outline: 2px solid rgba(31, 122, 84, 0.55) !important; outline-offset: 2px !important; }
[${ATTR}="drafted"] { outline: 2px dashed rgba(196, 120, 0, 0.9) !important; outline-offset: 2px !important; }
[${ATTR}="focus"] { outline: 3px solid rgba(37, 99, 235, 0.9) !important; outline-offset: 3px !important; }
`
const TAG_CSS = `
:host { all: initial; }
.tag { position: absolute; z-index: 2147483646; pointer-events: none; font: 600 11px/16px system-ui, -apple-system, "Segoe UI", sans-serif;
  color: #5c3b00; background: #fff4d6; border: 1px solid #e3b341; border-radius: 999px; padding: 0 7px; white-space: nowrap;
  box-shadow: 0 1px 2px rgba(0,0,0,.12); transform: translate(calc(-100% - 6px), -50%); }
@media (prefers-color-scheme: dark) { .tag { color: #ffe7a8; background: #3d2c05; border-color: #a77a10; } }
`

const tagged = new Map<string, { target: Element; tag: HTMLElement }>()
let shadow: ShadowRoot | null = null
let frame = 0

function ensureStyle(doc: Document) {
  if (doc.getElementById(STYLE_ID)) return
  const style = doc.createElement("style")
  style.id = STYLE_ID
  style.textContent = CSS
  ;(doc.head ?? doc.documentElement).appendChild(style)
}

function overlay(doc: Document): ShadowRoot {
  if (shadow && doc.getElementById(OVERLAY_ID)) return shadow
  const host = doc.createElement("div")
  host.id = OVERLAY_ID
  host.style.cssText = "position:absolute;top:0;left:0;width:0;height:0;"
  doc.documentElement.appendChild(host)
  shadow = host.attachShadow({ mode: "open" })
  const style = doc.createElement("style")
  style.textContent = TAG_CSS
  shadow.appendChild(style)
  const view = doc.defaultView
  view?.addEventListener("scroll", schedule, { passive: true, capture: true })
  view?.addEventListener("resize", schedule, { passive: true })
  return shadow
}

function place() {
  frame = 0
  for (const { target, tag } of tagged.values()) {
    const view = target.ownerDocument.defaultView
    const rect = target.getBoundingClientRect()
    const hidden = rect.width === 0 && rect.height === 0
    tag.style.display = hidden ? "none" : ""
    tag.style.top = `${rect.top + (view?.scrollY ?? 0)}px`
    tag.style.left = `${rect.right + (view?.scrollX ?? 0)}px`
  }
}

function schedule() {
  if (frame) return
  const view = shadow?.host.ownerDocument.defaultView
  frame = view?.requestAnimationFrame(place) ?? 0
}

/** Outlines a filled field; drafted ones also get a "review" tag in an overlay so page markup is left alone. */
export function markField(key: string, target: Element, drafted: boolean) {
  const doc = target.ownerDocument
  ensureStyle(doc)
  target.setAttribute(ATTR, drafted ? "drafted" : "filled")
  tagged.get(key)?.tag.remove()
  tagged.delete(key)
  if (!drafted) return
  const tag = doc.createElement("span")
  tag.className = "tag"
  tag.textContent = "Drafted by Blesser, review"
  overlay(doc).appendChild(tag)
  tagged.set(key, { target, tag })
  schedule()
}

export function unmarkField(key: string, target: Element) {
  target.removeAttribute(ATTR)
  tagged.get(key)?.tag.remove()
  tagged.delete(key)
}

export function flashField(target: Element) {
  ensureStyle(target.ownerDocument)
  const previous = target.getAttribute(ATTR)
  target.setAttribute(ATTR, "focus")
  target.ownerDocument.defaultView?.setTimeout(() => {
    if (previous) target.setAttribute(ATTR, previous)
    else target.removeAttribute(ATTR)
  }, 1600)
}

export function clearMarks(doc: Document) {
  doc.querySelectorAll(`[${ATTR}]`).forEach((el) => el.removeAttribute(ATTR))
  tagged.forEach(({ tag }) => tag.remove())
  tagged.clear()
}
