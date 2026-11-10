import * as React from "react"
import { Button, Field, Logo } from "@blesser/ui"
import type { Settings, Status } from "../shared/types"
import { send } from "../shared/ui"

export function Options() {
  const [form, setForm] = React.useState<Settings | null>(null)
  const [note, setNote] = React.useState<{ tone: "ok" | "error"; text: string } | null>(null)

  React.useEffect(() => {
    void send<Status>({ type: "status" }).then((s) => setForm(s.settings))
  }, [])

  const save = async (next: Settings) => {
    setNote(null)
    try {
      setForm(await send<Settings>({ type: "settings", settings: next }))
      setNote({ tone: "ok", text: "Saved." })
    } catch (err) {
      setNote({ tone: "error", text: err instanceof Error ? err.message : "Couldn't save" })
    }
  }

  const appOrigin = (() => {
    try {
      return form ? new URL(form.appUrl).origin : ""
    } catch {
      return ""
    }
  })()
  const reachable = !appOrigin || __APP_ORIGINS__.includes(appOrigin)

  return (
    <main className="mx-auto max-w-lg space-y-6 px-4 py-10">
      <header className="flex items-center gap-3">
        <Logo className="size-9" title="" />
        <div>
          <h1 className="type-title-2 text-ink">Blesser extension</h1>
          <p className="text-callout text-ink-secondary">Where the extension finds Blesser.</p>
        </div>
      </header>
      {form ? (
        <form
          className="space-y-4 rounded-lg border border-separator bg-surface p-5"
          onSubmit={(e) => {
            e.preventDefault()
            void save(form)
          }}
        >
          <Field label="API address" hint="Changing it disconnects this browser." value={form.apiUrl} onChange={(e) => setForm({ ...form, apiUrl: e.target.value })} type="url" required />
          <Field
            label="App address"
            hint={reachable ? "Where you connect the extension and edit your Apply kit." : `This build only accepts connections from ${__APP_ORIGINS__.join(", ")}. Rebuild with BLESSER_APP_ORIGINS to add more.`}
            error={reachable ? undefined : "Connect won't work from this address."}
            value={form.appUrl}
            onChange={(e) => setForm({ ...form, appUrl: e.target.value })}
            type="url"
            required
          />
          <div className="flex items-center justify-end gap-2">
            {note ? <p role="status" className={note.tone === "ok" ? "mr-auto text-callout text-positive" : "mr-auto text-callout text-critical"}>{note.text}</p> : null}
            <Button size="sm" variant="quiet" onClick={() => void save({ apiUrl: "", appUrl: "" })}>Use defaults</Button>
            <Button size="sm" variant="brand" type="submit">Save</Button>
          </div>
        </form>
      ) : null}
      <section className="space-y-2 text-callout text-ink-secondary">
        <h2 className="text-callout font-semibold text-ink">What the extension does</h2>
        <ul className="list-disc space-y-1 pl-5">
          <li>Reads a page only when you press Fill this page.</li>
          <li>Never submits a form, never presses buttons and never fills passwords or payment details.</li>
          <li>Keeps its sign-in in this browser. Disconnect it here or in Blesser under Settings, Account and security.</li>
        </ul>
      </section>
    </main>
  )
}
