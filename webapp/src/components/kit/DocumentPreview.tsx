import * as React from "react"
import { FileImage, FileSpreadsheet, FileText, Presentation, type LucideIcon } from "lucide-react"
import { cn } from "@blesser/ui"
import { fileFormat, formatLabel, type DocumentExcerpt, type FileFormat } from "../../lib/kit"
import { useDocumentPreview } from "../../lib/kitApi"
import type { KitDocument } from "../../lib/kitTypes"

const ICONS: Record<FileFormat, LucideIcon> = { pdf: FileText, word: FileText, slides: Presentation, sheet: FileSpreadsheet, image: FileImage, file: FileText }

/** True once the element has come within a screen of the viewport, so off-screen previews don't load. */
function useNearViewport(ref: React.RefObject<HTMLElement | null>) {
  const [near, setNear] = React.useState(() => typeof IntersectionObserver === "undefined")
  React.useEffect(() => {
    const node = ref.current
    if (near || !node) return
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((e) => e.isIntersecting)) {
          setNear(true)
          observer.disconnect()
        }
      },
      { rootMargin: "100% 0px" },
    )
    observer.observe(node)
    return () => observer.disconnect()
  }, [near, ref])
  return near
}

/**
 * The file's first page, picture or opening lines. `size="card"` fills a 4:3 tile;
 * `size="full"` is the larger view in the preview dialog.
 */
export function DocumentPreview({ doc, size = "card", className }: { doc: KitDocument; size?: "card" | "full"; className?: string }) {
  const ref = React.useRef<HTMLDivElement | null>(null)
  const near = useNearViewport(ref)
  const preview = useDocumentPreview(doc.id, near)
  const url = preview.data?.type === "image" ? preview.data.url : null
  const [broken, setBroken] = React.useState(false)
  const format = fileFormat(doc.content_type, doc.filename)
  const full = size === "full"
  const data = preview.data

  let body: React.ReactNode
  if (!near || preview.isPending) {
    body = <div className="absolute inset-0 animate-pulse bg-surface-sunk motion-reduce:animate-none" />
  } else if (url && !broken) {
    // Photos fill the tile. Pages sit like paper with their top showing. Slides fit whole.
    const photo = format === "image"
    const slide = format === "slides"
    body = full ? (
      <img src={url} alt="" decoding="async" onError={() => setBroken(true)} className={cn("mx-auto block max-h-[60vh] w-auto max-w-full", !photo && "border border-separator")} />
    ) : photo || slide ? (
      <img src={url} alt="" decoding="async" onError={() => setBroken(true)} className={cn("absolute inset-0 size-full", photo ? "object-cover" : "object-contain p-3")} />
    ) : (
      <Paper>
        <img src={url} alt="" decoding="async" onError={() => setBroken(true)} className="size-full object-cover object-top" />
      </Paper>
    )
  } else if (data && (data.type === "text" || data.type === "table")) {
    body = full ? <Excerpt excerpt={data} full /> : <Paper><Excerpt excerpt={data} /></Paper>
  } else {
    const Icon = ICONS[format]
    body = (
      <div className={cn("flex flex-col items-center justify-center gap-2 text-ink-secondary", full ? "py-16" : "absolute inset-0")}>
        <Icon className="size-7" strokeWidth={1.5} aria-hidden="true" />
        <span className="text-footnote">{formatLabel(doc.content_type, doc.filename)}</span>
      </div>
    )
  }

  return (
    <div ref={ref} className={cn("relative overflow-hidden bg-surface-sunk", full ? "rounded-md" : "aspect-[4/3]", className)}>
      {body}
    </div>
  )
}

/** A page peeking up from the bottom of the tile. */
function Paper({ children }: { children: React.ReactNode }) {
  return <div className="absolute inset-x-4 top-4 -bottom-px overflow-hidden rounded-t-sm border border-b-0 border-separator bg-surface shadow-elevation-1">{children}</div>
}

function Excerpt({ excerpt, full = false }: { excerpt: DocumentExcerpt; full?: boolean }) {
  if (excerpt.type === "text") {
    return (
      <div className={cn("space-y-1.5 text-caption text-ink-secondary", full ? "bg-surface p-5" : "h-full p-3 [mask-image:linear-gradient(to_bottom,black_60%,transparent)]")}>
        {excerpt.paragraphs.map((p, i) => (
          <p key={i} className={cn(i === 0 && "font-semibold text-ink", !full && "line-clamp-3")}>{p}</p>
        ))}
      </div>
    )
  }
  return (
    <div className={cn(full ? "overflow-x-auto bg-surface" : "h-full [mask-image:linear-gradient(to_bottom,black_60%,transparent)]")}>
      <table className="w-full border-collapse text-left text-caption text-ink-secondary tabular-nums">
        <tbody>
          {excerpt.rows.map((row, r) => (
            <tr key={r} className={cn("border-b border-separator", r === 0 && "font-semibold text-ink")}>
              {row.map((cell, c) => (
                <td key={c} className={cn("px-2 py-1", full ? "whitespace-nowrap" : "max-w-24 truncate")}>{cell}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
