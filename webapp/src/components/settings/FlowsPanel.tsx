import * as React from "react"
import { useQuery, useQueryClient } from "@tanstack/react-query"
import { ChevronRight, Copy, Lock, Pencil, Trash2 } from "lucide-react"
import * as api from "../../lib/api"
import { useAgentTools } from "../../lib/agents"
import { toastError, toastSuccess } from "../../lib/toast"
import { cn } from "../../lib/utils"
import { Button } from "../ui/button"
import { SkeletonStack } from "../ui/feedback"
import { Input, Textarea } from "../ui/input"
import { SettingsPanel, Switch } from "./controls"
import { friendlyToolName, friendlyToolText } from "../../lib/toolActivity"

const FLOWS_KEY = ["flows"]
const MAX_INSTRUCTIONS = 1500

function changes(flow: api.AgentFlow, labels: Record<string, string>): string {
  const out: string[] = []
  for (const s of flow.steps) {
    const label = labels[s.type] ?? "Research step"
    if (!s.enabled) out.push(`${label} off`)
    else {
      if (s.tool_groups.length || s.tools.length) out.push(`${label}: tools narrowed`)
      if (s.instructions) out.push(`${label}: instructions`)
    }
  }
  return out.length ? out.join(", ") : "Same as Standard"
}

/** Duplicate Standard to switch steps off, narrow tools or add instructions; flows can only narrow. */
export function FlowsPanel() {
  const qc = useQueryClient()
  const { data, isLoading } = useQuery({ queryKey: FLOWS_KEY, queryFn: api.listFlows })
  const [editing, setEditing] = React.useState<string | null>(null)
  const labels = Object.fromEntries((data?.steps ?? []).map((s) => [s.type, s.label]))
  const refresh = () => qc.invalidateQueries({ queryKey: FLOWS_KEY })

  async function duplicate(flow: api.AgentFlow) {
    try {
      const created = await api.duplicateFlow(flow.id, flow.builtin ? "My research flow" : `${flow.name} copy`)
      await refresh()
      setEditing(created.id)
      toastSuccess("Flow created. Make your changes and save.")
    } catch (err) {
      toastError(err)
    }
  }

  async function remove(flow: api.AgentFlow) {
    if (!window.confirm(`Delete "${flow.name}"? Runs that used it switch to Standard.`)) return
    try {
      await api.deleteFlow(flow.id)
      await refresh()
      toastSuccess("Flow deleted")
    } catch (err) {
      toastError(err)
    }
  }

  return (
    <SettingsPanel title="Flows" description="Shape your research process with reusable steps and instructions.">
      <div className="rounded-xl border border-border bg-muted/30 p-4 text-sm leading-relaxed text-muted-foreground">
        Duplicate Standard to create your own flow, then choose it when starting a run. You can skip steps, limit available tools or add instructions. Budgets, approvals and disabled tools always apply.
      </div>

      {isLoading || !data ? (
        <SkeletonStack className="mt-6 space-y-3" blocks={["h-16", "h-16"]} />
      ) : (
        <ul className="mt-6 space-y-3">
          {data.flows.map((flow) => (
            <li key={flow.id} className="rounded-xl border border-border bg-card">
              <div className="flex flex-wrap items-center gap-3 p-4">
                <div className="min-w-0 basis-full sm:basis-auto sm:flex-1">
                  <p className="flex items-center gap-2 text-sm font-semibold">
                    {flow.name}
                    {flow.builtin && (
                      <span className="inline-flex items-center gap-1 rounded-full bg-muted px-2 py-0.5 text-xs font-medium text-muted-foreground">
                        <Lock className="size-3" /> Built-in
                      </span>
                    )}
                  </p>
                  <p className="mt-0.5 type-caption">
                    {flow.builtin ? "Every step on, every enabled tool available." : changes(flow, labels)}
                  </p>
                </div>
                {!flow.builtin && (
                  <Button size="sm" variant="ghost" onClick={() => setEditing(editing === flow.id ? null : flow.id)}>
                    <Pencil /> {editing === flow.id ? "Close" : "Edit"}
                  </Button>
                )}
                <Button data-tooltip="Make an editable copy of this research pipeline" size="sm" variant="outline" onClick={() => void duplicate(flow)}>
                  <Copy /> Duplicate
                </Button>
                {!flow.builtin && (
                  <Button size="icon" variant="ghost" aria-label={`Delete ${flow.name}`} onClick={() => void remove(flow)}>
                    <Trash2 />
                  </Button>
                )}
              </div>
              {editing === flow.id && (
                <FlowEditor
                  key={flow.id}
                  flow={flow}
                  stepMeta={data.steps}
                  onSaved={async () => {
                    await refresh()
                    setEditing(null)
                  }}
                />
              )}
            </li>
          ))}
        </ul>
      )}
    </SettingsPanel>
  )
}

