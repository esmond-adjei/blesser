import * as React from "react"
import {
  Bold,
  ChevronDown,
  Columns2,
  Ellipsis,
  FileStack,
  Italic,
  Link2,
  List,
  ListOrdered,
  ListTree,
  Minus,
  Redo2,
  Sparkles,
  Table2,
  Underline,
  Undo2,
} from "lucide-react"
import { cn } from "../../lib/utils"
import { Menu, MenuItem, MenuSeparator } from "../ui/menu"
import type { BlockStyle, EditorCommand } from "./editor/format"
import type { TableAction } from "./editor/tables"
import type { EditorStatus } from "./editor/MarkdownEditor"
import { withShortcut } from "./editor/shortcuts"

const STYLES: { value: BlockStyle; label: string }[] = [
  { value: "normal", label: "Normal text" },
  { value: "title", label: "Title" },
  { value: "h1", label: "Heading 1" },
  { value: "h2", label: "Heading 2" },
  { value: "h3", label: "Heading 3" },
]

function ToolButton({
  title,
  onClick,
  active,
  disabled,
  badge,
  children,
  className,
}: {
  title: string
  onClick?: () => void
  active?: boolean
  disabled?: boolean
  badge?: number
  children: React.ReactNode
  className?: string
}) {
  return (
    <button
      type="button"
      data-tooltip={title}
      aria-label={title}
      aria-pressed={active}
      disabled={disabled}
      // Keep the editor's selection: the toolbar acts on it.
      onMouseDown={(e) => e.preventDefault()}
      onClick={onClick}
      className={cn(
        "relative inline-flex size-8 shrink-0 cursor-pointer items-center justify-center rounded-md text-muted-foreground transition-colors duration-150 hover:bg-muted hover:text-foreground disabled:cursor-not-allowed disabled:opacity-40 [&_svg]:size-4",
        active && "bg-primary/10 text-foreground dark:bg-primary/20",
        className,
      )}
    >
      {children}
      {badge ? (
        <span className="absolute -right-0.5 -top-0.5 min-w-4 rounded-full bg-primary px-1 text-xs font-semibold leading-4 text-primary-foreground">
          {badge}
        </span>
      ) : null}
    </button>
  )
}

function Divider({ className }: { className?: string }) {
  return <span aria-hidden className={cn("mx-1 h-5 w-px shrink-0 bg-border", className)} />
}

const GRID_ROWS = 8
const GRID_COLS = 8

/** A direct child of Menu, which passes `onSelect` to close itself. */
function TableSizePicker({ onPick, onSelect }: { onPick: (rows: number, cols: number) => void; onSelect?: () => void }) {
  const [size, setSize] = React.useState({ rows: 3, cols: 3 })
  const pick = (rows: number, cols: number) => {
    onPick(rows, cols)
    onSelect?.()
  }
  return (
    <div className="p-1.5">
      <div
        role="grid"
        aria-label="Table size"
        className="grid w-max gap-0.5"
        style={{ gridTemplateColumns: `repeat(${GRID_COLS}, 1rem)` }}
        onMouseDown={(e) => e.preventDefault()}
      >
        {Array.from({ length: GRID_ROWS * GRID_COLS }, (_, i) => {
          const rows = Math.floor(i / GRID_COLS) + 1
          const cols = (i % GRID_COLS) + 1
          const on = rows <= size.rows && cols <= size.cols
          return (
            <button
              key={i}
              type="button"
              role="gridcell"
              aria-label={`${rows} by ${cols}`}
              onMouseEnter={() => setSize({ rows, cols })}
              onFocus={() => setSize({ rows, cols })}
              onClick={() => pick(rows, cols)}
              className={cn(
                "size-4 cursor-pointer rounded-[3px] border transition-colors duration-75 focus:outline-none",
                on ? "border-primary/70 bg-primary/20" : "border-border bg-background hover:border-foreground/30",
              )}
            />
          )
        })}
      </div>
      <p className="mt-2 text-center text-xs tabular-nums text-muted-foreground" aria-live="polite">
        {size.rows} × {size.cols}
      </p>
    </div>
  )
}

