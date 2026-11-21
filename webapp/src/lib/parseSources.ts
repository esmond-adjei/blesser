import type { OpportunityCategory } from "./types"

export interface ParsedSource {
  url: string
  category: OpportunityCategory
  note: string
}

const URL_RE = /(?:https?:\/\/[^\s<>"')\]]+)|(?<![@\w.-])(?:[a-z0-9-]+\.)+[a-z]{2,24}(?:\/[^\s<>"')\]]*)?/gi
const NOT_SITES = /\.(?:txt|pdf|docx?|xlsx?|png|jpe?g|gif|csv|zip)$/i
const GUESSES: [OpportunityCategory, RegExp][] = [
  ["student", /scholar|bursar|student|undergrad|master|graduate|admission|exchange/i],
  ["research", /research|grant|fellow|phd|postdoc|laborator|academ/i],
  ["startup", /startup|accelerat|incubat|venture|founder|pitch|seed|innovat|entrepreneur/i],
]

function tidy(value: string): string {
  return value.replace(/^[\s\-–—*•>#\d.)(:|,;]+|[\s\-–—*•|:,;([]+$/g, "").replace(/\s+/g, " ").trim()
}

function guess(text: string, fallback: OpportunityCategory): OpportunityCategory {
  return GUESSES.find(([, pattern]) => pattern.test(text))?.[0] ?? fallback
}

/** Pull sites out of pasted text: links, bare domains, markdown links and "name - link" lines. */
export function parseSources(text: string, fallback: OpportunityCategory): ParsedSource[] {
  const found = new Map<string, ParsedSource>()
  let heading = ""
  for (const raw of text.split(/\r?\n/)) {
    const line = raw.replace(/\[([^\]]*)\]\(([^)]*)\)/g, " $1 $2 ")
    const urls = (line.match(URL_RE) ?? []).map((u) => u.replace(/[.,;:!?]+$/, "")).filter((u) => !NOT_SITES.test(u))
    const rest = tidy(line.replace(URL_RE, " "))
    if (!urls.length) {
      heading = rest
      continue
    }
    for (const url of urls) {
      const key = url.replace(/^https?:\/\//i, "").replace(/^www\./i, "").replace(/\/+$/, "").toLowerCase()
      if (found.has(key)) continue
      const note = (rest || heading).slice(0, 500)
      found.set(key, { url, category: guess(`${note} ${url}`, fallback), note })
    }
    heading = ""
  }
  return [...found.values()]
}
