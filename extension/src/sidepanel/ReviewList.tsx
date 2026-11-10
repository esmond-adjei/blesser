import * as React from "react"
import { Ban, Check, ChevronDown, Eraser, LocateFixed, PencilLine, X } from "lucide-react"
import { Button, Input, Select, Textarea, cn } from "@blesser/ui"
import { describeSource, displayValue, groupRows } from "../shared/review"
import type { PanelMessage, Review, ReviewRow, RowStatus } from "../shared/types"
import { send } from "../shared/ui"
import { canEdit, editorFor, initialDraft } from "./editor"

type Draft = string | string[]
type ActionReply = { review: Review; warning: string | null }

const GROUPS: { status: RowStatus; title: string }[] = [
  { status: "filled", title: "Filled" },
  { status: "drafted", title: "Drafted" },
  { status: "needs", title: "Needs you" },
]

const DOT: Record<RowStatus, string> = {
  filled: "bg-positive",
  drafted: "bg-caution",
  needs: "border border-ink-tertiary bg-transparent",
}

const wordCount = (text: string) => (text.trim() ? text.trim().split(/\s+/).length : 0)
const message = (err: unknown) => (err instanceof Error ? err.message : "Something went wrong.")

export function ReviewList({ review, tabId, stale }: { review: Review; tabId: number; stale: boolean }) {
  const groups = groupRows(review.rows)
  const [open, setOpen] = React.useState<string | null>(null)
  const [collapsed, setCollapsed] = React.useState<Partial<Record<RowStatus, boolean>>>({})

  if (!review.rows.length) {
    return <p className="rounded-md bg-surface-sunk px-3 py-3 text-footnote text-ink-secondary">Nothing on this page matched your kit, and nothing required is left.</p>
  }

  return (
    <div className="space-y-3" aria-label="Review" role="region">
      {GROUPS.map(({ status, title }) => {
        const rows = groups[status]
        if (!rows.length) return null
        const hidden = collapsed[status] ?? false
        const id = `group-${status}`
        return (
          <section key={status} aria-labelledby={`${id}-title`}>
            <h2 id={`${id}-title`} className="sticky top-0 z-10 bg-canvas">
              <button
                type="button"
                aria-expanded={!hidden}
                aria-controls={id}
                onClick={() => setCollapsed((c) => ({ ...c, [status]: !hidden }))}
                className="flex w-full items-center gap-2 rounded-sm py-1.5 text-left text-[12px] font-semibold tracking-[0.04em] text-ink-secondary uppercase focus-visible:outline-2 focus-visible:outline-focus"
              >
                <span className={cn("size-2 shrink-0 rounded-full", DOT[status])} aria-hidden="true" />
                {title}
                <span className="tabular-nums text-ink-tertiary">{rows.length}</span>
                <ChevronDown className={cn("ml-auto size-3.5 transition-transform duration-160", hidden && "-rotate-90")} aria-hidden="true" />
              </button>
            </h2>
            {hidden ? null : (
              <ul id={id} className="divide-y divide-separator overflow-hidden rounded-md border border-separator bg-surface">
                {rows.map((row) => (
                  <Row
                    key={row.key}
                    row={row}
                    tabId={tabId}
                    stale={stale}
                    open={open === row.key}
                    onToggle={() => setOpen((k) => (k === row.key ? null : row.key))}
                  />
                ))}
              </ul>
            )}
          </section>
        )
      })}
    </div>
  )
}

function Confidence({ level }: { level: ReviewRow["confidence"] }) {
  if (!level || level === "high") return null
  return (
    <span className="shrink-0 text-[11px] leading-4 text-ink-tertiary" title={`${level === "medium" ? "Medium" : "Low"} confidence: check it`}>
      {level === "medium" ? "Medium" : "Low"} confidence
    </span>
  )
}