function TableMenu({ exec, disabled }: { exec: (cmd: EditorCommand) => void; disabled: boolean }) {
  const run = (action: TableAction) => () => exec({ type: "tableEdit", action })
  return (
    <Menu
      label="Table"
      trigger={
        <button
          type="button"
          data-tooltip="Table rows and columns"
          aria-label="Table rows and columns"
          disabled={disabled}
          onMouseDown={(e) => e.preventDefault()}
          className="inline-flex h-8 shrink-0 cursor-pointer items-center gap-1 rounded-md bg-primary/10 px-2 text-sm text-foreground transition-colors duration-150 hover:bg-primary/15 disabled:opacity-40 dark:bg-primary/20 [&_svg]:size-4"
        >
          <Table2 /> <span className="hidden lg:inline">Table</span>
          <ChevronDown className="size-3.5" />
        </button>
      }
    >
      <MenuItem onSelect={run("rowAbove")}>Insert row above</MenuItem>
      <MenuItem onSelect={run("rowBelow")}>Insert row below</MenuItem>
      <MenuItem onSelect={run("colLeft")}>Insert column left</MenuItem>
      <MenuItem onSelect={run("colRight")}>Insert column right</MenuItem>
      <MenuSeparator />
      <MenuItem onSelect={run("deleteRow")}>Delete row</MenuItem>
      <MenuItem onSelect={run("deleteCol")}>Delete column</MenuItem>
      <MenuItem destructive onSelect={run("deleteTable")}>Delete table</MenuItem>
      <MenuSeparator />
      <MenuLabel>Tab and Shift+Tab move between cells; Enter adds a row.</MenuLabel>
    </Menu>
  )
}

function MenuLabel({ children }: { children: React.ReactNode; onSelect?: () => void }) {
  return <div className="px-2.5 pb-1 pt-2 text-xs font-medium text-muted-foreground">{children}</div>
}

