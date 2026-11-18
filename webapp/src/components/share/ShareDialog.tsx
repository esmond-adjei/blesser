import { Textarea } from "@blesser/ui"
import * as React from "react"
import { useQuery } from "@tanstack/react-query"
import { Copy, Download, Link2, Lock, Share2 } from "lucide-react"
import { Button } from "@blesser/ui"
import * as api from "../../lib/api"
import { canShareFiles, imageFilename, quickLinks } from "../../lib/share"
import { toastError, toastSuccess } from "../../lib/toast"
import type { Opportunity, ShareFormat, ShareKit } from "../../lib/types"
import { Dialog, DialogBody, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "../ui/dialog"
import { Segmented } from "../layout/PageHeader"
import { ErrorState } from "../feedback/EmptyState"

const FORMATS: { value: ShareFormat; label: string; hint: string }[] = [
  { value: "square", label: "Square", hint: "Instagram, WhatsApp, Facebook" },
  { value: "wide", label: "Wide", hint: "LinkedIn, X, link previews" },
  { value: "story", label: "Story", hint: "Stories and status" },
]

const CAPTIONS: { key: keyof ShareKit["captions"]; label: string; hint: string; rows: number }[] = [
  { key: "short", label: "Short", hint: "fits X", rows: 4 },
  { key: "standard", label: "Standard", hint: "LinkedIn, Facebook", rows: 6 },
  { key: "hashtags", label: "With hashtags", hint: "Instagram", rows: 6 },
]

async function copy(text: string, what: string) {
  try {
    await navigator.clipboard.writeText(text)
    toastSuccess(`${what} copied`)
  } catch {
    toastError("Copy didn't work. Select the text and copy it yourself.")
  }
}

/** Image and caption kit for sharing one opportunity on any network. */
export function ShareDialog({ opp, onClose }: { opp: Opportunity | null; onClose: () => void }) {
  // Keep the last opportunity while the dialog animates out.
  const [shown, setShown] = React.useState<Opportunity | null>(opp)
  if (opp && opp !== shown) setShown(opp)
  return (
    <Dialog open={!!opp} onOpenChange={(open) => !open && onClose()}>
      {shown ? (
        <DialogContent className="max-w-5xl" onClose={onClose}>
          <ShareBody opp={shown} onClose={onClose} />
        </DialogContent>
      ) : null}
    </Dialog>
  )
}

function ShareBody({ opp, onClose }: { opp: Opportunity; onClose: () => void }) {
  const kit = useQuery({
    queryKey: ["opportunities", opp.id, "share"],
    queryFn: () => api.shareOpportunity(opp.id),
    staleTime: 10 * 60_000,
  })
  return (
    <>
      <DialogHeader>
        <DialogTitle>Share this opportunity</DialogTitle>
        <DialogDescription className="line-clamp-1">{opp.title}</DialogDescription>
      </DialogHeader>
      <DialogBody>
        {kit.isError ? (
          <ErrorState title="The share kit didn't load" description="Check your connection and try again." onRetry={() => void kit.refetch()} />
        ) : (
          <Kit opp={opp} kit={kit.data} />
        )}
      </DialogBody>
      <DialogFooter>
        <Button variant="quiet" onClick={onClose}>
          Done
        </Button>
      </DialogFooter>
    </>
  )
}

function Kit({ opp, kit }: { opp: Opportunity; kit: ShareKit | undefined }) {
  const [format, setFormat] = React.useState<ShareFormat>("square")
  const [loaded, setLoaded] = React.useState<string | null>(null)
  const [native] = React.useState(canShareFiles)
  const files = React.useRef(new Map<string, Promise<File>>())
  const image = kit?.images[format]
  const filename = imageFilename(opp.slug || opp.id, format)

  // Fetched ahead of the click: Safari drops the user gesture across a slow await.
  const fileFor = React.useCallback(
    (url: string, name: string) => {
      let pending = files.current.get(url)
      if (!pending) {
        pending = fetch(url).then(async (res) => {
          if (!res.ok) throw new Error(`The image didn't load (${res.status})`)
          return new File([await res.blob()], name, { type: "image/png" })
        })
        pending.catch(() => files.current.delete(url))
        files.current.set(url, pending)
      }
      return pending
    },
    [files],
  )
  React.useEffect(() => {
    if (native && image) void fileFor(image, filename).catch(() => undefined)
  }, [native, image, filename, fileFor])

  const download = async () => {
    if (!image) return
    try {
      const url = URL.createObjectURL(await fileFor(image, filename))
      const link = document.createElement("a")
      link.href = url
      link.download = filename
      link.click()
      window.setTimeout(() => URL.revokeObjectURL(url), 1000)
    } catch (err) {
      toastError(err, "The image didn't download")
    }
  }
  const share = async () => {
    if (!kit || !image) return
    try {
      await navigator.share({ files: [await fileFor(image, filename)], title: opp.title, text: kit.captions.standard })
    } catch (err) {
      if ((err as Error).name !== "AbortError") toastError(err, "Sharing didn't work")
    }
  }

  return (
    <div className="grid gap-6 md:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
      <div className="min-w-0 space-y-3">
        <div className="relative grid h-[300px] place-items-center overflow-hidden rounded-md bg-surface-sunk p-4">
          {image ? (
            <img
              key={image}
              src={image}
              alt={`Share image, ${FORMATS.find((f) => f.value === format)?.label.toLowerCase()} format`}
              onLoad={() => setLoaded(image)}
              className="max-h-[268px] w-auto max-w-full rounded-sm shadow-elevation-1 transition-opacity duration-200 data-[loading=true]:opacity-0"
              data-loading={loaded !== image}
            />
          ) : null}
          {loaded !== image ? (
            <div aria-hidden="true" className="absolute inset-8 animate-pulse rounded-sm bg-separator/60 motion-reduce:animate-none" />
          ) : null}
        </div>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <Segmented label="Image format" value={format} onChange={setFormat} options={FORMATS} />
          <span className="text-footnote text-ink-tertiary">{FORMATS.find((f) => f.value === format)?.hint}</span>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button size="sm" variant="secondary" onClick={() => void download()} disabled={!image} icon={<Download />}>
            Download image
          </Button>
          <Button size="sm" variant="quiet" onClick={() => kit && void copy(kit.share_url, "Link")} disabled={!kit} icon={<Link2 />}>
            Copy link
          </Button>
          {native ? (
            <Button size="sm" variant="quiet" onClick={() => void share()} disabled={!image} icon={<Share2 />}>
              Share…
            </Button>
          ) : null}
        </div>
        {kit ? (
          <div className="flex flex-wrap items-center gap-x-3.5 gap-y-1 text-callout">
            <span className="text-ink-tertiary">Post to</span>
            {quickLinks(kit, opp.title).map((l) => (
              <a key={l.label} href={l.href} target="_blank" rel="noopener noreferrer" className="font-medium text-link hover:underline">
                {l.label}
              </a>
            ))}
          </div>
        ) : null}
      </div>

      <div className="min-w-0 space-y-4">
        {CAPTIONS.map((c) => (
          <div key={c.key}>
            <div className="flex items-center justify-between gap-2">
              <label htmlFor={`share-${c.key}`} className="text-callout font-semibold text-ink">
                {c.label} <span className="ml-1 font-normal text-ink-tertiary">{c.hint}</span>
              </label>
              <Button
                size="sm"
                variant="quiet"
                onClick={() => kit && void copy(kit.captions[c.key], `${c.label} caption`)}
                disabled={!kit}
                icon={<Copy />}
              >
                Copy
              </Button>
            </div>
            <Textarea
              id={`share-${c.key}`}
              readOnly
              rows={c.rows}
              value={kit?.captions[c.key] ?? ""}
              className="nice-scroll mt-1 w-full resize-none rounded-sm border border-separator bg-surface-sunk px-3 py-2 text-footnote leading-5 text-ink"
            />
          </div>
        ))}
        <p className="text-footnote text-ink-tertiary">
          {opp.audience === "members" ? (
            <span className="mb-1.5 flex items-start gap-1.5">
              <Lock aria-hidden="true" className="mt-0.5 size-3.5 shrink-0" />
              Members only: people without an account see a short preview and sign up to get the official link.
            </span>
          ) : null}
          {kit?.disclaimer ?? ""} The image and text show Blesser as where you found it, not as the funder.
        </p>
      </div>
    </div>
  )
}