function Row({ row, tabId, stale, open, onToggle }: { row: ReviewRow; tabId: number; stale: boolean; open: boolean; onToggle: () => void }) {
  const [editing, setEditing] = React.useState(false)
  const [busy, setBusy] = React.useState<string | null>(null)
  const [error, setError] = React.useState<string | null>(null)
  const headRef = React.useRef<HTMLButtonElement | null>(null)
  const panelId = `row-${row.key.replace(/[^a-z0-9]/gi, "-")}`
  const value = displayValue(row)
  const source = row.status === "needs" ? row.reason : describeSource(row)
  const filled = row.status !== "needs"

  const run = async (label: string, message_: PanelMessage, after?: () => void) => {
    setBusy(label)
    setError(null)
    try {
      const reply = await send<ActionReply | Review | boolean>(message_)
      if (reply && typeof reply === "object" && "warning" in reply && reply.warning) setError(reply.warning)
      after?.()
    } catch (err) {
      setError(message(err))
    } finally {
      setBusy(null)
    }
  }

  const jump = () => void run("jump", { type: "focus", tabId, key: row.key })

  return (
    <li className={cn("relative", open && "bg-surface-raised")}>
      <button
        ref={headRef}
        type="button"
        aria-expanded={open}
        aria-controls={panelId}
        onClick={onToggle}
        className="flex w-full items-start gap-2.5 px-3 py-2 text-left transition-colors duration-160 hover:bg-surface-sunk/60 focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-focus"
      >
        <span className={cn("mt-1.5 size-1.5 shrink-0 rounded-full", DOT[row.status])} aria-hidden="true" />
        <span className="min-w-0 flex-1">
          <span className="flex items-baseline gap-2">
            <span className="min-w-0 flex-1 truncate text-callout text-ink">{row.label}</span>
            <Confidence level={row.confidence} />
          </span>
          {filled ? (
            <span className={cn("block text-footnote break-words text-ink", open ? "whitespace-pre-wrap" : "line-clamp-2")}>{value || "Empty"}</span>
          ) : null}
          <span className={cn("block text-[12px] leading-4", filled ? "text-ink-tertiary" : "text-ink-secondary")}>{source}</span>
        </span>
      </button>

      {row.pageEdit ? (
        <div className="mx-3 mb-2 rounded-sm bg-info-soft px-2.5 py-2" role="status">
          <p className="text-footnote text-ink">
            You changed this on the page{row.pageEdit.value === null ? " to empty" : <> to <q className="font-medium">{displayValue({ ...row, value: row.pageEdit.value, document: null })}</q></>}.
          </p>
          <div className="mt-1.5 flex flex-wrap gap-1.5">
            <Button size="sm" variant="brand" className="h-7 px-3 text-[12px]" disabled={!!busy} onClick={() => void run("remember", { type: "remember", tabId, key: row.key })}>
              {busy === "remember" ? "Remembering…" : "Remember this correction"}
            </Button>
            <Button size="sm" variant="quiet" className="h-7 px-2.5 text-[12px]" disabled={!!busy} onClick={() => void run("dismiss", { type: "dismissEdit", tabId, key: row.key })}>
              Just this once
            </Button>
          </div>
        </div>
      ) : null}

      {open ? (
        <div id={panelId} className="px-3 pb-2.5 pl-7">
          {editing ? (
            <Editor
              row={row}
              busy={busy === "edit"}
              onCancel={() => {
                setEditing(false)
                headRef.current?.focus()
              }}
              onSave={(draft) =>
                void run("edit", { type: "edit", tabId, key: row.key, value: draft }, () => {
                  setEditing(false)
                  headRef.current?.focus()
                })
              }
            />
          ) : (
            <div className="flex flex-wrap gap-1" role="group" aria-label={`Actions for ${row.label}`}>
              <Action icon={<LocateFixed />} label="Jump to field" onClick={jump} disabled={stale || !!busy} />
              {canEdit(row.field) ? (
                <Action icon={<PencilLine />} label={filled ? "Edit" : "Fill in"} onClick={() => setEditing(true)} disabled={stale || !!busy} />
              ) : null}
              {filled ? (
                <>
                  <Action icon={<Eraser />} label="Clear" onClick={() => void run("clear", { type: "clear", tabId, key: row.key })} disabled={stale || !!busy} />
                  <Action
                    icon={<Ban />}
                    label="Wrong field"
                    title="Clears it and tells Blesser not to fill this field on this site"
                    onClick={() => void run("wrong", { type: "wrongField", tabId, key: row.key })}
                    disabled={stale || !!busy}
                  />
                </>
              ) : null}
            </div>
          )}
          {stale && !editing ? <p className="mt-1.5 text-[12px] leading-4 text-ink-tertiary">The page moved on. Fill this step to work with its fields.</p> : null}
        </div>
      ) : null}
      {error ? (
        <p role="alert" className="px-3 pb-2 pl-7 text-footnote text-critical">
          {error}
        </p>
      ) : null}
    </li>
  )
}

