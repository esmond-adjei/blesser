import * as React from "react"
import { ChevronsDownUp, ChevronsUpDown } from "lucide-react"
import { taskLabel } from "../../lib/taskTrace"
import type { Task } from "../../lib/types"
import { cn } from "../../lib/utils"
import { TaskStatusSquare } from "../cards/TaskStatusSquare"

type OutlineTask = Pick<Task, "id" | "status" | "task_type" | "target_name">

function jumpTo(id: string) {
  document.getElementById(`task-${id}`)?.scrollIntoView({ behavior: "smooth", block: "start" })
}

/** The task whose card is nearest the top of the view; re-observes when the loaded list changes. */
function useTaskInView(ids: string[]) {
  const [inView, setInView] = React.useState<string | null>(null)
  const key = ids.join(",")
  React.useEffect(() => {
    const seen = new Map<string, number>()
    const io = new IntersectionObserver(
      (entries) => {
        for (const e of entries) {
          const id = e.target.id.slice("task-".length)
          if (e.isIntersecting) seen.set(id, e.boundingClientRect.top)
          else seen.delete(id)
        }
        let best: [string, number] | null = null
        for (const entry of seen) if (!best || entry[1] < best[1]) best = entry
        setInView(best?.[0] ?? null)
      },
      { rootMargin: "-80px 0px -40% 0px" },
    )
    for (const id of key ? key.split(",") : []) {
      const el = document.getElementById(`task-${id}`)
      if (el) io.observe(el)
    }
    return () => io.disconnect()
  }, [key])
  return inView
}

/** A labelled list in the page's margin ("list"), or a strip of status squares above the cards where there is no room ("strip"). */
export function TasksOutline({
  variant,
  className,
  tasks,
  allCollapsed,
  onCollapseAll,
}: {
  variant: "list" | "strip"
  className?: string
  tasks: OutlineTask[]
  allCollapsed: boolean
  onCollapseAll: (collapse: boolean) => void
}) {
  if (tasks.length < 2) return null

  return (
    // The wheel holds still in the margin's middle (fixed, left where the
    // margin column puts it) and only turns; the strip rides the sticky header.
    <nav aria-label="Tasks outline" className={cn(variant === "list" && "fixed top-1/2 z-10 w-56 -translate-y-1/2", className)}>
      {variant === "strip" ? (
        <TasksStrip tasks={tasks} />
      ) : (
        <TasksWheel tasks={tasks} allCollapsed={allCollapsed} onCollapseAll={onCollapseAll} />
      )}
    </nav>
  )
}

function TasksStrip({ tasks }: { tasks: OutlineTask[] }) {
  const inView = useTaskInView(tasks.map((t) => t.id))
  return (
    <div className="flex max-h-fit flex-wrap gap-1">
      {tasks.map((t) => (
        <button
          key={t.id}
          type="button"
          onClick={() => jumpTo(t.id)}
          aria-label={`${taskLabel(t.task_type, t.target_name)} (${t.status})`}
          data-tooltip={`${taskLabel(t.task_type, t.target_name)}, ${t.status}`}
          className={cn("cursor-pointer rounded-xs p-0.5", inView === t.id && "ring-2 ring-ring")}
        >
          <TaskStatusSquare status={t.status} working className="block size-3" />
        </button>
      ))}
    </div>
  )
}

// The wheel's rows: evenly spaced, HALF_ROWS either side of the centre
// row, fading out into the top and bottom edges.
const ROW = 30
const HALF_ROWS = 4
const HEIGHT = (2 * HALF_ROWS + 1) * ROW

