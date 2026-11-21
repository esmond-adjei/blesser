import { Children, isValidElement, type ComponentProps, type ReactNode } from "react"
import ReactMarkdown, { type Components } from "react-markdown"
import remarkGfm from "remark-gfm"
import { Link } from "react-router-dom"
import { Check, Copy } from "lucide-react"
import { cn } from "@blesser/ui"
import { useCopy } from "../../lib/useCopy"

function textOf(node: ReactNode): string {
  return Children.toArray(node).map((child) => {
    if (typeof child === "string" || typeof child === "number") return String(child)
    if (isValidElement<{ children?: ReactNode }>(child)) return textOf(child.props.children)
    return ""
  }).join("")
}

function CodeBlock({ children }: ComponentProps<"pre">) {
  const { copied, copy } = useCopy(() => textOf(children).replace(/\n$/, ""))
  const language = isValidElement<{ className?: string }>(children) ? /language-(\w+)/.exec(children.props.className ?? "")?.[1] : undefined
  return (
    <div className="overflow-hidden rounded-md border border-separator bg-surface-sunk">
      <div className="flex items-center justify-between border-b border-separator px-3 py-1">
        <span className="text-caption text-ink-tertiary">{language ?? "Text"}</span>
        <button
          type="button"
          onClick={() => void copy()}
          aria-label={copied ? "Code copied" : "Copy code"}
          className="flex cursor-pointer items-center gap-1.5 rounded-sm px-1.5 py-1 text-caption text-ink-secondary transition-colors hover:text-ink focus-visible:outline-2 focus-visible:outline-focus"
        >
          {copied ? <Check className="size-3.5 text-positive" aria-hidden="true" /> : <Copy className="size-3.5" aria-hidden="true" />}
          {copied ? "Copied" : "Copy"}
        </button>
      </div>
      <pre className="nice-scroll overflow-x-auto p-3 text-footnote leading-relaxed">{children}</pre>
    </div>
  )
}

function MarkdownLink({ href, children }: ComponentProps<"a"> & { node?: unknown }) {
  if (href?.startsWith("/")) return <Link to={href}>{children}</Link>
  return <a href={href} target="_blank" rel="noreferrer noopener">{children}</a>
}

const COMPONENTS: Components = {
  a: MarkdownLink,
  pre: CodeBlock,
  table: ({ children }) => <div className="nice-scroll overflow-x-auto rounded-md border border-separator"><table>{children}</table></div>,
}

const STYLE = [
  "text-body text-ink wrap-anywhere [&>*+*]:mt-3",
  "[&_h1]:text-title-3 [&_h2]:text-title-3 [&_h3]:text-headline [&_h4]:text-callout [&_h1]:font-semibold [&_h2]:font-semibold [&_h3]:font-semibold [&_h4]:font-semibold [&_:is(h1,h2,h3,h4)]:mt-5 [&_:is(h1,h2,h3,h4):first-child]:mt-0",
  "[&_ul]:list-disc [&_ol]:list-decimal [&_ul]:pl-6 [&_ol]:pl-6 [&_li+li]:mt-1 [&_li>p+p]:mt-2 [&_li>:is(ul,ol)]:mt-1",
  "[&_a]:text-link [&_a]:underline [&_a]:underline-offset-2 [&_strong]:font-semibold",
  "[&_blockquote]:border-l-2 [&_blockquote]:border-separator [&_blockquote]:pl-4 [&_blockquote]:text-ink-secondary [&_hr]:border-separator",
  "[&_:not(pre)>code]:rounded-sm [&_:not(pre)>code]:bg-surface-sunk [&_:not(pre)>code]:px-1 [&_:not(pre)>code]:py-0.5 [&_code]:font-mono [&_code]:text-[0.875em]",
  "[&_table]:w-full [&_table]:text-callout [&_th]:border-b [&_th]:border-separator [&_th]:bg-surface-sunk [&_th]:px-3 [&_th]:py-2 [&_th]:text-left [&_th]:font-semibold [&_td]:border-b [&_td]:border-separator [&_td]:px-3 [&_td]:py-2 [&_tr:last-child_td]:border-b-0",
].join(" ")

export function Markdown({ text, className }: { text: string; className?: string }) {
  return (
    <div className={cn(STYLE, className)}>
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={COMPONENTS}>{text}</ReactMarkdown>
    </div>
  )
}
