import * as React from "react"
import { Link, useLocation, useNavigate, useParams, useSearchParams } from "react-router-dom"
import { useAuth } from "../../lib/auth"
import { useCvDocument, useCvVersion } from "../../lib/queries"
import type { CvDocumentDetail } from "../../lib/types"
import { toastError } from "../../lib/toast"
import { Alert, AlertDescription } from "../ui/feedback"
import { loadDraft } from "./documentLocal"
import { DocumentWorkspace, WorkspaceSkeleton } from "./DocumentWorkspace"
import { isKind, KIND } from "./kinds"
import { startDraft, tailoredPath } from "./tailor"
import type { DocumentSource, NewDocument } from "./useDocumentSync"

/** Fetches once unless the data postdates opening `key` (or failed), so a document opens from the server's latest revision. */
function useFresh(
  q: { data: unknown; dataUpdatedAt: number; isError: boolean; isFetching: boolean; refetch: () => unknown },
  key: string,
  enabled: boolean,
): boolean {
  // The cache's timestamp when this key opened: newer data is fresh.
  const [base, setBase] = React.useState({ key, at: q.dataUpdatedAt })
  if (base.key !== key) setBase({ key, at: q.dataUpdatedAt })
  const at = base.key === key ? base.at : q.dataUpdatedAt
  const fresh = !!q.data && (q.dataUpdatedAt > at || q.isError)
  const asked = React.useRef("")
  React.useEffect(() => {
    if (!enabled || fresh || q.isFetching || asked.current === key) return
    asked.current = key
    void q.refetch()
  }, [enabled, fresh, q, key])
  return fresh
}

function Missing({ children, back }: { children: React.ReactNode; back: string }) {
  return (
    <div className="mx-auto w-full max-w-[640px] p-8">
      <Alert variant="destructive">
        <AlertDescription>
          {children}{" "}
          <Link to={back} className="font-medium underline">
            Back
          </Link>
        </AlertDescription>
      </Alert>
    </div>
  )
}

/**
 * /cv/:documentId opens the base CV; ?version=<id> a saved variant, ?draft=<id> a device-only one,
 * ?for=<candidate> the variant for that professor, ?variant=new a blank-target draft.
 * /documents/new is saved nowhere until the first edit, then moves to its address without remounting.
 */
export function DocumentEditor() {
  const { documentId = "" } = useParams()
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()
  const location = useLocation()
  const { user } = useAuth()
  const userId = user?.id ?? "anon"
  const versionId = searchParams.get("version")
  const draftId = searchParams.get("draft")
  const forCandidate = searchParams.get("for")
  const newVariant = searchParams.get("variant") === "new"

  const isNew = documentId === "new"
  // One per visit to /documents/new, followed to the address it was created at.
  const [fresh, setFresh] = React.useState<{ key: string; id: string | null; source: DocumentSource; doc: CvDocumentDetail } | null>(null)
  if (isNew && (!fresh || fresh.id !== null)) {
    const kind = searchParams.get("type")
    const documentKind = isKind(kind) ? kind : "cv"
    const key = `new:${location.key}`
    const blank: NewDocument = {
      documentKind,
      folderId: searchParams.get("folder"),
      title: KIND[documentKind].title,
      markdown: KIND[documentKind].starter,
      onCreated: (created) => {
        setFresh((f) => (f && f.key === key ? { ...f, id: created.id, doc: created } : f))
        navigate(`/documents/${created.id}`, { replace: true })
      },
    }
    setFresh({ key, id: null, source: { kind: "new", blank }, doc: unsavedDocument(blank) })
  } else if (!isNew && fresh && fresh.id !== documentId) {
    setFresh(null)
  }
  const adopted = fresh !== null && (isNew || fresh.id === documentId)

  const doc = useCvDocument(isNew ? null : documentId)
  const version = useCvVersion(draftId ? null : versionId)
  const docReady = useFresh(doc, documentId, true)
  const versionReady = useFresh(version, `${versionId}:${draftId}`, !!versionId && !draftId)

  const resolving = !!forCandidate || newVariant
  React.useEffect(() => {
    if (!resolving || !docReady || !doc.data) return
    let cancelled = false
    const d = doc.data
    const pick = forCandidate
      ? tailoredPath(userId, d, forCandidate)
      : Promise.resolve(`/documents/${d.id}?draft=${startDraft(userId, d, { candidateId: null, name: `${d.title} (variant)`, targetLabel: null }).id}`)
    pick
      .then((to) => {
        if (!cancelled) navigate(to, { replace: true })
      })
      .catch((err) => toastError(err, "Couldn't open the variant"))
    return () => {
      cancelled = true
    }
  }, [resolving, docReady, doc.data, forCandidate, userId, navigate])

  // An unsaved variant: read once per id from this device.
  const draft = React.useMemo(() => (draftId ? loadDraft(userId, draftId) : null), [userId, draftId])

  if (adopted) {
    return <DocumentWorkspace key={fresh.key} user={userId} source={fresh.source} doc={doc.data ?? fresh.doc} version={null} />
  }
  if (doc.isError && !doc.data) return <Missing back="/documents">Document not found.</Missing>
  if (!docReady || !doc.data || resolving) return <WorkspaceSkeleton />

  let source: DocumentSource
  if (draftId) {
    if (!draft || draft.documentId !== doc.data.id) {
      return (
        <Missing back={`/documents/${doc.data.id}`}>
          This unsaved variant isn&rsquo;t on this device. It may have been saved or discarded.
        </Missing>
      )
    }
    source = { kind: "draft", draft }
  } else if (versionId) {
    if (version.isError && !version.data) {
      return <Missing back={`/documents/${doc.data.id}`}>This variant doesn&rsquo;t exist any more.</Missing>
    }
    if (!version.data || !versionReady) return <WorkspaceSkeleton />
    const v = version.data
    source = { kind: "version", id: v.id, server: { markdown: v.markdown, revision: v.revision, title: v.name } }
  } else {
    const d = doc.data
    source = { kind: "doc", id: d.id, server: { markdown: d.markdown, revision: d.revision, title: d.title } }
  }
  const key = source.kind === "draft" ? `draft:${source.draft.id}` : `${source.kind}:${source.id}`
  return (
    <DocumentWorkspace
      key={key}
      user={userId}
      source={source}
      doc={doc.data}
      version={source.kind === "version" ? (version.data ?? null) : null}
    />
  )
}

function unsavedDocument(blank: NewDocument): CvDocumentDetail {
  return {
    id: "",
    title: blank.title,
    kind: blank.documentKind,
    folder_id: blank.folderId,
    word_limit: null,
    page_limit: null,
    format: "md",
    size_bytes: 0,
    has_original: false,
    revision: 0,
    version_count: 0,
    created_at: null,
    updated_at: null,
    versions: [],
    markdown: blank.markdown,
  }
}
