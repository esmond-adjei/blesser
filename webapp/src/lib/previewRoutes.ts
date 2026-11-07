/** Preview kind -> full-page route. Rail previews show "Open as page" only
 * when this returns a route; a new kind just needs a case here. */
export type PreviewRef =
  | { kind: "application"; id: string }
  | { kind: "candidate"; id: string }
  | { kind: "draft"; id: string }
  | { kind: "professor"; id: string }
  | { kind: "program"; id: string; runId: string }
  | { kind: "school"; id: string }
  | { kind: "run"; id: string }

export function fullPageFor(ref: PreviewRef | null | undefined): string | null {
  if (!ref) return null
  switch (ref.kind) {
    case "application":
      return `/applications/${ref.id}`
    case "candidate":
      return `/dossier/${ref.id}`
    case "draft":
      return `/outbox/${ref.id}`
    case "program":
      return `/runs/${ref.runId}/programmes/${ref.id}`
    case "professor":
      return `/professors/${ref.id}`
    case "school":
      return `/schools/${ref.id}`
    case "run":
      return `/runs/${ref.id}`
  }
}
