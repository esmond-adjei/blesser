import * as React from "react"
import { ArrowLeft, FileText, FolderInput, Save, UserRoundSearch } from "lucide-react"
import type { DocumentFolder } from "../../lib/types"
import { cn } from "../../lib/utils"
import { AccountMenu } from "../layout/AccountMenu"
import { Button } from "../ui/button"
import { Menu, MenuItem, MenuSeparator } from "../ui/menu"
import type { BlockStyle, EditorCommand } from "./editor/format"
import { SHORTCUTS, shortcutLabel } from "./editor/shortcuts"

type ShortcutName = keyof typeof SHORTCUTS

export type ExportChoice = "pdf" | "docx" | "md" | "txt" | "original" | "copy-text" | "copy-md"

function BarMenu({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <Menu
      label={label}
      align="start"
      maxHeight={640}
      className="w-64"
      trigger={
        <button
          type="button"
          // Keep the editor's selection: the menus act on it.
          onMouseDown={(e) => e.preventDefault()}
          className="h-7 cursor-pointer rounded-md px-2 text-sm text-label-secondary transition-colors duration-150 hover:bg-accent hover:text-foreground"
        >
          {label}
        </button>
      }
    >
      {children}
    </Menu>
  )
}

function Item({ children, keys }: { children: React.ReactNode; keys?: ShortcutName }) {
  return (
    <>
      <span className="min-w-0 flex-1 truncate">{children}</span>
      {keys && <span className="shrink-0 pl-3 text-xs text-muted-foreground">{shortcutLabel(SHORTCUTS[keys])}</span>}
    </>
  )
}

export type HeaderActions = {
  exec: (cmd: EditorCommand) => void
  onLink: () => void
  onSuggest: () => void
  onExport: (choice: ExportChoice) => void
  onPalette: () => void
  onTailor: (() => void) | null
  onOpenBase: (() => void) | null
  onDelete: () => void
  onRename: () => void
  onNew: () => void
  onToggleOutline: () => void
  onTogglePages: () => void
  onTogglePanel: () => void
  onToggleCompare: (() => void) | null
}

