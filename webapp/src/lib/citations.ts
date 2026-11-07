/** Citations in Gradis replies. The server keys every source a tool
 * result returned (s1, s2…) and the reply cites them as `[s3]`. Here they
 * become numbered chips, numbered by first appearance in one message. */

/** One source the server issued a key for. In-app records carry `href`
 * (a route); pages, papers and authors carry `url`. */
export interface CitationSource {
  key: string
  kind: string
  id?: string
  title: string
  subtitle?: string | null
  image_url?: string | null
  snippet?: string | null
  href?: string | null
  url?: string | null
  venue?: string | null
  year?: number | string | null
  score?: number | null
  program?: string | null
}

/** A cited source and its number in the message. */
export interface Citation {
  n: number
  source: CitationSource
}

/** Key -> number and source, for the citations one message makes. */
export type CitationIndex = Record<string, Citation>

const KIND_LABELS: Record<string, string> = {
  candidate: "Professor match",
  professor: "Professor",
  author: "Researcher",
  program: "Programme",
  school: "School",
  application: "Application",
  draft: "Email draft",
  run: "Run",
  cv: "CV",
  document: "Document",
  paper: "Paper",
  web: "Web page",
}

export function kindLabel(kind: string): string {
  return KIND_LABELS[kind] ?? "Source"
}

/** Code fences and spans first, so a citation-looking string in code is skipped. */
const CITE = /(```[\s\S]*?```|`[^`\n]*`)|\[(s\d+)\]/g

/** Every key the text cites outside code, in order of first appearance. */
export function citedKeys(text: string): string[] {
  const out: string[] = []
  for (const m of text.matchAll(CITE)) {
    if (m[2] && !out.includes(m[2])) out.push(m[2])
  }
  return out
}

/** Number the sources one message cites, 1, 2, 3 by first appearance.
 * Keys with no known source are left out (and stay plain text). */
export function citationIndex(text: string, sources: Record<string, CitationSource>): CitationIndex {
  const index: CitationIndex = {}
  let n = 0
  for (const key of citedKeys(text)) {
    const source = sources[key]
    if (source) index[key] = { n: ++n, source }
  }
  return index
}

/** The source's own address: an in-app route made absolute, or its URL. */
function sourceUrl(source: CitationSource, origin = window.location.origin): string | null {
  if (source.url) return source.url
  if (source.href) return new URL(source.href, origin).toString()
  return null
}

/** Copy-as-Markdown: `[s3]` becomes a footnote reference, with the
 * footnotes listed at the end. Code is left alone. */
export function citationsToMarkdown(text: string, index: CitationIndex, origin?: string): string {
  const used = Object.values(index)
  if (used.length === 0) return text
  const body = text.replace(CITE, (match, code: string | undefined, key: string | undefined) => {
    if (code || !key) return match
    const cite = index[key]
    return cite ? `[^${cite.n}]` : match
  })
  const notes = used
    .sort((a, b) => a.n - b.n)
    .map(({ n, source }) => {
      const url = sourceUrl(source, origin)
      return `[^${n}]: ${url ? `[${source.title}](${url})` : source.title}`
    })
  return `${body}\n\n${notes.join("\n")}`
}

// Only `text` nodes are rewritten, so
// inline code and code blocks (their own node types) are never touched.

interface MdNode {
  type: string
  value?: string
  url?: string
  children?: MdNode[]
}

const CITE_PREFIX = "#cite-"

const KEY = /\[(s\d+)\]/g

function splitText(node: MdNode, index: CitationIndex): MdNode[] | null {
  const value = node.value ?? ""
  const parts: MdNode[] = []
  let last = 0
  for (const m of value.matchAll(KEY)) {
    const cite = index[m[1]]
    if (!cite) continue
    const at = m.index ?? 0
    if (at > last) parts.push({ type: "text", value: value.slice(last, at) })
    parts.push({
      type: "link",
      url: `${CITE_PREFIX}${m[1]}`,
      children: [{ type: "text", value: String(cite.n) }],
    })
    last = at + m[0].length
  }
  if (parts.length === 0) return null
  if (last < value.length) parts.push({ type: "text", value: value.slice(last) })
  return parts
}

function walk(node: MdNode, index: CitationIndex) {
  if (!node.children) return
  // A citation inside a link would nest links; leave those as they are.
  if (node.type === "link" || node.type === "linkReference") return
  const next: MdNode[] = []
  for (const child of node.children) {
    if (child.type === "text") {
      const split = splitText(child, index)
      if (split) {
        next.push(...split)
        continue
      }
    } else {
      walk(child, index)
    }
    next.push(child)
  }
  node.children = next
}

/** remark plugin: `[sN]` with a known source becomes a link to `#cite-sN`
 * whose text is its number. Unknown keys stay plain text. */
export function remarkCitations(options: { index: CitationIndex }) {
  return (tree: MdNode) => {
    walk(tree, options.index)
  }
}

/** The key a citation link points at, or null for an ordinary link. */
export function citationKey(href: string | undefined): string | null {
  return href?.startsWith(CITE_PREFIX) ? href.slice(CITE_PREFIX.length) : null
}
