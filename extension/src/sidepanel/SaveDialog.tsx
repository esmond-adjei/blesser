import * as React from "react"
import { Button, Field, Select } from "@blesser/ui"
import type { ApplicationStatus, NewApplication, PageDetails } from "../shared/types"
import { STATUSES, deadlineText } from "./statuses"

/** Shown only when the page didn't say enough to save on its own: the member fills what's missing. */
export function SaveDialog({
  open,
  details,
  onClose,
  onSave,
}: {
  open: boolean
  details: PageDetails
  onClose: () => void
  onSave: (application: NewApplication) => Promise<void>
}) {
  const ref = React.useRef<HTMLDialogElement | null>(null)
  const [title, setTitle] = React.useState("")
  const [organization, setOrganization] = React.useState("")
  const [date, setDate] = React.useState("")
  const [status, setStatus] = React.useState<ApplicationStatus>("preparing")
  const [saving, setSaving] = React.useState(false)
  const [error, setError] = React.useState<string | null>(null)
  const titleId = React.useId()

  React.useEffect(() => {
    const dialog = ref.current
    if (!dialog) return
    if (open && !dialog.open) {
      setTitle(details.title)
      setOrganization(details.organization)
      setDate(details.deadline?.date ?? "")
      setStatus("preparing")
      setError(null)
      dialog.showModal()
    } else if (!open && dialog.open) dialog.close()
  }, [open, details])

  const submit = async () => {
    setSaving(true)
    setError(null)
    try {
      const rolling = !date && !!details.deadline?.rolling
      await onSave({
        title: title.trim(),
        organization: organization.trim(),
        link: "",
        deadline: date ? deadlineText(date) : rolling ? "Rolling" : "",
        deadline_date: date || null,
        status,
      })
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn't save this application")
    } finally {
      setSaving(false)
    }
  }

  return (
    <dialog
      ref={ref}
      aria-labelledby={titleId}
      onClose={onClose}
      onCancel={onClose}
      className="m-auto w-[calc(100%-24px)] max-w-[420px] rounded-lg border border-separator bg-surface p-0 text-ink shadow-elevation-3 backdrop:bg-scrim"
    >
      <form
        method="dialog"
        className="space-y-3 p-4"
        onSubmit={(e) => {
          e.preventDefault()
          void submit()
        }}
      >
        <div>
          <h2 id={titleId} className="text-headline text-ink">Save to my applications</h2>
          <p className="mt-1 text-footnote text-ink-secondary">This page becomes the application's link. Fill in what the page didn't say.</p>
        </div>
        <Field label="Title" value={title} required maxLength={300} onChange={(e) => setTitle(e.target.value)} error={title.trim() ? undefined : "The page has no clear title. Add one."} />
        <Field label="Funder or organisation" value={organization} maxLength={200} onChange={(e) => setOrganization(e.target.value)} />
        <Field
          label="Deadline"
          type="date"
          value={date}
          onChange={(e) => setDate(e.target.value)}
          hint={date || details.deadline?.date ? undefined : details.deadline?.rolling ? "The page says it's rolling. Leave this empty to save it as rolling." : "We couldn't find a deadline on this page."}
        />
        <Field label="Status">
          <Select value={status} onChange={(e) => setStatus(e.target.value as ApplicationStatus)}>
            {STATUSES.map((s) => (
              <option key={s.value} value={s.value}>{s.label}</option>
            ))}
          </Select>
        </Field>
        {error ? <p role="alert" className="text-footnote text-critical">{error}</p> : null}
        <div className="flex justify-end gap-2">
          <Button size="sm" variant="quiet" onClick={onClose} disabled={saving}>Cancel</Button>
          <Button type="submit" size="sm" variant="brand" disabled={saving || !title.trim()}>
            {saving ? "Saving…" : "Save"}
          </Button>
        </div>
      </form>
    </dialog>
  )
}