/** Below `sm` the less used controls fold into a "More" menu, so the row never scrolls. */
export function DocumentToolbar({
  exec,
  onLink,
  status,
  disabled,
  outlineOpen,
  onToggleOutline,
  pagesOn,
  onTogglePages,
  panelOpen,
  onTogglePanel,
  pending,
  compare,
  onToggleCompare,
}: {
  exec: (cmd: EditorCommand) => void
  onLink: () => void
  status: EditorStatus
  disabled: boolean
  outlineOpen: boolean
  onToggleOutline: () => void
  pagesOn: boolean
  onTogglePages: () => void
  panelOpen: boolean
  onTogglePanel: () => void
  pending: number
  compare: boolean | null
  onToggleCompare: () => void
}) {
  const off = disabled
  const { marks } = status
  return (
    <div
      role="toolbar"
      aria-label="Formatting"
      className="mx-2 mb-2 flex h-10 flex-none items-center gap-0.5 overflow-hidden whitespace-nowrap rounded-lg p-2 sm:mx-3 dark:bg-muted/50"
    >
      <span className="hidden items-center gap-0.5 sm:flex">
        <ToolButton title={withShortcut("Undo", "undo")} disabled={off || !status.canUndo} onClick={() => exec({ type: "undo" })}>
          <Undo2 />
        </ToolButton>
        <ToolButton title={withShortcut("Redo", "redo")} disabled={off || !status.canRedo} onClick={() => exec({ type: "redo" })}>
          <Redo2 />
        </ToolButton>
        <Divider />
      </span>
      <select
        aria-label="Paragraph style"
        data-tooltip="Paragraph style"
        disabled={off}
        value={status.block}
        onChange={(e) => exec({ type: "block", style: e.target.value as BlockStyle })}
        className="h-8 w-28 shrink-0 cursor-pointer rounded-md border border-transparent bg-transparent px-1.5 text-sm hover:bg-accent focus:border-input focus:outline-none disabled:opacity-40 sm:w-32"
      >
        {STYLES.map((s) => (
          <option key={s.value} value={s.value}>
            {s.label}
          </option>
        ))}
        {status.block === "other" && (
          <option value="other" disabled>
            Smaller heading
          </option>
        )}
      </select>
      <Divider />
      <ToolButton title={withShortcut("Bold", "bold")} active={marks.bold} disabled={off} onClick={() => exec({ type: "bold" })}>
        <Bold />
      </ToolButton>
      <ToolButton title={withShortcut("Italic", "italic")} active={marks.italic} disabled={off} onClick={() => exec({ type: "italic" })}>
        <Italic />
      </ToolButton>
      <ToolButton title={withShortcut("Underline", "underline")} active={marks.underline} disabled={off} onClick={() => exec({ type: "underline" })}>
        <Underline />
      </ToolButton>
      <Divider className="hidden sm:block" />
      <ToolButton title={withShortcut("Link", "link")} active={marks.link} disabled={off} onClick={onLink}>
        <Link2 />
      </ToolButton>
      <span className="hidden items-center gap-0.5 sm:flex">
        <Divider />
        <ToolButton title={withShortcut("Bulleted list", "bullets")} disabled={off} onClick={() => exec({ type: "list", ordered: false })}>
          <List />
        </ToolButton>
        <ToolButton title={withShortcut("Numbered list", "numbers")} disabled={off} onClick={() => exec({ type: "list", ordered: true })}>
          <ListOrdered />
        </ToolButton>
        <Divider />
        <Menu
          label="Insert table"
          className="w-auto"
          trigger={
            <ToolButton title="Insert table" disabled={off}>
              <Table2 />
            </ToolButton>
          }
        >
          <TableSizePicker onPick={(rows, cols) => exec({ type: "table", rows, cols })} />
        </Menu>
        <ToolButton title="Horizontal line" disabled={off} onClick={() => exec({ type: "rule" })}>
          <Minus />
        </ToolButton>
      </span>
      {status.inTable && (
        <span className="ml-1 hidden sm:flex">
          <TableMenu exec={exec} disabled={off} />
        </span>
      )}

      <span className="min-w-1 flex-1" />

      <span className="hidden items-center gap-0.5 sm:flex">
        <ToolButton title={outlineOpen ? "Hide outline" : "Show outline"} active={outlineOpen} onClick={onToggleOutline}>
          <ListTree />
        </ToolButton>
        <ToolButton title={pagesOn ? "Hide page breaks" : "Show page breaks"} active={pagesOn} onClick={onTogglePages}>
          <FileStack />
        </ToolButton>
        {compare !== null && (
          <ToolButton title={compare ? "Stop comparing" : "Compare with the base"} active={compare} onClick={onToggleCompare}>
            <Columns2 />
          </ToolButton>
        )}
        <ToolButton
          title={panelOpen ? "Hide suggestions" : "Show suggestions"}
          active={panelOpen}
          badge={panelOpen ? undefined : pending}
          onClick={onTogglePanel}
        >
          <Sparkles />
        </ToolButton>
      </span>

      {/* Phones: what doesn't fit the row. */}
      <span className="sm:hidden">
        <Menu
          label="More tools"
          trigger={
            <ToolButton title="More">
              <Ellipsis />
            </ToolButton>
          }
        >
          <MenuItem disabled={off || !status.canUndo} onSelect={() => exec({ type: "undo" })}>
            <Undo2 /> Undo
          </MenuItem>
          <MenuItem disabled={off || !status.canRedo} onSelect={() => exec({ type: "redo" })}>
            <Redo2 /> Redo
          </MenuItem>
          <MenuItem disabled={off} onSelect={() => exec({ type: "list", ordered: false })}>
            <List /> Bulleted list
          </MenuItem>
          <MenuItem disabled={off} onSelect={() => exec({ type: "list", ordered: true })}>
            <ListOrdered /> Numbered list
          </MenuItem>
          <MenuItem disabled={off} onSelect={() => exec({ type: "table", rows: 3, cols: 3 })}>
            <Table2 /> Insert table
          </MenuItem>
          {status.inTable ? (
            <MenuItem disabled={off} onSelect={() => exec({ type: "tableEdit", action: "rowBelow" })}>
              <Table2 /> Insert row below
            </MenuItem>
          ) : null}
          <MenuItem disabled={off} onSelect={() => exec({ type: "rule" })}>
            <Minus /> Horizontal line
          </MenuItem>
          <MenuSeparator />
          <MenuItem onSelect={onToggleOutline}>
            <ListTree /> {outlineOpen ? "Hide outline" : "Show outline"}
          </MenuItem>
          <MenuItem onSelect={onTogglePages}>
            <FileStack /> {pagesOn ? "Hide page breaks" : "Show page breaks"}
          </MenuItem>
          {compare !== null ? (
            <MenuItem onSelect={onToggleCompare}>
              <Columns2 /> {compare ? "Stop comparing" : "Compare with the base"}
            </MenuItem>
          ) : null}
          <MenuItem onSelect={onTogglePanel}>
            <Sparkles /> {panelOpen ? "Hide suggestions" : `Suggestions${pending ? ` (${pending})` : ""}`}
          </MenuItem>
        </Menu>
      </span>

    </div>
  )
}
