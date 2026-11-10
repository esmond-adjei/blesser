import { readFileSync } from "node:fs"
import { JSDOM } from "jsdom"

export function loadFixture(name: string): Document {
  const html = readFileSync(new URL(`./fixtures/${name}`, import.meta.url), "utf8")
  return new JSDOM(html, { url: "https://apply.example.org/form" }).window.document
}

export const byLabel = <T extends { label: string }>(fields: T[], label: string): T => {
  const found = fields.find((f) => f.label === label)
  if (!found) throw new Error(`No field labelled "${label}". Labels: ${fields.map((f) => f.label).join(" | ")}`)
  return found
}
