import * as React from "react"
import { EllipsisVertical, Folder, FolderPlus } from "lucide-react"
import type { DocumentFolder } from "../../lib/types"
import { cn } from "../../lib/utils"
import { Menu, MenuItem, MenuSeparator } from "../ui/menu"
import { RenameInput } from "../ui/RenameInput"

const NAME_INPUT = "h-8 w-full min-w-32 rounded-md border border-input bg-background px-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"

/** The open folder carries its own menu (rename, move, delete). */
export function FolderRail({
  folders,
  selected,
  onSelect,
  onCreate,
  onRename,
  onMove,
  onDelete,
}: {
  folders: DocumentFolder[]
  selected: string | null
  onSelect: (id: string | null) => void
  onCreate: (name: string) => void
  onRename: (folder: DocumentFolder, name: string) => void
  onMove: (folder: DocumentFolder, by: -1 | 1) => void
  onDelete: (folder: DocumentFolder) => void
}) {
  const [creating, setCreating] = React.useState(false)
  const [renaming, setRenaming] = React.useState<string | null>(null)

  const folderItem = (active: boolean) =>
    cn(
      "relative flex h-10 min-w-0 max-w-[240px] shrink-0 cursor-pointer items-center gap-2 rounded-md bg-surface px-3 text-sm text-label shadow-sm transition-[box-shadow] duration-150 hover:shadow-md [&>svg]:text-label-tertiary",
      active && "font-medium ring-2 ring-tint",
    )

  return (
    <nav aria-label="Folders" className="-mx-1 min-w-0">
      <ul className="nice-scroll flex gap-2 overflow-x-auto p-1">
        {folders.map((f, i) => {
          const active = selected === f.id
          if (renaming === f.id) {
            return (
              <li key={f.id} className="shrink-0">
                <RenameInput
                  value={f.name}
                  label="Folder name"
                  maxLength={120}
                  selectOnFocus
                  className={NAME_INPUT}
                  onDone={(next) => {
                    setRenaming(null)
                    const clean = next?.trim()
                    if (clean && clean !== f.name) onRename(f, clean)
                  }}
                />
              </li>
            )
          }
          return (
            <li key={f.id} className="group relative flex shrink-0 items-center">
              <button type="button" aria-current={active ? "page" : undefined} onClick={() => onSelect(active ? null : f.id)} className={cn(folderItem(active), active && "pr-9 md:pr-8")}>
                <Folder className="size-4 shrink-0" aria-hidden />
                <span className="truncate" title={f.name}>
                  {f.name}
                </span>
                <span className={cn("ml-auto pl-1 text-xs tabular-nums text-label-tertiary", active && "hidden md:inline")}>{f.document_count}</span>
              </button>
              {active && (
                <div className="absolute right-1 top-1/2 -translate-y-1/2">
                  <Menu
                    label={`${f.name} actions`}
                    trigger={
                      <button
                        type="button"
                        aria-label={`More for ${f.name}`}
                        className="inline-flex size-6 cursor-pointer items-center justify-center rounded-full text-label-secondary hover:bg-fill hover:text-label"
                      >
                        <EllipsisVertical className="size-3.5" />
                      </button>
                    }
                  >
                    <MenuItem onSelect={() => setRenaming(f.id)}>Rename</MenuItem>
                    <MenuItem disabled={i === 0} onSelect={() => onMove(f, -1)}>Move up</MenuItem>
                    <MenuItem disabled={i === folders.length - 1} onSelect={() => onMove(f, 1)}>Move down</MenuItem>
                    <MenuSeparator />
                    <MenuItem destructive onSelect={() => onDelete(f)}>Delete folder</MenuItem>
                  </Menu>
                </div>
              )}
            </li>
          )
        })}
        <li className="shrink-0">
          {creating ? (
            <RenameInput
              value=""
              label="New folder name"
              maxLength={120}
              selectOnFocus
              className={NAME_INPUT}
              onDone={(next) => {
                setCreating(false)
                const clean = next?.trim()
                if (clean) onCreate(clean)
              }}
            />
          ) : (
            <button type="button" onClick={() => setCreating(true)} className="flex h-10 shrink-0 cursor-pointer items-center gap-2 rounded-md px-3 text-sm text-label-secondary ring-1 ring-separator transition-colors ring-inset hover:bg-fill-quiet hover:text-label">
              <FolderPlus className="size-4 shrink-0" aria-hidden />
              <span>New folder</span>
            </button>
          )}
        </li>
      </ul>
    </nav>
  )
}
