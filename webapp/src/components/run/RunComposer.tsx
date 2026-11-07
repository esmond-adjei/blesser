import * as React from "react"
import { ArrowUp, FileText, Loader2 } from "lucide-react"
import { Link } from "react-router-dom"
import * as api from "../../lib/api"
import { useCvDocuments } from "../../lib/queries"
import { toastError } from "../../lib/toast"
import type { Inferred } from "../../lib/runInference"
import type { ProgramSeed, SchoolTier } from "../../lib/types"
import { ComposerMenu, CvSuggestButton, SchoolsMenu } from "./composer/ComposerMenu"
import { SchoolChips, type SizeValue } from "./composer/Pickers"
import { RunModelDropup } from "./ModelPicker"
import { Popover } from "../ui/popover"

export interface ComposerValue extends SizeValue {
  interest: string
  interestDocumentId?: string | null
  degrees: string[]
  regions: string[]
  fields: string[]
  schoolTiers: SchoolTier[]
  seeds: ProgramSeed[]
  /** "default", "system" or a configured provider. */
  model: string
}

/** Which pills still follow the interest text; a pill the user set stops. */
export interface AutoFlags {
  degrees: boolean
  regions: boolean
  fields: boolean
}

/** Shortest interest worth scoring professors against. */
export const MIN_INTEREST = 12

const isCoarse = () => typeof window !== "undefined" && !!window.matchMedia?.("(pointer: coarse)").matches

/** Every option has a default, so typing a sentence and pressing Enter starts a run. */
export function RunComposer({
  value,
  onChange,
  auto,
  onAutoChange,
  inferred,
  recentPlaces,
  busy,
  nudge,
  onSubmit,
  onSuggest,
}: {
  value: ComposerValue
  onChange: (v: ComposerValue) => void
  auto: AutoFlags
  onAutoChange: (a: AutoFlags) => void
  inferred: Inferred
  recentPlaces: string[]
  busy: boolean
  nudge: string | null
  onSubmit: () => void
  /** Opens interest suggestions from the chosen CV; absent without a CV. */
  onSuggest?: (documentId: string) => void
}) {
  const ref = React.useRef<HTMLTextAreaElement | null>(null)
  // Menus open under the whole card, at its width.
  const card = React.useRef<HTMLDivElement | null>(null)
  const set = <K extends keyof ComposerValue>(k: K, v: ComposerValue[K]) => onChange({ ...value, [k]: v })
  const documents = useCvDocuments()
  const interests = (documents.data ?? []).filter((document) => document.kind === "interest")

  async function loadStatement(id: string, close: () => void) {
    try {
      const document = await api.getCvDocument(id)
      onChange({ ...value, interest: document.markdown.trim(), interestDocumentId: document.id })
      close()
    } catch (error) {
      toastError(error, "Couldn't open that interest statement")
    }
  }

  React.useLayoutEffect(() => {
    const el = ref.current
    if (!el) return
    el.style.height = "auto"
    el.style.height = `${Math.min(el.scrollHeight, window.innerHeight * 0.4)}px`
  }, [value.interest])

  return (
    <div ref={card} className="rounded-xl border border-border bg-card shadow-sm transition-colors focus-within:border-ring">
      <SchoolChips seeds={value.seeds} onRemove={(i) => set("seeds", value.seeds.filter((_, j) => j !== i))} />
      <textarea
        ref={ref}
        autoFocus
        rows={2}
        value={value.interest}
        onChange={(e) => onChange({ ...value, interest: e.target.value, interestDocumentId: null })}
        onKeyDown={(e) => {
          if (e.key !== "Enter" || e.nativeEvent.isComposing) return
          const always = e.metaKey || e.ctrlKey
          // Phones: Enter is a newline; the send button submits.
          if (always || (!e.shiftKey && !isCoarse())) {
            e.preventDefault()
            onSubmit()
          }
        }}
        placeholder="Describe the research you want to do... e.g. PhD in robot learning for manipulation, in Canada"
        aria-label="Research interest"
        className="nice-scroll block w-full resize-none bg-transparent px-4 pt-3.5 text-md leading-relaxed outline-none placeholder:text-label-tertiary"
      />
      {nudge && <p className="px-4 pt-1 type-caption" aria-live="polite">{nudge}</p>}
      {/* One line at any width: the summary truncates, model and send stay right. */}
      <div className="flex items-center gap-1.5 px-2.5 pb-2.5 pt-2">
        <SchoolsMenu value={value} anchor={card} onAdd={(seeds) => set("seeds", [...value.seeds, ...seeds])} />
        <Popover
          label="Saved interest statements"
          anchor={card}
          trigger={(props) => (
            <button {...props} type="button" aria-label="Use a saved interest statement" data-tooltip="Use a saved interest statement" className="flex h-7 shrink-0 cursor-pointer items-center gap-1.5 rounded-full border border-border px-2.5 text-xs text-muted-foreground hover:border-foreground/20 hover:text-foreground">
              <FileText className="size-3.5" />
              <span className="hidden sm:inline">{value.interestDocumentId ? "Statement selected" : "Use statement"}</span>
            </button>
          )}
        >
          {(close) => (
            <div className="nice-scroll max-h-72 overflow-y-auto p-2" data-popover-body>
              <p className="px-2 py-1.5 text-xs font-semibold text-muted-foreground">Interest statements</p>
              {interests.length ? interests.map((document) => (
                <button key={document.id} type="button" onClick={() => void loadStatement(document.id, close)} className="block w-full cursor-pointer rounded-md px-2 py-2 text-left text-sm hover:bg-accent">
                  <span className="block truncate font-medium">{document.title}</span>
                  <span className="mt-0.5 block truncate text-xs text-muted-foreground">{document.id === value.interestDocumentId ? "Currently selected" : "Replace the run interest with this statement"}</span>
                </button>
              )) : (
                <div className="px-2 py-2 text-sm text-muted-foreground">
                  No saved interest statements. <Link to="/documents" className="font-medium text-primary underline">Create one</Link>.
                </div>
              )}
            </div>
          )}
        </Popover>
        <CvSuggestButton onSuggest={onSuggest} />
        <ComposerMenu
          value={value}
          onChange={onChange}
          auto={auto}
          onAutoChange={onAutoChange}
          inferred={inferred}
          recentPlaces={recentPlaces}
          anchor={card}
        />
        <span className="ml-auto flex shrink-0 items-center gap-1.5">
          <RunModelDropup value={value.model} onChange={(m) => set("model", m)} />
          <button
            type="button"
            onClick={onSubmit}
            disabled={busy || !value.interest.trim()}
            data-tooltip={busy ? "Starting your research run…" : !value.interest.trim() ? "Describe your research interests to start a run" : "Find matching programmes and supervisors (Enter)"}
            aria-label="Start run"
            className="flex size-8 shrink-0 cursor-pointer items-center justify-center rounded-full bg-primary text-primary-foreground transition-opacity disabled:cursor-default disabled:opacity-40"
          >
            {busy ? <Loader2 className="size-4 animate-spin" /> : <ArrowUp className="size-4" />}
          </button>
        </span>
      </div>
    </div>
  )
}
