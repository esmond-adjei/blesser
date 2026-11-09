import * as React from "react"
import { Link, useNavigate } from "react-router-dom"
import { useQueryClient } from "@tanstack/react-query"
import { FolderKanban, Plus } from "lucide-react"
import { Button, Chip, Field } from "@blesser/ui"
import { SettingsSection } from "../../components/settings/controls"
import { EmptyState, ErrorState } from "../../components/feedback/EmptyState"
import { CompletenessMeter, KitSkeleton } from "../../components/kit/parts"
import { Dialog, DialogBody, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "../../components/ui/dialog"
import { formatAgo } from "../../lib/format"
import { KIT_PITCH, emptyProject, stageLabel } from "../../lib/kit"
import { createProject, kitKeys, useProjects } from "../../lib/kitApi"
import { toastError } from "../../lib/toast"

export function ProjectsTab() {
  const projects = useProjects()
  const [creating, setCreating] = React.useState(false)
  const list = projects.data ?? []

  return (
    <SettingsSection id="kit-projects" title="Projects" description="Ventures, research and community work you apply with, each told once in full.">
      {projects.isLoading ? (
        <KitSkeleton rows={2} />
      ) : projects.isError ? (
        <ErrorState title="Your projects didn't load" description="Check your connection and try again." onRetry={() => void projects.refetch()} />
      ) : list.length === 0 ? (
        <EmptyState
          title="Add your first project"
          description={`A startup, a research project or community work: its story, team, money and documents in one place. ${KIT_PITCH}`}
          action={<Button size="sm" variant="brand" icon={<Plus />} onClick={() => setCreating(true)}>New project</Button>}
        />
      ) : (
        <div className="space-y-4">
          <div className="flex justify-end">
            <Button size="sm" variant="secondary" icon={<Plus />} onClick={() => setCreating(true)}>New project</Button>
          </div>
          <ul className="grid gap-3 sm:grid-cols-2">
            {list.map((p) => (
              <li key={p.id}>
                <Link
                  to={`/kit/projects/${p.id}`}
                  className="group flex h-full flex-col gap-4 rounded-lg border border-separator bg-surface p-4 transition-[border-color,box-shadow] duration-160 hover:border-control-border hover:shadow-elevation-1 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus"
                >
                  <div className="flex min-w-0 items-start gap-3">
                    <span aria-hidden="true" className="grid size-10 shrink-0 place-items-center rounded-md bg-forest-soft font-display text-base font-semibold text-link">
                      {(p.name.trim()[0] ?? "?").toUpperCase()}
                    </span>
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-headline text-ink group-hover:underline">{p.name || "Untitled project"}</p>
                      <p className="line-clamp-2 text-footnote text-ink-secondary">{p.tagline || "No tagline yet"}</p>
                    </div>
                  </div>
                  <div className="flex flex-wrap items-center gap-2 text-footnote text-ink-tertiary">
                    <Chip>{stageLabel(p.stage)}</Chip>
                    {p.sector ? <Chip>{p.sector}</Chip> : null}
                    <span className="ml-auto">Edited {formatAgo(p.updated_at)}</span>
                  </div>
                  <CompletenessMeter value={p.completeness} className="mt-auto" />
                </Link>
              </li>
            ))}
          </ul>
        </div>
      )}
      <NewProjectDialog open={creating} onOpenChange={setCreating} />
    </SettingsSection>
  )
}

function NewProjectDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  const [name, setName] = React.useState("")
  const [busy, setBusy] = React.useState(false)
  const client = useQueryClient()
  const navigate = useNavigate()
  const close = React.useCallback(() => {
    onOpenChange(false)
    setName("")
  }, [onOpenChange])

  return (
    <Dialog open={open} onOpenChange={(o) => (o ? onOpenChange(true) : close())}>
      <DialogContent onClose={close} className="max-w-md">
        <DialogHeader>
          <DialogTitle>New project</DialogTitle>
          <DialogDescription>Start with a name. You can fill in the rest at your own pace.</DialogDescription>
        </DialogHeader>
        <DialogBody>
          <form
            className="space-y-4"
            onSubmit={async (e) => {
              e.preventDefault()
              if (!name.trim()) return
              setBusy(true)
              try {
                const project = await createProject(emptyProject(name.trim()))
                client.setQueryData(kitKeys.project(project.id), project)
                void client.invalidateQueries({ queryKey: kitKeys.projects })
                close()
                navigate(`/kit/projects/${project.id}`)
              } catch (err) {
                toastError(err, "Couldn't create the project")
              } finally {
                setBusy(false)
              }
            }}
          >
            <Field label="Project name" value={name} onChange={(e) => setName(e.target.value)} maxLength={120} placeholder="Siwa" required autoFocus />
            <div className="flex justify-end gap-2 pt-1">
              <Button size="sm" variant="quiet" onClick={close}>Cancel</Button>
              <Button type="submit" size="sm" variant="brand" disabled={busy || !name.trim()} icon={<FolderKanban />}>Create project</Button>
            </div>
          </form>
        </DialogBody>
      </DialogContent>
    </Dialog>
  )
}
