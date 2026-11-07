import * as React from "react"
import { useQuery } from "@tanstack/react-query"
import * as api from "../../lib/api"
import { cn } from "../../lib/utils"
import { Markdown } from "../ui/MarkdownLazy"

/** A4 at 96dpi, the size `.doc-sheet` lays the page out at. */
const PAGE_WIDTH = 794

/** Where a thumbnail's text comes from: a saved CV (fetched once it
 * scrolls into view, cached per edit) or text already on this device. */
export type ThumbSource =
  | { kind: "doc" | "version"; id: string; stamp: string | null }
  | { kind: "text"; text: string }

/** A sticky note's heading (its first line, when that is a heading) and
 * the plain text after it. */
function briefPreview(markdown: string): { heading: string | null; text: string } {
  const first = markdown.trimStart().match(/^#{1,6}\s+(.+)\n?/)
  const text = (first ? markdown.trimStart().slice(first[0].length) : markdown)
    .replace(/^#{1,6}\s+/gm, "")
    .replace(/^\s*[-*+]\s+/gm, "")
    .replace(/\[([^\]]+)\]\([^)]+\)/g, "$1")
    .replace(/[`*_>#]/g, "")
    .replace(/\s+/g, " ")
    .trim()
  return {
    heading: first ? first[1].replace(/[`*_]/g, "").trim() : null,
    text: text.length > 150 ? `${text.slice(0, 147).trimEnd()}…` : text,
  }
}

/** True once the element has come near the viewport (and stays true). */
function useSeen(ref: React.RefObject<HTMLElement | null>): boolean {
  // No observer to ask (old browsers, tests): render straight away.
  const [seen, setSeen] = React.useState(() => typeof IntersectionObserver === "undefined")
  React.useEffect(() => {
    const el = ref.current
    if (seen || !el) return
    const io = new IntersectionObserver(
      (entries) => {
        if (entries.some((e) => e.isIntersecting)) {
          setSeen(true)
          io.disconnect()
        }
      },
      { rootMargin: "240px" },
    )
    io.observe(el)
    return () => io.disconnect()
  }, [ref, seen])
  return seen
}

function useScale(ref: React.RefObject<HTMLElement | null>): number {
  const [scale, setScale] = React.useState(0)
  React.useLayoutEffect(() => {
    const el = ref.current
    if (!el) return
    const measure = () => setScale(el.clientWidth / PAGE_WIDTH)
    measure()
    if (typeof ResizeObserver === "undefined") return
    const ro = new ResizeObserver(measure)
    ro.observe(el)
    return () => ro.disconnect()
  }, [ref])
  return scale
}

/** Memoized so a re-render of the list never re-parses the Markdown. */
const Page = React.memo(function Page({ text, scale }: { text: string; scale: number }) {
  return (
    <div className="doc-sheet origin-top-left" style={{ transform: `scale(${scale})` }}>
      <Markdown text={text} />
    </div>
  )
})

function Lines() {
  return (
    <div className="flex h-full flex-col gap-[5%] p-[9%] pt-[8%]" aria-hidden>
      <span className="h-[3%] w-1/2 rounded-sm bg-current opacity-15" />
      <span className="h-[1.5%] w-1/3 rounded-sm bg-current opacity-10" />
      <span className="mt-[4%] h-[1.5%] w-full rounded-sm bg-current opacity-10" />
      <span className="h-[1.5%] w-11/12 rounded-sm bg-current opacity-10" />
      <span className="h-[1.5%] w-4/5 rounded-sm bg-current opacity-10" />
    </div>
  )
}

/** A blank one shows what it is for. */
function Sticky({ text, tone }: { text: string; tone: "interest" | "note" }) {
  const { heading, text: body } = briefPreview(text)
  const blank = !heading && !body
  return (
    <div className="relative h-full p-[11%] pt-[13%]">
      {(heading || blank) && (
        <p className="mb-[8%] line-clamp-2 text-[clamp(9px,3.5vw,13px)] font-semibold leading-tight text-label">
          {heading ?? (tone === "note" ? "Quick note" : "Research focus")}
        </p>
      )}
      <p className="line-clamp-6 text-[clamp(8px,2.9vw,11px)] leading-relaxed text-label-secondary">
        {body || (blank ? (tone === "note" ? "A short note to keep here." : "A brief note about the work you want to pursue.") : "")}
      </p>
    </div>
  )
}

/** Nothing is fetched or rendered until the card nears the viewport. */
export function DocumentThumb({ source, className, variant = "page", stickyTone = "interest", compactPage = false }: { source: ThumbSource; className?: string; variant?: "page" | "sticky"; stickyTone?: "interest" | "note"; compactPage?: boolean }) {
  const box = React.useRef<HTMLDivElement | null>(null)
  const seen = useSeen(box)
  const scale = useScale(box)
  const saved = source.kind === "text" ? null : source
  const q = useQuery({
    queryKey: ["document-thumb", saved?.kind, saved?.id, saved?.stamp],
    queryFn: async () =>
      saved?.kind === "version" ? (await api.getCvVersion(saved.id)).markdown : (await api.getCvDocument(saved!.id)).markdown,
    enabled: seen && saved !== null,
    staleTime: Infinity,
  })
  const text = source.kind === "text" ? source.text : q.data
  return (
    <div
      ref={box}
      aria-hidden
      className={cn(
        "pointer-events-none relative select-none overflow-hidden",
        // A card grid mixes kinds, so a sticky note takes a page's shape
        // there. Pages follow the theme, as the sheet inside them does.
        compactPage ? "aspect-4/5" : variant === "sticky" ? "aspect-square" : "aspect-[1/1.414]",
        variant === "sticky"
          ? "bg-surface text-label"
          : "bg-white text-black dark:bg-surface dark:text-label",
        className,
      )}
    >
      {seen && text !== undefined ? (
        variant === "sticky" ? (
          <Sticky text={text} tone={stickyTone} />
        ) : scale > 0 ? (
          <Page text={text} scale={scale} />
        ) : (
          <Lines />
        )
      ) : (
        <Lines />
      )}
      {variant === "sticky" && <span className={cn("absolute bottom-0 right-0 border-b-14 border-l-14 border-b-canvas transition-[border-width] duration-200 ease-out group-hover:border-b-20 group-hover:border-l-20 group-has-[a:focus-visible]:border-b-20 group-has-[a:focus-visible]:border-l-20 group-focus-visible:border-b-20 group-focus-visible:border-l-20 motion-reduce:transition-none", "border-l-fill")} />}
    </div>
  )
}
