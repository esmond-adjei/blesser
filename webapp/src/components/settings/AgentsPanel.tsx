import * as React from "react"
import {
  Bot,
  ClipboardList,
  FileText,
  FlaskConical,
  Globe,
  GraduationCap,
  Hand,
  Mail,
  School,
  Search,
  ShieldCheck,
  UserRound,
  UserRoundSearch,
  Zap,
  type LucideIcon,
} from "lucide-react"
import { groupTools, useAgentTasks, useAgentTools, type ToolEntry } from "../../lib/agents"
import type { AgentTask, AgentTool, AgentToolGroup } from "../../lib/types"
import { friendlyToolName, friendlyToolText } from "../../lib/toolActivity"
import { toastError, toastSuccess } from "../../lib/toast"
import { useAuth } from "../../lib/auth"
import * as api from "../../lib/api"
import { Alert, AlertDescription, SkeletonStack } from "../ui/feedback"
import { EmptyState } from "../feedback/EmptyState"
import { Button } from "../ui/button"
import { cn } from "../../lib/utils"
import { SettingDisclosure, SettingSection, SettingsPanel, Switch } from "./controls"

const TASKS: Record<string, { label: string; description: string }> = {
  discover_programs: { label: "Discover programmes", description: "Find schools and programmes that match your interests." },
  research_professor: { label: "Discover faculty", description: "Find potential supervisors at each school." },
  research_one_professor: { label: "Research a professor", description: "Review publications and assess a supervisor's research fit." },
  draft_email: { label: "Draft outreach emails", description: "Prepare a personal introduction for a potential supervisor." },
}

const GROUP_ICONS: Record<string, LucideIcon> = {
  web: Globe,
  scholar: GraduationCap,
  search: Search,
  runs: FlaskConical,
  schools: School,
  professors: UserRound,
  matches: UserRoundSearch,
  applications: ClipboardList,
  drafts: Mail,
  cv: FileText,
}

type Scope = "worker" | "assistant"

