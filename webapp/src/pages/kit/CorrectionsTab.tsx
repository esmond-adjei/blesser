import * as React from "react"
import { useQueryClient } from "@tanstack/react-query"
import { Ban, Search, Trash2 } from "lucide-react"
import { Button, Input, cn } from "@blesser/ui"
import { SettingsSection } from "../../components/settings/controls"
import { EmptyState, ErrorState } from "../../components/feedback/EmptyState"
import { KitSkeleton } from "../../components/kit/parts"
import { formatAgo } from "../../lib/format"
import { correctionValue, groupCorrections } from "../../lib/kit"
import { deleteCorrection, kitKeys, useCorrections } from "../../lib/kitApi"
import type { Correction } from "../../lib/kitTypes"
import { toastError, toastSuccess } from "../../lib/toast"

const TYPES: Record<string, string> = {
  select: "Dropdown",
  "select-multiple": "List",
  radio: "Choice",
  checkbox: "Checkbox",
  textarea: "Long text",
  date: "Date",
  email: "Email",
  tel: "Phone",
  url: "Link",
  number: "Number",
}

export function CorrectionsTab() {
  return (
    <SettingsSection
      id="kit-corrections"
      title="Corrections"
      description="When you fix a field the extension filled, it remembers your answer for that site and uses it next time. Only you see these."
    >
      <CorrectionsBody />
    </SettingsSection>
  )
}

function CorrectionsBody() {
  const query = useCorrections()
  const client = useQueryClient()
  const [text, setText] = React.useState("")
  const [removing, setRemoving] = React.useState<string | null>(null)
  const list = query.data ?? []
  const groups = groupCorrections(list, text)

  const forget = async (c: Correction) => {
    setRemoving(c.id)
    try {
      await deleteCorrection(c.id)
      client.setQueryData<Correction[]>(kitKeys.corrections, (old) => old?.filter((x) => x.id !== c.id))
      toastSuccess(`Forgot the correction for "${c.label}"`)
    } catch (err) {
      toastError(err, "Couldn't forget that correction")
    } finally {
      setRemoving(null)
    }
  }

  if (query.isError && !query.data)
    return <ErrorState title="Your corrections didn't load" description="Check your connection and try again." onRetry={() => void query.refetch()} />
  if (query.isLoading) return <KitSkeleton rows={2} />
  if (!list.length)
    return (
      <EmptyState
        title="No corrections yet"
        description={'In the extension\'s side panel, edit a value Blesser filled or press "Wrong field". Blesser remembers it for that site, and it shows up here.'}
      />
    )

  return (
    <div className="space-y-4">
      {list.length > 6 ? (
        <div className="relative max-w-sm">
          <Search aria-hidden="true" className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-ink-tertiary" />
          <Input
            type="search"
            aria-label="Search corrections"
            placeholder="Search sites, fields and values"
            value={text}
            onChange={(e) => setText(e.target.value)}
            className="h-control-sm pl-9 text-callout"
          />
        </div>
      ) : null}
      {groups.length === 0 ? (
        <p className="rounded-lg border border-separator bg-surface px-4 py-6 text-center text-footnote text-ink-secondary">No corrections match.</p>
      ) : (
        groups.map((group) => (
          <section key={group.host} aria-labelledby={`site-${group.host}`}>
            <h3 id={`site-${group.host}`} className="mb-1.5 flex items-baseline gap-2 text-footnote font-semibold text-ink-secondary">
              <span className="truncate">{group.host}</span>
              <span className="font-normal text-ink-tertiary tabular-nums">{group.items.length}</span>
            </h3>
            <ul className="divide-y divide-separator overflow-hidden rounded-lg border border-separator bg-surface">
              {group.items.map((c) => (
                <li key={c.id} className="flex items-start gap-3 px-4 py-3">
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-callout font-medium text-ink">{c.label || "Unlabelled field"}</p>
                    <p className={cn("mt-0.5 text-footnote break-words", c.wrong_field ? "flex items-center gap-1.5 text-caution" : "text-ink")}>
                      {c.wrong_field ? <Ban className="size-3.5 shrink-0" aria-hidden="true" /> : null}
                      {correctionValue(c)}
                    </p>
                    <p className="mt-1 text-caption font-normal text-ink-tertiary">
                      {TYPES[c.field_type] ?? "Text"}, {formatAgo(c.updated_at)}
                    </p>
                  </div>
                  <Button
                    size="sm"
                    variant="quiet"
                    icon={<Trash2 />}
                    aria-label={`Forget the correction for ${c.label || "this field"} on ${c.host}`}
                    title="Forget this correction"
                    disabled={removing === c.id}
                    onClick={() => void forget(c)}
                    className="size-8 shrink-0 text-ink-tertiary hover:text-critical [&_svg]:size-4"
                  />
                </li>
              ))}
            </ul>
          </section>
        ))
      )}
    </div>
  )
}