/** Fractional card index under the reading line (3.4 = 40% from card 3 to 4); near the page bottom the line slides down so the last cards reach the centre. */
function scrollPosition(els: HTMLElement[], scroller: HTMLElement | null): number {
  if (!els.length) return 0
  const top = scroller?.getBoundingClientRect().top ?? 0
  const view = scroller?.clientHeight ?? window.innerHeight
  const left = scroller ? scroller.scrollHeight - scroller.clientHeight - scroller.scrollTop : 0
  const ramp = view / 2
  const end = left < ramp ? 1 - left / ramp : 0
  const line = top + 96 + end * (view * 0.6 - 96)
  const tops = els.map((el) => el.getBoundingClientRect().top - line)
  let i = -1
  while (i + 1 < tops.length && tops[i + 1] <= 0) i++
  if (i < 0) return 0
  if (i === tops.length - 1) return i
  return i + Math.min(1, -tops[i] / (tops[i + 1] - tops[i]))
}

function scrollParent(el: HTMLElement | null): HTMLElement | null {
  for (let p = el?.parentElement; p; p = p.parentElement) {
    if (/(auto|scroll)/.test(getComputedStyle(p).overflowY)) return p
  }
  return null
}

/** Turns with the page; scrolling over the wheel turns it alone, to browse, until the next page scroll. */
function TasksWheel({
  tasks,
  allCollapsed,
  onCollapseAll,
}: {
  tasks: OutlineTask[]
  allCollapsed: boolean
  onCollapseAll: (collapse: boolean) => void
}) {
  const rows = React.useRef<(HTMLLIElement | null)[]>([])
  const wheel = React.useRef<HTMLOListElement | null>(null)
  const [active, setActive] = React.useState(0)
  const key = tasks.map((t) => t.id).join(",")
  const Toggle = allCollapsed ? ChevronsUpDown : ChevronsDownUp

  React.useEffect(() => {
    const ids = key ? key.split(",") : []
    const els = ids.map((id) => document.getElementById(`task-${id}`)).filter((el): el is HTMLElement => !!el)
    const scroller = scrollParent(els[0] ?? null)
    let frame = 0
    // Where the wheel has been turned to by hand, while browsing; null
    // when it follows the page.
    let browse: number | null = null
    let pagePos = 0
    let snapTimer = 0
    let snapFrame = 0
    const paint = () => {
      frame = 0
      pagePos = scrollPosition(els, scroller)
      const pos = browse ?? pagePos
      rows.current.forEach((li, i) => {
        if (!li) return
        const d = i - pos
        li.style.visibility = Math.abs(d) > HALF_ROWS + 1 ? "hidden" : ""
        li.style.transform = `translateY(${d * ROW - ROW / 2}px)`
      })
      setActive(Math.round(pagePos))
    }
    const schedule = () => {
      if (!frame) frame = requestAnimationFrame(paint)
    }
    const stopBrowsing = () => {
      clearTimeout(snapTimer)
      cancelAnimationFrame(snapFrame)
      browse = null
    }
    const onPageScroll = () => {
      // Our own wheel never scrolls the page, so any page scroll means the
      // reader moved on: follow it again.
      stopBrowsing()
      schedule()
    }
    const snap = () => {
      if (browse === null) return
      const from = browse
      const to = Math.round(from)
      const start = performance.now()
      const step = (now: number) => {
        const t = Math.min(1, (now - start) / 180)
        browse = from + (to - from) * (1 - (1 - t) ** 3)
        paint()
        if (t < 1) snapFrame = requestAnimationFrame(step)
      }
      snapFrame = requestAnimationFrame(step)
    }
    const turn = (by: number) => {
      clearTimeout(snapTimer)
      cancelAnimationFrame(snapFrame)
      browse = Math.max(0, Math.min(els.length - 1, (browse ?? pagePos) + by))
      schedule()
    }
    const onWheel = (e: WheelEvent) => {
      e.preventDefault()
      turn((e.deltaMode === 1 ? e.deltaY * ROW : e.deltaMode === 2 ? e.deltaY * HEIGHT : e.deltaY) / ROW)
      snapTimer = window.setTimeout(snap, 140)
    }
    let touchY: number | null = null
    const onTouchStart = (e: TouchEvent) => { touchY = e.touches[0]?.clientY ?? null }
    const onTouchMove = (e: TouchEvent) => {
      const y = e.touches[0]?.clientY
      if (touchY === null || y === undefined) return
      e.preventDefault()
      turn((touchY - y) / ROW)
      touchY = y
    }
    const onTouchEnd = () => {
      touchY = null
      snap()
    }
    const ol = wheel.current
    ol?.addEventListener("wheel", onWheel, { passive: false })
    ol?.addEventListener("touchstart", onTouchStart, { passive: true })
    ol?.addEventListener("touchmove", onTouchMove, { passive: false })
    ol?.addEventListener("touchend", onTouchEnd)
    paint()
    // Cards fold and unfold without the page scrolling, so watch their size too.
    const ro = new ResizeObserver(schedule)
    for (const el of els) ro.observe(el)
    const target = scroller ?? window
    target.addEventListener("scroll", onPageScroll, { passive: true })
    window.addEventListener("resize", schedule)
    return () => {
      cancelAnimationFrame(frame)
      stopBrowsing()
      ro.disconnect()
      ol?.removeEventListener("wheel", onWheel)
      ol?.removeEventListener("touchstart", onTouchStart)
      ol?.removeEventListener("touchmove", onTouchMove)
      ol?.removeEventListener("touchend", onTouchEnd)
      target.removeEventListener("scroll", onPageScroll)
      window.removeEventListener("resize", schedule)
    }
  }, [key])

  const go = (i: number) => {
    const t = tasks[Math.max(0, Math.min(tasks.length - 1, i))]
    if (!t) return
    jumpTo(t.id)
    rows.current[tasks.indexOf(t)]?.querySelector("button")?.focus({ preventScroll: true })
  }
  const onKeyDown = (e: React.KeyboardEvent) => {
    const to = { ArrowUp: active - 1, ArrowDown: active + 1, Home: 0, End: tasks.length - 1 }[e.key]
    if (to === undefined) return
    e.preventDefault()
    go(to)
  }

  return (
    <div>
      <div className="relative" style={{ height: HEIGHT }}>
        <ol
          ref={wheel}
          onKeyDown={onKeyDown}
          className="absolute inset-0 overflow-hidden"
          style={{
            maskImage: "linear-gradient(to bottom, transparent, black 30%, black 70%, transparent)",
            WebkitMaskImage: "linear-gradient(to bottom, transparent, black 30%, black 70%, transparent)",
          }}
        >
          {tasks.map((t, i) => (
            <li
              key={t.id}
              ref={(el) => { rows.current[i] = el }}
              className="absolute inset-x-0 top-1/2 will-change-transform"
              style={{ height: ROW, visibility: "hidden" }}
            >
              <button
                type="button"
                onClick={() => go(i)}
                tabIndex={i === active ? 0 : -1}
                aria-current={i === active ? "location" : undefined}
                data-tooltip={`${taskLabel(t.task_type, t.target_name)}, ${t.status}`}
                className={cn(
                  "flex h-full w-full cursor-pointer items-center gap-2 rounded-md px-2 text-left text-sm text-muted-foreground transition-colors hover:text-foreground",
                  i === active && "font-medium text-foreground",
                )}
              >
                <TaskStatusSquare status={t.status} working className="size-2.5 shrink-0" />
                <span className="min-w-0 flex-1 truncate">{t.target_name || taskLabel(t.task_type, "")}</span>
              </button>
            </li>
          ))}
        </ol>
      </div>
      <button
        type="button"
        onClick={() => onCollapseAll(!allCollapsed)}
        className="mt-1 flex cursor-pointer items-center gap-1 rounded-md px-2 py-1 text-xs text-muted-foreground hover:bg-accent hover:text-foreground"
      >
        <Toggle aria-hidden className="size-3.5" /> {allCollapsed ? "Expand all" : "Collapse all"}
      </button>
    </div>
  )
}