export function AgentsPanel() {
  const tools = useAgentTools()
  const tasks = useAgentTasks()
  const { user, updateUser } = useAuth()
  const [scope, setScope] = React.useState<Scope>("worker")
  const [saving, setSaving] = React.useState(false)
  const fullAccess = !!user?.agent_full_access
  const scopeTools = tools.tools.filter((tool) => tool.scope === scope)
  // Groups in their defined order (web first, documents last), not by tool name.
  const order = (entry: ToolEntry) => {
    const i = tools.groups.findIndex((g) => g.id === (entry.kind === "group" ? entry.group.id : entry.tool.group))
    return i < 0 ? tools.groups.length : i
  }
  const entries = groupTools(scopeTools, tools.groups).sort((a, b) => order(a) - order(b))

  async function run(label: string, fn: () => Promise<unknown>) {
    if (saving) return
    setSaving(true)
    try {
      await fn()
      toastSuccess(label)
    } catch (err) {
      toastError(err instanceof Error ? friendlyToolText(err.message) : "Couldn't save this setting")
    } finally {
      setSaving(false)
    }
  }

  return (
    <SettingsPanel title="Agents & tools" description="Choose what research agents and Gradis can do for you.">
      {tools.isLoading || tasks.isLoading ? (
        <SkeletonStack className="space-y-3" blocks={["h-12", "h-64"]} />
      ) : tools.isError || tasks.isError ? (
        <Alert variant="destructive"><AlertDescription>Couldn't load agent settings.</AlertDescription></Alert>
      ) : tools.tools.length === 0 ? (
        <EmptyState title="No tools available" description="Reload the page to check for available tools." />
      ) : (
        <>
          <div role="group" aria-label="Agent" className="mt-6 flex gap-1 rounded-xl bg-muted p-1">
            <ScopeTab active={scope === "worker"} onClick={() => setScope("worker")} icon={FlaskConical}>Research runs</ScopeTab>
            <ScopeTab active={scope === "assistant"} onClick={() => setScope("assistant")} icon={Bot}>Gradis</ScopeTab>
          </div>

          {scope === "assistant" && (
            <SettingSection title="Permissions" description="Lookups never ask. This decides whether Gradis asks before it saves, edits or deletes anything.">
              <div role="radiogroup" aria-label="Gradis permissions" className="grid gap-3 py-4 sm:grid-cols-2">
                <AccessOption
                  icon={Hand}
                  title="Ask before changes"
                  description="Gradis shows an approval card for each change. You choose which kinds of change ask, below."
                  checked={!fullAccess}
                  disabled={saving}
                  onSelect={() => void run("Gradis asks before changes", async () => updateUser(await api.setAgentFullAccess(false)))}
                />
                <AccessOption
                  icon={Zap}
                  title="Full access"
                  description="Gradis makes changes straight away, without asking. Turned-off tools stay off."
                  checked={fullAccess}
                  disabled={saving}
                  onSelect={() => void run("Gradis has full access", async () => updateUser(await api.setAgentFullAccess(true)))}
                />
              </div>
              {fullAccess && (
                <p className="flex items-start gap-2 pb-4 text-xs leading-relaxed text-muted-foreground">
                  <ShieldCheck className="mt-px size-3.5 shrink-0" aria-hidden />
                  Gradis still asks before sending your private details to a web page you didn't give it.
                </p>
              )}
            </SettingSection>
          )}

          {scope === "worker" && (
            <SettingSection title="Research activities" description="The steps your research agents take. Open one to choose what it may use.">
              {tasks.tasks.map((task) => (
                <TaskRow key={task.task_type} task={task} tools={scopeTools} groups={tools.groups} saving={saving} run={run} update={tasks.update} />
              ))}
            </SettingSection>
          )}

          <SettingSection
            title={scope === "worker" ? "What research agents can use" : "What Gradis can do"}
            description={`${scopeTools.filter((tool) => tool.enabled).length} of ${scopeTools.length} tools on. Each switch covers everything of that kind; open one to fine-tune.`}
          >
            {entries.map((entry) =>
              entry.kind === "group" ? (
                <ToolGroupRow
                  key={entry.group.id}
                  group={entry.group}
                  members={entry.members}
                  askable={scope === "assistant" && !fullAccess}
                  saving={saving}
                  onEnable={(next) => void run(`${entry.group.label} ${next ? "on" : "off"}`, () => tools.updateGroup(scope, entry.group.id, { enabled: next }))}
                  onAsk={(next) => void run(`${entry.group.label}: ${next ? "asks first" : "no longer asks"}`, () => tools.updateGroup(scope, entry.group.id, { confirm_required: next }))}
                  onTool={(tool, body) => void run(`${friendlyToolName(tool.name)} updated`, () => tools.update(tool.scope, tool.name, body))}
                />
              ) : (
                <ToolRow
                  key={entry.tool.name}
                  tool={entry.tool}
                  askable={scope === "assistant" && !fullAccess}
                  saving={saving}
                  onChange={(body) => void run(`${friendlyToolName(entry.tool.name)} updated`, () => tools.update(entry.tool.scope, entry.tool.name, body))}
                />
              ),
            )}
          </SettingSection>

          <p className="mt-4 text-xs leading-relaxed text-muted-foreground">
            Changes apply to the next step. Work already in progress finishes with its existing settings.
          </p>
        </>
      )}
    </SettingsPanel>
  )
}

function ScopeTab({ active, onClick, icon: Icon, children }: { active: boolean; onClick: () => void; icon: LucideIcon; children: React.ReactNode }) {
  return (
    <button
      type="button"
      aria-pressed={active}
      onClick={onClick}
      className={cn(
        "flex flex-1 cursor-pointer items-center justify-center gap-2 rounded-lg px-3 py-2 text-sm font-medium transition-colors",
        active ? "bg-background text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground",
      )}
    >
      <Icon className="size-4" aria-hidden /> {children}
    </button>
  )
}

