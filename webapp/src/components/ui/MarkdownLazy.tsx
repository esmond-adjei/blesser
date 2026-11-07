/* eslint-disable react/only-export-components -- lazy wrapper ships with its preload hook */
import * as React from "react"
import { Skeleton } from "./feedback"
import type { CitationIndex } from "../../lib/citations"

const load = () => import("./Markdown")
const LazyMarkdown = React.lazy(load)

/** Fetch the renderer early (e.g. when chat opens) so the first message doesn't flash a skeleton. Safe to repeat. */
export function preloadMarkdown() {
  void load()
}

/** Code-split `react-markdown` wrapper so the renderer stays out of the initial bundle until first use. */
export function Markdown({
  text,
  className,
  citations,
}: {
  text: string
  className?: string
  citations?: CitationIndex
}) {
  return (
    <React.Suspense fallback={<Skeleton className="h-16 w-full" />}>
      <LazyMarkdown text={text} className={className} citations={citations} />
    </React.Suspense>
  )
}