function Action({ icon, label, onClick, disabled, title }: { icon: React.ReactNode; label: string; onClick: () => void; disabled?: boolean; title?: string }) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      title={title}
      className="inline-flex h-7 cursor-pointer items-center gap-1 rounded-full px-2 text-[12px] font-medium text-ink-secondary transition-colors duration-160 hover:bg-surface-sunk hover:text-ink focus-visible:outline-2 focus-visible:outline-focus disabled:cursor-not-allowed disabled:opacity-45 [&_svg]:size-3.5"
    >
      {icon}
      {label}
    </button>
  )
}

function Editor({ row, busy, onSave, onCancel }: { row: ReviewRow; busy: boolean; onSave: (draft: Draft) => void; onCancel: () => void }) {
  const { kind, inputType } = editorFor(row.field)
  const [draft, setDraft] = React.useState<Draft>(() => initialDraft(row))
  const id = React.useId()
  const focusRef = React.useCallback((el: HTMLElement | null) => el?.focus(), [])
  const text = typeof draft === "string" ? draft : ""
  const limit = row.field.word_limit
  const words = wordCount(text)
  const control = "h-control-sm px-2.5 text-footnote"

  return (
    <form
      className="space-y-2"
      aria-label={`Edit ${row.label}`}
      onSubmit={(e) => {
        e.preventDefault()
        onSave(draft)
      }}
      onKeyDown={(e) => {
        if (e.key === "Escape") {
          e.preventDefault()
          onCancel()
        }
        if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
          e.preventDefault()
          onSave(draft)
        }
      }}
    >
      <label htmlFor={id} className="sr-only">
        {row.label}
      </label>
      {kind === "select" || kind === "yesno" ? (
        <Select id={id} ref={focusRef} value={text} onChange={(e) => setDraft(e.target.value)} className={control}>
          <option value="">Leave empty</option>
          {kind === "yesno" ? (
            <>
              <option value="Yes">Yes, tick it</option>
              <option value="No">No, leave it unticked</option>
            </>
          ) : (
            row.field.options.map((o, i) => (
              <option key={`${o.value}-${i}`} value={o.value}>
                {o.label || o.value}
              </option>
            ))
          )}
        </Select>
      ) : kind === "multi" ? (
        <fieldset id={id} className="max-h-48 space-y-1 overflow-y-auto rounded-sm border border-control-border bg-surface px-2.5 py-2">
          <legend className="sr-only">{row.label}</legend>
          {row.field.options.map((o, i) => {
            const list = Array.isArray(draft) ? draft : []
            const checked = list.includes(o.value)
            return (
              <label key={`${o.value}-${i}`} className="flex cursor-pointer items-center gap-2 text-footnote text-ink">
                <input
                  type="checkbox"
                  ref={i === 0 ? focusRef : undefined}
                  checked={checked}
                  onChange={() => setDraft(checked ? list.filter((v) => v !== o.value) : [...list, o.value])}
                  className="size-3.5 accent-forest"
                />
                {o.label || o.value}
              </label>
            )
          })}
        </fieldset>
      ) : kind === "textarea" ? (
        <Textarea id={id} ref={focusRef} value={text} onChange={(e) => setDraft(e.target.value)} rows={5} className="min-h-20 px-2.5 text-footnote leading-5" />
      ) : (
        <Input id={id} ref={focusRef} type={inputType} value={text} onChange={(e) => setDraft(e.target.value)} className={control} />
      )}
      <div className="flex items-center gap-1.5">
        <Button type="submit" size="sm" variant="brand" className="h-7 px-3 text-[12px]" icon={<Check />} disabled={busy}>
          {busy ? "Saving…" : "Save to page"}
        </Button>
        <Button size="sm" variant="quiet" className="h-7 px-2.5 text-[12px]" icon={<X />} onClick={onCancel} disabled={busy}>
          Cancel
        </Button>
        {limit && kind === "textarea" ? (
          <span className={cn("ml-auto text-[12px] tabular-nums", words > limit ? "font-semibold text-critical" : "text-ink-tertiary")}>
            {words} / {limit} words
          </span>
        ) : null}
      </div>
      <p className="text-[12px] leading-4 text-ink-tertiary">Blesser remembers your change for this site next time.</p>
    </form>
  )
}
