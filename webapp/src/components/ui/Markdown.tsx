import * as React from "react"
import ReactMarkdown, { type Components, type Options } from "react-markdown"
import remarkGfm from "remark-gfm"
import { cn } from "../../lib/utils"
import { citationKey, remarkCitations, type CitationIndex } from "../../lib/citations"
import { CitationChip } from "./Citation"
import { Check, Copy } from "lucide-react"
import { toastError } from "../../lib/toast"

const CitationsContext = React.createContext<CitationIndex | null>(null)

/** One stable component, so a re-render (a streaming reply) never remounts an open preview. */
function MarkdownLink({ href, children, node: _node, ...props }: React.ComponentProps<"a"> & { node?: unknown }) {
  const index = React.useContext(CitationsContext)
  const key = citationKey(href)
  const cite = key && index ? index[key] : undefined
  if (cite) return <CitationChip cite={cite} />
  return (
    <a href={href} {...props}>
      {children}
    </a>
  )
}

function codeText(children: React.ReactNode): string {
  return React.Children.toArray(children).map(child => {
    if (typeof child === "string" || typeof child === "number") return String(child)
    if (React.isValidElement<{ children?: React.ReactNode }>(child)) return codeText(child.props.children)
    return ""
  }).join("")
}

function CodeBlock({ children }: React.ComponentProps<"pre">) {
  const [copied, setCopied] = React.useState(false)
  React.useEffect(() => {
    if (!copied) return
    const timer = window.setTimeout(() => setCopied(false), 1500)
    return () => window.clearTimeout(timer)
  }, [copied])
  async function copy() {
    try { await navigator.clipboard.writeText(codeText(children)); setCopied(true) }
    catch { toastError("Couldn't copy code") }
  }
  return <div className="relative rounded-lg border border-border bg-muted/50">
    <div className="sticky top-0 z-10 flex justify-end rounded-t-lg bg-muted px-2 py-1">
      <button type="button" aria-label={copied ? "Code copied" : "Copy code"} onClick={() => void copy()} className="flex cursor-pointer items-center gap-1.5 rounded px-2 py-1 text-xs text-muted-foreground hover:text-foreground">{copied ? <Check className="size-3.5" /> : <Copy className="size-3.5" />}{copied ? "Copied" : "Copy"}</button>
    </div>
    <pre className="m-0! overflow-x-auto border-0! nice-scroll">{children}</pre>
  </div>
}

const COMPONENTS: Components = { a: MarkdownLink, pre: CodeBlock }

/** Styling comes from `.rich-text`; with `citations`, `[s3]` markers become numbered chips. */
export function Markdown({
  text,
  className,
  citations,
}: {
  text: string
  className?: string
  citations?: CitationIndex
}) {
  const cited = citations && Object.keys(citations).length > 0 ? citations : null
  const remarkPlugins = React.useMemo<Options["remarkPlugins"]>(
    () => (cited ? [remarkGfm, [remarkCitations, { index: cited }]] : [remarkGfm]),
    [cited],
  )
  return (
    <div className={cn("rich-text", className)}>
      <CitationsContext.Provider value={cited}>
        <ReactMarkdown remarkPlugins={remarkPlugins} components={COMPONENTS}>
          {text}
        </ReactMarkdown>
      </CitationsContext.Provider>
    </div>
  )
}

export default Markdown
