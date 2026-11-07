import * as React from "react"
import { Loader2 } from "lucide-react"

/** End-of-list sentinel for infinite scroll: asks for the next page as it
 * nears the visible area of whatever scrolls the list. */
export function LoadMore({
  hasMore,
  loading,
  onLoad,
}: {
  hasMore: boolean
  loading: boolean
  onLoad: () => void
}) {
  const ref = React.useRef<HTMLDivElement>(null)
  React.useEffect(() => {
    const el = ref.current
    if (!el || !hasMore || loading || typeof IntersectionObserver === "undefined") return
    const io = new IntersectionObserver(
      (entries) => {
        if (entries[0]?.isIntersecting) onLoad()
      },
      { rootMargin: "200px" },
    )
    io.observe(el)
    return () => io.disconnect()
  }, [hasMore, loading, onLoad])

  if (!hasMore) return null
  return (
    <div ref={ref} aria-busy={loading} className="flex h-8 items-center justify-center text-muted-foreground">
      {loading && <Loader2 aria-label="Loading more" className="size-3.5 animate-spin" />}
    </div>
  )
}
