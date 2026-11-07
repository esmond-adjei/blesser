import type * as React from "react"
import {
  BookOpen,
  ChevronRight,
  ClipboardList,
  FilePenLine,
  FileText,
  Library,
  Mail,
  Play,
  School,
  UserRound,
  UserRoundSearch,
  type LucideIcon,
} from "lucide-react"
import { Link } from "react-router-dom"
import { cn } from "../../lib/utils"

/** With `to` it's a link (modified clicks open the page), else a button; `active` gets a ring, never a shadow. */
export function RecordCard({
  kind,
  eyebrow,
  label,
  sublabel,
  to,
  onClick,
  tooltip,
  active = false,
  className,
}: {
  kind: RecordKind
  /** What the record is, over its name; the kind's name by default. */
  eyebrow?: string
  label: string
  sublabel?: string | null
  to?: string
  onClick?: (e: React.MouseEvent) => void
  tooltip?: string
  active?: boolean
  className?: string
}) {
  const { icon: Icon, name, shape, wash, tile, ink } = KINDS[kind]
  const classes = cn(
    "group relative flex w-full cursor-pointer items-center gap-3 rounded-lg p-3 text-left shadow-sm transition-[filter,box-shadow] duration-200 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--focus)] motion-reduce:transition-none",
    wash,
    active ? "shadow-none ring-2 ring-tint" : "hover:brightness-[0.98] hover:shadow-none dark:hover:brightness-110",
    className,
  )
  const body = (
    <>
      <span className={cn("g-icon-tile", shape ?? "rounded-[6px]", tile, ink)} aria-hidden>
        <Icon className="size-4" strokeWidth={1.75} />
      </span>
      <span className="min-w-0 flex-1">
        <span className={cn("block type-caption", ink)}>{eyebrow ?? name}</span>
        <span className="block truncate text-sm font-semibold">{label}</span>
        {sublabel && <span className="block truncate type-caption text-label-tertiary">{sublabel}</span>}
      </span>
      <ChevronRight
        className={cn(
          "size-4 shrink-0 transition-transform group-hover:translate-x-0.5 motion-reduce:transition-none",
          active ? "text-tint" : "text-label-tertiary",
        )}
      />
    </>
  )
  return to ? (
    <Link
      to={to}
      onClick={onClick}
      data-tooltip={tooltip}
      data-active={active || undefined}
      aria-current={active || undefined}
      className={classes}
    >
      {body}
    </Link>
  ) : (
    <button
      type="button"
      onClick={onClick}
      data-tooltip={tooltip}
      data-active={active || undefined}
      aria-current={active || undefined}
      className={classes}
    >
      {body}
    </button>
  )
}

export type RecordKind =
  | "program" | "application" | "draft" | "candidate" | "school" | "run" | "professor" | "document" | "paper" | "suggestions"

type KindStyle = {
  icon: LucideIcon
  name: string
  /** The card's light ground, so kinds read before their icon is parsed. */
  wash: string
  tile: string
  ink: string
  /** People and runs are round; paper records keep squarer corners. */
  shape?: string
}

/** The word always names the kind, so colour is a second cue, never the only one. */
const KINDS: Record<RecordKind, KindStyle> = {
  professor: {
    name: "Professor",
    icon: UserRound,
    wash: "bg-teal-50/70 dark:bg-teal-950/40",
    tile: "bg-teal-50 dark:bg-teal-950/50",
    ink: "text-teal-700 dark:text-teal-300",
    shape: "rounded-full",
  },
  candidate: {
    name: "Match",
    icon: UserRoundSearch,
    wash: "bg-rose-50/70 dark:bg-rose-950/40",
    tile: "bg-rose-50 dark:bg-rose-950/50",
    ink: "text-rose-700 dark:text-rose-300",
    shape: "rounded-full",
  },
  program: {
    name: "Programme",
    icon: BookOpen,
    wash: "bg-blue-50/70 dark:bg-blue-950/40",
    tile: "bg-blue-50 dark:bg-blue-950/50",
    ink: "text-blue-700 dark:text-blue-300",
  },
  school: {
    name: "School",
    icon: School,
    wash: "bg-indigo-50/70 dark:bg-indigo-950/40",
    tile: "bg-indigo-50 dark:bg-indigo-950/50",
    ink: "text-indigo-700 dark:text-indigo-300",
  },
  application: {
    name: "Application",
    icon: ClipboardList,
    wash: "bg-emerald-50/70 dark:bg-emerald-950/40",
    tile: "bg-emerald-50 dark:bg-emerald-950/50",
    ink: "text-emerald-700 dark:text-emerald-300",
  },
  draft: {
    name: "Email draft",
    icon: Mail,
    wash: "bg-sky-50/70 dark:bg-sky-950/40",
    tile: "bg-sky-50 dark:bg-sky-950/50",
    ink: "text-sky-700 dark:text-sky-300",
  },
  run: {
    name: "Run",
    icon: Play,
    wash: "bg-violet-50/70 dark:bg-violet-950/40",
    tile: "bg-violet-50 dark:bg-violet-950/50",
    ink: "text-violet-700 dark:text-violet-300",
    shape: "rounded-full",
  },
  document: {
    name: "Document",
    icon: FileText,
    wash: "bg-amber-50/70 dark:bg-amber-950/40",
    tile: "bg-amber-50 dark:bg-amber-950/50",
    ink: "text-amber-700 dark:text-amber-300",
  },
  // Suggested edits belong to a document, so they wear its theme.
  suggestions: {
    name: "Suggestions",
    icon: FilePenLine,
    wash: "bg-amber-50/70 dark:bg-amber-950/40",
    tile: "bg-amber-50 dark:bg-amber-950/50",
    ink: "text-amber-700 dark:text-amber-300",
  },
  paper: {
    name: "Paper",
    icon: Library,
    wash: "bg-fuchsia-50/70 dark:bg-fuchsia-950/40",
    tile: "bg-fuchsia-50 dark:bg-fuchsia-950/50",
    ink: "text-fuchsia-700 dark:text-fuchsia-300",
  },
}
