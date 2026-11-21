import * as React from "react"
import { useQueryClient } from "@tanstack/react-query"
import { CircleAlert, FileText, Loader2, Upload } from "lucide-react"
import { Button, cn } from "@blesser/ui"
import { Checkbox } from "../ui/checkbox"
import { Alert, AlertDescription } from "../ui/feedback"
import { Dialog, DialogBody, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "../ui/dialog"
import { applyCv, cvSuggestions, defaultChoice, readableCvs, type CvProfile, type Suggestion } from "../../lib/cvImport"
import { formatAgo } from "../../lib/format"
import { fileExtension, titleFromFilename, uploadProblem } from "../../lib/kit"
import { kitKeys, readCv, uploadDocument, useDocuments, useUsage } from "../../lib/kitApi"
import type { KitDocument, ProfileInput } from "../../lib/kitTypes"

const CV_ACCEPT = ".pdf,.docx"

type Step =
  | { name: "choose"; error?: string }
  | { name: "uploading"; filename: string; progress: number }
  | { name: "reading"; doc: KitDocument }
  | { name: "review"; doc: KitDocument; found: CvProfile }

export function CvImportDialog({ open, onClose, profile, onApply }: {
  open: boolean
  onClose: () => void
  profile: ProfileInput
  onApply: (next: ProfileInput, count: number) => void
}) {
  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent onClose={onClose} className="max-w-xl">
        {open ? <CvImportBody onClose={onClose} profile={profile} onApply={onApply} /> : null}
      </DialogContent>
    </Dialog>
  )
}

