import { ChevronLeft, ChevronRight } from "lucide-react"
import { Button } from "../ui/button"

const PAGE_SIZE_FALLBACK = 20

export function Pager({
  page, pages, total, pageSize, onPage,
}: {
  page: number
  pages: number
  total: number
  pageSize: number
  onPage: (page: number) => void
}) {
  if (pages <= 1) return null
  const from = page * pageSize + 1
  const to = Math.min(total, (page + 1) * pageSize)
  return (
    <div className="flex items-center justify-between pt-1 type-meta">
      <span>
        {from}–{to} of {total}
      </span>
      <span className="flex gap-1">
        <Button data-tooltip={page === 0 ? "You are on the first page" : "Show the previous page of results"} size="sm" variant="outline" disabled={page === 0} onClick={() => onPage(page - 1)}>
          <ChevronLeft /> Prev
        </Button>
        <span className="self-center px-2">
          {page + 1} / {pages}
        </span>
        <Button data-tooltip={page >= pages - 1 ? "You are on the last page" : "Show the next page of results"} size="sm" variant="outline" disabled={page >= pages - 1} onClick={() => onPage(page + 1)}>
          Next <ChevronRight />
        </Button>
      </span>
    </div>
  )
}

export const DEFAULT_PAGE_SIZE = PAGE_SIZE_FALLBACK
