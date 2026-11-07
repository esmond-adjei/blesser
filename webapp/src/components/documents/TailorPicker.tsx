import * as React from "react"
import { useQuery } from "@tanstack/react-query"
import { Search } from "lucide-react"
import * as api from "../../lib/api"
import { professorPlace } from "../../lib/entities"
import { Avatar } from "../ui/avatar"
import { Button } from "../ui/button"
import { Dialog, DialogBody, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "../ui/dialog"
import { Skeleton } from "../ui/feedback"
import { Input } from "../ui/input"
import { ScoreBar } from "../ui/status"

export function TailorPicker({
  open,
  onOpenChange,
  onPick,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  onPick: (candidateId: string) => void
}) {
  const [q, setQ] = React.useState("")
  const [term, setTerm] = React.useState("")
  React.useEffect(() => {
    const t = window.setTimeout(() => setTerm(q.trim()), 250)
    return () => window.clearTimeout(t)
  }, [q])
  const results = useQuery({
    queryKey: ["tailor-candidates", term],
    queryFn: () => api.searchCandidates({ q: term || undefined, limit: 20 }),
    enabled: open,
  })
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent onClose={() => onOpenChange(false)} className="max-w-xl">
        <DialogHeader>
          <DialogTitle>Tailor for a professor</DialogTitle>
          <DialogDescription>
            A copy of your base CV is made for them. Select any passage to tailor it to their research.
          </DialogDescription>
        </DialogHeader>
        <div className="shrink-0 px-6 pt-4">
          <div className="relative">
            <Search className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              autoFocus
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Search professors, schools, programmes"
              className="pl-8"
              aria-label="Search candidates"
            />
          </div>
        </div>
        <DialogBody className="px-6 py-3">
          <ul className="-mx-2">
            {results.isLoading &&
              [0, 1, 2].map((i) => (
                <li key={i} className="px-2 py-1.5">
                  <Skeleton className="h-10" />
                </li>
              ))}
            {results.data?.items.map((c) => (
              <li key={c.id}>
                <button
                  type="button"
                  onClick={() => onPick(c.id)}
                  className="flex w-full items-center gap-3 rounded-md px-2 py-2 text-left hover:bg-accent"
                >
                  <Avatar name={c.professor_name} src={c.professor_photo_url} size="sm" />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-sm font-medium">{c.professor_name}</span>
                    <span className="block truncate type-caption">
                      {professorPlace(c.program_name, c.school_name)}
                    </span>
                  </span>
                  <ScoreBar score={c.similarity_score} />
                </button>
              </li>
            ))}
            {results.data && results.data.items.length === 0 && (
              <li className="px-2 py-3 type-meta">
                {term ? "No candidates match." : "No candidates yet: start a run to find professors."}
              </li>
            )}
          </ul>
        </DialogBody>
        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>Cancel</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