function CvImportBody({ onClose, profile, onApply }: { onClose: () => void; profile: ProfileInput; onApply: (next: ProfileInput, count: number) => void }) {
  const client = useQueryClient()
  const documents = useDocuments()
  const usage = useUsage()
  const [step, setStep] = React.useState<Step>({ name: "choose" })
  const input = React.useRef<HTMLInputElement>(null)
  // A read that finishes after the member closed the dialog or picked another file is dropped.
  const run = React.useRef(0)
  const upload = React.useRef<AbortController | null>(null)
  React.useEffect(() => () => {
    run.current += 1
    upload.current?.abort()
  }, [])

  const docs = readableCvs(documents.data ?? [])

  const read = async (doc: KitDocument) => {
    const id = ++run.current
    setStep({ name: "reading", doc })
    try {
      const found = await readCv(doc.id)
      if (id === run.current) setStep({ name: "review", doc, found })
    } catch (err) {
      if (id === run.current) setStep({ name: "choose", error: err instanceof Error ? err.message : "Blesser couldn't read that CV." })
    }
  }

  const addFile = async (file: File) => {
    const problem = fileExtension(file.name) === "pdf" || fileExtension(file.name) === "docx" ? uploadProblem(file, usage.data) : "Blesser can read CVs saved as PDF or Word (.docx)."
    if (problem) return setStep({ name: "choose", error: problem })
    const id = ++run.current
    const controller = new AbortController()
    upload.current = controller
    setStep({ name: "uploading", filename: file.name, progress: 0 })
    try {
      const isDefault = !(documents.data ?? []).some((d) => d.kind === "cv")
      const doc = await uploadDocument(
        { file, kind: "cv", title: titleFromFilename(file.name), is_default: isDefault || undefined },
        (progress) => id === run.current && setStep({ name: "uploading", filename: file.name, progress }),
        controller.signal,
      )
      client.setQueryData<KitDocument[]>(kitKeys.documents, (list) => (list ? [doc, ...list.filter((d) => d.id !== doc.id)] : list))
      void client.invalidateQueries({ queryKey: kitKeys.documents })
      if (id === run.current) await read(doc)
    } catch (err) {
      if (err instanceof DOMException && err.name === "AbortError") return
      if (id === run.current) setStep({ name: "choose", error: err instanceof Error ? err.message : "The upload didn't finish." })
    }
  }

  const picker = (
    <input
      ref={input}
      type="file"
      accept={CV_ACCEPT}
      className="sr-only"
      tabIndex={-1}
      aria-hidden="true"
      onChange={(e) => {
        const file = e.target.files?.[0]
        e.target.value = ""
        if (file) void addFile(file)
      }}
    />
  )

  if (step.name === "review") {
    return <Review profile={profile} doc={step.doc} found={step.found} onBack={() => setStep({ name: "choose" })} onClose={onClose} onApply={onApply} />
  }

  if (step.name === "uploading" || step.name === "reading") {
    const label = step.name === "uploading" ? `Uploading ${step.filename}` : `Reading ${step.doc.title}`
    return (
      <>
        <DialogHeader>
          <DialogTitle>Fill your profile from a CV</DialogTitle>
          <DialogDescription>Blesser suggests details from your CV. You choose what goes in.</DialogDescription>
        </DialogHeader>
        <DialogBody>
          <div role="status" className="flex flex-col items-center gap-3 py-8 text-center">
            <Loader2 className="size-6 text-ink-secondary motion-safe:animate-spin" aria-hidden="true" />
            <p className="text-callout font-medium text-ink">{label}</p>
            <p className="text-footnote text-ink-secondary">
              {step.name === "uploading" ? `${Math.round(step.progress * 100)}%` : "This can take up to a minute."}
            </p>
          </div>
        </DialogBody>
        <DialogFooter>
          <Button variant="secondary" onClick={onClose}>Cancel</Button>
        </DialogFooter>
      </>
    )
  }

  return (
    <>
      <DialogHeader>
        <DialogTitle>Fill your profile from a CV</DialogTitle>
        <DialogDescription>
          Blesser suggests details from your CV and you choose what goes in. Anything it can't find stays empty for you to fill.
        </DialogDescription>
      </DialogHeader>
      <DialogBody className="space-y-4">
        {step.error ? (
          <Alert variant="destructive">
            <CircleAlert aria-hidden="true" />
            <AlertDescription>{step.error}</AlertDescription>
          </Alert>
        ) : null}
        {documents.isPending ? (
          <p className="flex items-center gap-2 text-footnote text-ink-secondary">
            <Loader2 className="size-4 motion-safe:animate-spin" aria-hidden="true" /> Loading your documents
          </p>
        ) : docs.length ? (
          <div>
            <p className="mb-2 text-footnote font-semibold text-ink-secondary">From your documents</p>
            <ul className="divide-y divide-separator overflow-hidden rounded-lg border border-separator">
              {docs.map((doc) => (
                <li key={doc.id}>
                  <button
                    type="button"
                    onClick={() => void read(doc)}
                    className="flex w-full cursor-pointer items-center gap-3 px-4 py-3 text-left transition-colors duration-160 hover:bg-highlight focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-focus"
                  >
                    <FileText className="size-5 shrink-0 text-ink-tertiary" strokeWidth={1.75} aria-hidden="true" />
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-callout font-medium text-ink">{doc.title}</span>
                      <span className="block truncate text-footnote text-ink-secondary">
                        {doc.filename}, added {formatAgo(doc.created_at)}
                      </span>
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          </div>
        ) : (
          <p className="text-callout text-ink-secondary">Upload your CV and Blesser saves it to Documents too, ready to attach to applications.</p>
        )}
        <p className="text-footnote text-ink-tertiary">PDF or Word (.docx), up to 15 MB. Scans and photos can't be read.</p>
        {picker}
      </DialogBody>
      <DialogFooter>
        <Button variant="secondary" onClick={onClose}>Cancel</Button>
        <Button variant={docs.length ? "secondary" : "brand"} icon={<Upload />} onClick={() => input.current?.click()}>
          {docs.length ? "Upload another CV" : "Upload your CV"}
        </Button>
      </DialogFooter>
    </>
  )
}

function Review({ profile, doc, found, onBack, onClose, onApply }: {
  profile: ProfileInput
  doc: KitDocument
  found: CvProfile
  onBack: () => void
  onClose: () => void
  onApply: (next: ProfileInput, count: number) => void
}) {
  const list = React.useMemo(() => cvSuggestions(profile, found), [profile, found])
  const [chosen, setChosen] = React.useState(() => defaultChoice(list))
  const sections = React.useMemo(() => {
    const groups = new Map<string, Suggestion[]>()
    for (const s of list) groups.set(s.section, [...(groups.get(s.section) ?? []), s])
    return [...groups]
  }, [list])
  const toggle = (id: string, on: boolean) =>
    setChosen((set) => {
      const next = new Set(set)
      if (on) next.add(id)
      else next.delete(id)
      return next
    })

  if (!list.length) {
    return (
      <>
        <DialogHeader>
          <DialogTitle>Nothing new in this CV</DialogTitle>
          <DialogDescription>Your profile already has everything Blesser found in {doc.title}.</DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <Button variant="secondary" onClick={onBack}>Choose another CV</Button>
          <Button variant="brand" onClick={onClose}>Done</Button>
        </DialogFooter>
      </>
    )
  }

  const count = list.filter((s) => chosen.has(s.id)).length
  return (
    <>
      <DialogHeader>
        <DialogTitle>Check what Blesser found</DialogTitle>
        <DialogDescription>
          Ticked details go into your profile. Fields not listed here stay as they are.
        </DialogDescription>
      </DialogHeader>
      <DialogBody className="space-y-5">
        {sections.map(([section, items]) => (
          <section key={section} aria-label={section}>
            <h3 className="mb-1 text-footnote font-semibold text-ink-secondary">{section}</h3>
            <ul className="divide-y divide-separator">
              {items.map((s) => (
                <li key={s.id}>
                  <label className="flex cursor-pointer items-start gap-3 py-2.5">
                    <Checkbox checked={chosen.has(s.id)} onCheckedChange={(v) => toggle(s.id, v === true)} className="mt-0.5" aria-label={s.label} />
                    <span className="min-w-0 flex-1">
                      <span className="block text-footnote text-ink-secondary">{s.label}</span>
                      <span className={cn("block text-callout break-words text-ink", s.id === "long_bio" && "line-clamp-4")}>{s.value}</span>
                      {s.current !== undefined ? (
                        <span className="mt-0.5 block text-footnote break-words text-ink-tertiary">Replaces {s.current}</span>
                      ) : null}
                    </span>
                  </label>
                </li>
              ))}
            </ul>
          </section>
        ))}
      </DialogBody>
      <DialogFooter>
        <Button variant="secondary" onClick={onBack}>Back</Button>
        <Button variant="brand" disabled={!count} onClick={() => onApply(applyCv(profile, found, chosen), count)}>
          {count === 1 ? "Add 1 detail" : count ? `Add ${count} details` : "Add details"}
        </Button>
      </DialogFooter>
    </>
  )
}