function AccessOption({ icon: Icon, title, description, checked, disabled, onSelect }: {
  icon: LucideIcon
  title: string
  description: string
  checked: boolean
  disabled: boolean
  onSelect: () => void
}) {
  return (
    <button
      type="button"
      role="radio"
      aria-checked={checked}
      disabled={disabled}
      onClick={() => !checked && onSelect()}
      className={cn(
        "flex cursor-pointer items-start gap-3 rounded-xl border p-4 text-left transition-colors disabled:cursor-wait focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
        checked ? "border-primary bg-primary/5 ring-1 ring-primary" : "border-border hover:bg-accent/50",
      )}
    >
      <span className={cn("flex size-8 shrink-0 items-center justify-center rounded-lg", checked ? "bg-primary text-primary-foreground" : "bg-muted text-muted-foreground")}>
        <Icon className="size-4" aria-hidden />
      </span>
      <span className="min-w-0">
        <span className="block text-sm font-medium text-foreground">{title}</span>
        <span className="mt-1 block text-xs leading-relaxed text-muted-foreground">{description}</span>
      </span>
    </button>
  )
}

/** Every tool of one kind behind one switch; for Gradis, also whether its changes ask first. */
function ToolGroupRow({ group, members, askable, saving, onEnable, onAsk, onTool }: {
  group: AgentToolGroup
  members: AgentTool[]
  askable: boolean
  saving: boolean
  onEnable: (next: boolean) => void
  onAsk: (next: boolean) => void
  onTool: (tool: AgentTool, body: { enabled?: boolean; confirm_required?: boolean }) => void
}) {
  const label = friendlyToolText(group.label)
  const on = members.filter((tool) => tool.enabled).length
  const changes = members.filter((tool) => !tool.read_only)
  const asking = changes.filter((tool) => tool.confirm_required).length
  const Icon = GROUP_ICONS[group.id] ?? Bot
  const status = on === 0 ? "Off" : on < members.length ? `${on} of ${members.length} tools on` : `${members.length} tools`
  return (
    <SettingDisclosure
      title={label}
      description={`${friendlyToolText(group.description)} ${status}${askable && changes.length > 0 && on > 0 ? `, ${asking === 0 ? "never asks" : asking === changes.length ? "asks before changes" : "asks before some changes"}` : ""}.`}
      leading={<span className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-muted text-muted-foreground"><Icon className="size-4" aria-hidden /></span>}
      control={<Switch disabled={saving} checked={on === members.length} mixed={on > 0 && on < members.length} label={`Turn ${label} on or off`} onChange={onEnable} />}
    >
      {askable && changes.length > 0 && (
        <div className="flex items-center justify-between gap-4 border-b border-border/60 py-3">
          <div className="min-w-0">
            <p className="text-sm font-medium">Ask before changes</p>
            <p className="mt-0.5 text-xs text-muted-foreground">An approval card before Gradis saves, edits or deletes {label.toLowerCase()}.</p>
          </div>
          <Switch disabled={saving} checked={asking === changes.length} mixed={asking > 0 && asking < changes.length} label={`Ask before ${label} changes`} onChange={onAsk} />
        </div>
      )}
      <ul className="divide-y divide-border/60">
        {members.map((tool) => (
          <li key={tool.name}><ToolRow tool={tool} askable={askable} saving={saving} compact onChange={(body) => onTool(tool, body)} /></li>
        ))}
      </ul>
    </SettingDisclosure>
  )
}

function ToolRow({ tool, askable, saving, compact = false, onChange }: {
  tool: AgentTool
  askable: boolean
  saving: boolean
  compact?: boolean
  onChange: (body: { enabled?: boolean; confirm_required?: boolean }) => void
}) {
  const name = friendlyToolName(tool.name)
  return (
    <div className={cn("flex items-center gap-4", compact ? "py-2.5" : "py-4")}>
      <div className="min-w-0 flex-1">
        <p className="text-sm">{name}</p>
        {tool.description && <p className="mt-0.5 text-xs text-muted-foreground">{friendlyToolText(tool.description)}</p>}
      </div>
      {askable && !tool.read_only && tool.enabled && (
        <label className="flex shrink-0 cursor-pointer items-center gap-1.5 text-xs text-muted-foreground">
          <input
            type="checkbox"
            className="size-3.5 cursor-pointer accent-[var(--primary)]"
            checked={tool.confirm_required}
            disabled={saving}
            aria-label={`Ask before ${name}`}
            onChange={(event) => onChange({ confirm_required: event.target.checked })}
          />
          Ask first
        </label>
      )}
      <Switch disabled={saving} checked={tool.enabled} label={`Enable ${name}`} onChange={(next) => onChange({ enabled: next })} />
    </div>
  )
}

/** An activity and the kinds of tool it may use, picked by group. */
function TaskRow({ task, tools, groups, saving, run, update }: {
  task: AgentTask
  tools: AgentTool[]
  groups: AgentToolGroup[]
  saving: boolean
  run: (label: string, fn: () => Promise<unknown>) => Promise<void>
  update: (taskType: string, body: { enabled?: boolean; tools?: string[] }) => Promise<void>
}) {
  const presentation = TASKS[task.task_type] ?? { label: "Research activity", description: "An activity available in research runs." }
  const choices = groupTools(tools, groups).map((entry) =>
    entry.kind === "group"
      ? { id: entry.group.id, label: friendlyToolText(entry.group.label), names: entry.members.map((m) => m.name), enabled: entry.members.some((m) => m.enabled) }
      : { id: entry.tool.name, label: friendlyToolName(entry.tool.name), names: [entry.tool.name], enabled: entry.tool.enabled },
  )
  return (
    <SettingDisclosure
      title={presentation.label}
      description={task.enabled ? presentation.description : "Currently off."}
      control={<Switch disabled={saving} checked={task.enabled} label={`Enable ${presentation.label}`} onChange={(next) => void run(`${presentation.label} ${next ? "on" : "off"}`, () => update(task.task_type, { enabled: next }))} />}
    >
      <div className="space-y-3 py-3">
        <p className="text-xs leading-relaxed text-muted-foreground">What this activity may use. Keep at least one, or switch the activity off.</p>
        <div className="flex flex-wrap gap-2" role="group" aria-label={`Allowed tools for ${presentation.label}`}>
          {choices.map((choice) => {
            const allowedCount = choice.names.filter((n) => task.tools.includes(n)).length
            const allowed = allowedCount === choice.names.length
            const rest = task.tools.filter((n) => !choice.names.includes(n))
            const last = allowedCount > 0 && rest.length === 0
            return (
              <button
                key={choice.id}
                type="button"
                aria-pressed={allowed ? true : allowedCount > 0 ? "mixed" : false}
                disabled={saving || !choice.enabled || last}
                data-tooltip={last ? "Keep one selected, or switch this activity off" : !choice.enabled ? "Turn this on below first" : undefined}
                onClick={() => void run(`${presentation.label} updated`, () => update(task.task_type, { tools: allowed ? rest : [...rest, ...choice.names] }))}
                className={cn(
                  "cursor-pointer rounded-lg border px-3 py-2 text-xs transition-colors disabled:cursor-default disabled:opacity-50",
                  allowedCount > 0 ? "border-primary/35 bg-primary/10 text-foreground" : "border-border text-muted-foreground hover:bg-accent",
                )}
              >{choice.label}</button>
            )
          })}
        </div>
        <Button size="sm" variant="outline" disabled={saving} onClick={() => void run(`${presentation.label} defaults restored`, () => update(task.task_type, { tools: [] }))}>Restore defaults</Button>
      </div>
    </SettingDisclosure>
  )
}