/** The document icon is the way back to all documents: it turns into a back arrow on hover. */
export function DocumentHeader({
  name,
  nameInput,
  status,
  target,
  folders,
  folderId,
  onMove,
  draft,
  savingVariant,
  onSaveVariant,
  canExport,
  hasOriginal,
  views,
  deleteLabel,
  disabled,
  onBack,
  actions,
}: {
  name: string
  nameInput: React.ReactNode
  status: React.ReactNode
  target: string | null
  /** null when this can't move (a variant, unsaved). */
  folders: DocumentFolder[] | null
  folderId: string | null
  onMove: (folderId: string | null) => void
  draft: boolean
  savingVariant: boolean
  onSaveVariant: () => void
  canExport: boolean
  hasOriginal: boolean
  views: { outline: boolean; pages: boolean; panel: boolean; compare: boolean | null }
  deleteLabel: string
  disabled: boolean
  onBack: () => void
  actions: HeaderActions
}) {
  const a = actions
  const block = (style: BlockStyle) => () => a.exec({ type: "block", style })
  const folder = folders?.find((f) => f.id === folderId) ?? null
  return (
    <header className="flex flex-none items-center gap-2 px-2 pb-1.5 pt-2 sm:gap-3 sm:px-3">
      <button
        type="button"
        onClick={onBack}
        aria-label="Back to all documents"
        className="group/back relative inline-flex size-11 shrink-0 cursor-pointer items-center justify-center rounded-full transition-colors duration-150 hover:bg-accent focus-visible:bg-accent focus-visible:outline-none"
      >
        <FileText
          aria-hidden
          strokeWidth={1.75}
          className={cn(
            "size-8 transition-[opacity,scale] duration-150 group-hover/back:scale-75 group-hover/back:opacity-0 group-focus-visible/back:scale-75 group-focus-visible/back:opacity-0 motion-reduce:transition-none",
            "text-label-secondary",
          )}
        />
        <ArrowLeft
          aria-hidden
          className="absolute size-5 scale-75 text-foreground opacity-0 transition-[opacity,scale] duration-150 group-hover/back:scale-100 group-hover/back:opacity-100 group-focus-visible/back:scale-100 group-focus-visible/back:opacity-100 motion-reduce:transition-none"
        />
      </button>

      <div className="flex min-w-0 flex-1 flex-col">
        <div className="flex min-w-0 items-center gap-0.5">
          {nameInput}
          {folders && (
            <Menu
              label="Move to a folder"
              trigger={
                <button
                  type="button"
                  aria-label={folder ? `In ${folder.name}. Move to a folder` : "Move to a folder"}
                  data-tooltip={folder ? `In ${folder.name}` : "Move to a folder"}
                  className="inline-flex size-7 shrink-0 cursor-pointer items-center justify-center rounded-full text-muted-foreground hover:bg-accent hover:text-foreground [&_svg]:size-4"
                >
                  <FolderInput />
                </button>
              }
            >
              {folders.length === 0 && <p className="px-2.5 py-2 text-sm text-muted-foreground">No folders yet. Make one on the Documents page.</p>}
              {folders.map((f) => (
                <MenuItem key={f.id} disabled={f.id === folderId} onSelect={() => onMove(f.id)}>
                  <span className="min-w-0 flex-1 truncate">{f.name}</span>
                  {f.id === folderId && <span className="text-xs text-muted-foreground">Here</span>}
                </MenuItem>
              ))}
              {folderId && (
                <>
                  <MenuSeparator />
                  <MenuItem onSelect={() => onMove(null)}>Remove from folder</MenuItem>
                </>
              )}
            </Menu>
          )}
          {status}
          {target && (
            <span className="ml-1 hidden min-w-0 truncate rounded-full bg-muted px-2 py-0.5 text-xs text-muted-foreground md:inline" title={`Tailored for ${target}`}>
              for {target}
            </span>
          )}
        </div>

        <nav aria-label="Menu" className="nice-scroll flex min-w-0 items-center overflow-x-auto">
          <BarMenu label="File">
            <MenuItem onSelect={a.onNew}>New document</MenuItem>
            <MenuItem onSelect={a.onRename}>Rename</MenuItem>
            <MenuSeparator />
            <MenuItem disabled={!canExport} onSelect={() => a.onExport("pdf")}>
              <Item>Download PDF{canExport ? "" : " (once it's saved)"}</Item>
            </MenuItem>
            <MenuItem disabled={!canExport} onSelect={() => a.onExport("docx")}>
              <Item>Download Word (.docx){canExport ? "" : " (once it's saved)"}</Item>
            </MenuItem>
            <MenuItem onSelect={() => a.onExport("md")}>Download Markdown (.md)</MenuItem>
            <MenuItem onSelect={() => a.onExport("txt")}>Download plain text (.txt)</MenuItem>
            {hasOriginal ? <MenuItem onSelect={() => a.onExport("original")}>Download the uploaded file</MenuItem> : null}
            <MenuSeparator />
            <MenuItem onSelect={() => a.onExport("copy-text")}>Copy as text</MenuItem>
            <MenuItem onSelect={() => a.onExport("copy-md")}>Copy as Markdown</MenuItem>
            <MenuSeparator />
            <MenuItem destructive onSelect={a.onDelete}>{deleteLabel}</MenuItem>
          </BarMenu>
          <BarMenu label="Edit">
            <MenuItem disabled={disabled} onSelect={() => a.exec({ type: "undo" })}><Item keys="undo">Undo</Item></MenuItem>
            <MenuItem disabled={disabled} onSelect={() => a.exec({ type: "redo" })}><Item keys="redo">Redo</Item></MenuItem>
            <MenuSeparator />
            <MenuItem disabled={disabled} onSelect={() => a.exec({ type: "find" })}><Item keys="find">Find and replace</Item></MenuItem>
            <MenuItem disabled={disabled} onSelect={a.onSuggest}><Item keys="suggest">Suggest a change to the selection</Item></MenuItem>
          </BarMenu>
          <BarMenu label="View">
            <MenuItem onSelect={a.onToggleOutline}>{views.outline ? "Hide outline" : "Show outline"}</MenuItem>
            <MenuItem onSelect={a.onTogglePages}>{views.pages ? "Hide page breaks" : "Show page breaks"}</MenuItem>
            <MenuItem onSelect={a.onTogglePanel}>{views.panel ? "Hide suggestions" : "Show suggestions"}</MenuItem>
            {a.onToggleCompare && views.compare !== null ? (
              <MenuItem onSelect={a.onToggleCompare}>{views.compare ? "Stop comparing" : "Compare with the base"}</MenuItem>
            ) : null}
            {a.onOpenBase ? (
              <>
                <MenuSeparator />
                <MenuItem onSelect={a.onOpenBase}>Open the base</MenuItem>
              </>
            ) : null}
          </BarMenu>
          <BarMenu label="Insert">
            <MenuItem disabled={disabled} onSelect={() => a.exec({ type: "table", rows: 3, cols: 3 })}>Table (3 × 3)</MenuItem>
            <MenuItem disabled={disabled} onSelect={() => a.exec({ type: "rule" })}>Horizontal line</MenuItem>
            <MenuItem disabled={disabled} onSelect={a.onLink}><Item keys="link">Link</Item></MenuItem>
          </BarMenu>
          <BarMenu label="Format">
            <MenuItem disabled={disabled} onSelect={() => a.exec({ type: "bold" })}><Item keys="bold">Bold</Item></MenuItem>
            <MenuItem disabled={disabled} onSelect={() => a.exec({ type: "italic" })}><Item keys="italic">Italic</Item></MenuItem>
            <MenuItem disabled={disabled} onSelect={() => a.exec({ type: "underline" })}><Item keys="underline">Underline</Item></MenuItem>
            <MenuSeparator />
            <MenuItem disabled={disabled} onSelect={block("normal")}><Item keys="normal">Normal text</Item></MenuItem>
            <MenuItem disabled={disabled} onSelect={block("title")}>Title</MenuItem>
            <MenuItem disabled={disabled} onSelect={block("h1")}><Item keys="h1">Heading 1</Item></MenuItem>
            <MenuItem disabled={disabled} onSelect={block("h2")}><Item keys="h2">Heading 2</Item></MenuItem>
            <MenuItem disabled={disabled} onSelect={block("h3")}><Item keys="h3">Heading 3</Item></MenuItem>
            <MenuSeparator />
            <MenuItem disabled={disabled} onSelect={() => a.exec({ type: "list", ordered: false })}><Item keys="bullets">Bulleted list</Item></MenuItem>
            <MenuItem disabled={disabled} onSelect={() => a.exec({ type: "list", ordered: true })}><Item keys="numbers">Numbered list</Item></MenuItem>
          </BarMenu>
          <BarMenu label="Tools">
            {a.onTailor ? <MenuItem onSelect={a.onTailor}>Tailor for a professor…</MenuItem> : null}
            <MenuItem onSelect={a.onPalette}><Item keys="commands">Commands</Item></MenuItem>
          </BarMenu>
        </nav>
      </div>

      <div className="flex shrink-0 items-center gap-2">
        {draft && (
          <Button data-tooltip="Save this tailored version as a separate variant" size="sm" className="h-9 rounded-full px-4" disabled={savingVariant} onClick={onSaveVariant}>
            <Save /> <span className="hidden sm:inline">{savingVariant ? "Saving…" : "Save variant"}</span>
            <span className="sm:hidden">Save</span>
          </Button>
        )}
        {a.onTailor && (
          <button
            type="button"
            onClick={a.onTailor}
            data-tooltip="Choose a professor to tailor this for"
            aria-label={`Tailor ${name} for a professor`}
            className="g-btn g-btn--secondary hidden shrink-0 sm:inline-flex [&_svg]:size-4"
          >
            <UserRoundSearch /> Tailor for a professor
          </button>
        )}
        <AccountMenu compact placement="below" />
      </div>
    </header>
  )
}