function FlowEditor({
  flow,
  stepMeta,
  onSaved,
}: {
  flow: api.AgentFlow
  stepMeta: api.FlowList["steps"]
  onSaved: () => Promise<void>
}) {
  const { tools, groups } = useAgentTools()
  const workerTools = tools.filter((t) => t.scope === "worker")
  const [name, setName] = React.useState(flow.name)
  const [steps, setSteps] = React.useState<api.FlowStep[]>(flow.steps)
  const [open, setOpen] = React.useState<string | null>(null)
  const [saving, setSaving] = React.useState(false)
  const workerGroups = groups.filter((g) => g.tools.some((t) => workerTools.some((w) => w.name === t)))

  const update = (type: string, patch: Partial<api.FlowStep>) =>
    setSteps((all) => all.map((s) => (s.type === type ? { ...s, ...patch } : s)))
  const toggleIn = (list: string[], v: string) => (list.includes(v) ? list.filter((x) => x !== v) : [...list, v])

  async function save() {
    setSaving(true)
    try {
      await api.updateFlow(flow.id, { name: name.trim(), steps })
      toastSuccess("Flow saved")
      await onSaved()
    } catch (err) {
      toastError(err)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="space-y-4 border-t border-border p-4">
      <div className="max-w-sm">
        <label htmlFor={`flow-name-${flow.id}`} className="mb-1.5 block text-compact font-medium">Name</label>
        <Input id={`flow-name-${flow.id}`} value={name} maxLength={80} onChange={(e) => setName(e.target.value)} />
      </div>
      <ol className="space-y-2">
        {steps.map((step, i) => {
          const meta = stepMeta.find((m) => m.type === step.type)
          const narrowed = step.tool_groups.length + step.tools.length > 0
          const expanded = open === step.type
          return (
            <li key={step.type} className={cn("rounded-lg border border-border", !step.enabled && "bg-muted/40")}>
              <div className="flex items-center gap-3 p-3">
                <span className="flex size-6 shrink-0 items-center justify-center rounded-full bg-muted text-xs font-semibold">{i + 1}</span>
                <button
                  type="button"
                  onClick={() => setOpen(expanded ? null : step.type)}
                  aria-expanded={expanded}
                  className="flex min-w-0 flex-1 cursor-pointer items-center gap-1.5 text-left"
                >
                  <ChevronRight className={cn("size-4 shrink-0 text-muted-foreground transition-transform", expanded && "rotate-90")} />
                  <span className="min-w-0">
                    <span className={cn("block text-sm font-medium", !step.enabled && "text-muted-foreground line-through")}>
                      {meta?.label ?? "Research step"}
                    </span>
                    <span className="block truncate type-caption">
                      {!step.enabled
                        ? "Off: this step is skipped"
                        : [narrowed ? "Tools narrowed" : "All enabled tools", step.instructions ? "Has instructions" : null]
                            .filter(Boolean)
                            .join(", ")}
                    </span>
                  </span>
                </button>
                <Switch
                  checked={step.enabled}
                  label={`Run step ${meta?.label ?? "Research step"}`}
                  onChange={(v) => update(step.type, { enabled: v })}
                />
              </div>
              {expanded && step.enabled && (
                <div className="space-y-4 border-t border-border px-3 py-4 sm:pl-12">
                  <p className="type-caption">{friendlyToolText(meta?.summary ?? "")}</p>
                  <div>
                    <p className="text-compact font-medium">Tools this step may use</p>
                    <p className="mt-0.5 type-caption">Pick none to allow every enabled tool.</p>
                    <div className="mt-2 flex flex-wrap gap-1.5">
                      {workerGroups.map((g) => (
                        <Chip key={g.id} active={step.tool_groups.includes(g.id)} onClick={() => update(step.type, { tool_groups: toggleIn(step.tool_groups, g.id) })}>
                          {g.label} group
                        </Chip>
                      ))}
                      {workerTools
                        .filter((t) => !workerGroups.some((g) => g.tools.includes(t.name)))
                        .map((t) => (
                          <Chip key={friendlyToolName(t.name)} active={step.tools.includes(t.name)} onClick={() => update(step.type, { tools: toggleIn(step.tools, t.name) })}>
                            {friendlyToolName(t.name)}
                          </Chip>
                        ))}
                    </div>
                  </div>
                  <div>
                    <label htmlFor={`flow-${flow.id}-${step.type}`} className="text-compact font-medium">Extra instructions</label>
                    <Textarea
                      id={`flow-${flow.id}-${step.type}`}
                      rows={3}
                      maxLength={MAX_INSTRUCTIONS}
                      className="mt-1.5"
                      value={step.instructions}
                      onChange={(e) => update(step.type, { instructions: e.target.value })}
                      placeholder="e.g. Prefer labs with recent publications in top robotics venues."
                    />
                    <p className="mt-1 text-right type-caption tabular-nums">
                      {step.instructions.length}/{MAX_INSTRUCTIONS}
                    </p>
                  </div>
                </div>
              )}
            </li>
          )
        })}
      </ol>
      <div className="flex justify-end">
        <Button data-tooltip="Save the steps, tools and instructions for this pipeline" onClick={() => void save()} disabled={saving || !name.trim()}>
          {saving ? "Saving…" : "Save flow"}
        </Button>
      </div>
    </div>
  )
}

function Chip({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      type="button"
      aria-pressed={active}
      onClick={onClick}
      className={cn(
        "cursor-pointer rounded-lg border px-3 py-2 text-xs transition-colors",
        active ? "border-primary/50 bg-primary/10 text-foreground" : "border-border text-muted-foreground hover:bg-accent",
      )}
    >
      {children}
    </button>
  )
}
