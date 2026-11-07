import { useQuery } from "@tanstack/react-query"
import { getChatModelInfo, type ChatModelSel } from "../../lib/gradis"
import { useGradis } from "./GradisProvider"
import { cn } from "../../lib/utils"
import { Gauge } from "lucide-react"
import { useSettingsParam } from "../dialogs/SettingsDialog"
import { Popover } from "../ui/popover"

export function ChatControls() {
  const { activeId, modelSel, effort, setEffort, messages, contextUsage, composer, sending, attachments, contextChips } = useGradis()
  const { data } = useQuery({ queryKey: ["chat-model-info", modelSel, activeId, messages.length], queryFn: () => getChatModelInfo(modelSel, activeId), staleTime: 30_000 })
  const [, setSettingsTab] = useSettingsParam()
  // Set once per model in Settings → Models; unset leaves a count only.
  const limit = data?.context_window ?? null
  const live = sending && contextUsage?.model === data?.model && contextUsage?.provider === data?.provider ? contextUsage : null
  const attachedTokens = attachments.reduce((total, item) => total + (item.kind === "image" ? 4096 : Math.ceil(item.text.length / 4)), 0)
  const selectedTokens = contextChips.reduce((total, chip) => total + (chip.tokens ?? 0), 0)
  const tokens = (live?.input_tokens ?? data?.input_tokens ?? 0) + Math.ceil(composer.length / 4) + attachedTokens + selectedTokens
  const fraction = limit ? Math.min(tokens / limit, 1) : 0
  const label = limit
    ? `${Math.round(fraction * 100)}% of context used: ${tokens.toLocaleString()} of ${limit.toLocaleString()} tokens`
    : `${tokens.toLocaleString()} context tokens, window size not set`
  return <>
    {/* In a narrow composer, a gauge with the select laid invisibly over it. */}
    {!!data?.effort_levels.length && <label data-tooltip={`Reasoning effort: ${effort ? (effort === "xhigh" ? "extra high" : effort) : "auto"}`} className="relative flex items-center gap-1 rounded-md text-xs text-muted-foreground @max-[24rem]/composer:size-7 @max-[24rem]/composer:justify-center @max-[24rem]/composer:hover:bg-accent">
      <span className="sr-only">Reasoning effort</span>
      <Gauge aria-hidden className="hidden size-3.5 @max-[24rem]/composer:block" />
      <select aria-label="Reasoning effort" disabled={sending} value={effort ?? ""} onChange={e => {
        const value = e.target.value
        const next: ChatModelSel["effort"] = value === "low" || value === "medium" || value === "high" || value === "xhigh" ? value : undefined
        setEffort(next)
      }} className="max-w-24 cursor-pointer rounded bg-transparent py-1.5 outline-none @max-[24rem]/composer:absolute @max-[24rem]/composer:inset-0 @max-[24rem]/composer:max-w-none @max-[24rem]/composer:opacity-0"><option value="">Auto effort</option>{data.effort_levels.map(level => <option key={level} value={level}>{level === "xhigh" ? "Extra high" : level[0].toUpperCase() + level.slice(1)} effort</option>)}</select>
    </label>}
    <Popover label="Model context" side="top" trigger={props => <button {...props} type="button" aria-label={label} className="flex size-7 shrink-0 cursor-pointer items-center justify-center rounded-full text-muted-foreground hover:bg-accent">
      <svg viewBox="0 0 28 28" className="size-5 -rotate-90" aria-hidden><circle cx="14" cy="14" r="10" fill="none" stroke="currentColor" strokeOpacity="0.2" strokeWidth="3" /><circle cx="14" cy="14" r="10" fill="none" stroke={fraction >= .9 ? "var(--destructive)" : "var(--primary)"} strokeWidth="3" strokeDasharray={`${fraction * 62.83} 62.83`} strokeLinecap="round" /></svg>
    </button>}>
      {() => <div className="w-64 space-y-3 p-2 text-sm">
        <p className="font-medium">{data?.model ?? "Model context"}</p>
        <div className="space-y-1.5 cursor-help" 
        data-tooltip="Token counts between replies are estimates. The provider's last prompt count is used during a reply. This measures context, not billing."
        >
          <div role="meter" aria-label="Context used" aria-valuemin={0} aria-valuemax={limit ?? undefined} aria-valuenow={limit ? Math.min(tokens, limit) : tokens} aria-valuetext={label}>
            <ContextBar fraction={fraction} />
          </div>
          <div className="flex justify-between gap-2 text-xs text-muted-foreground tabular-nums">
            <span>{tokens.toLocaleString()} / {limit ? limit.toLocaleString() : "?"} tokens</span>
            {limit ? <span>{Math.round(fraction * 100)}%</span> : <span>Window not set</span>}
          </div>
        </div>
        {!limit && modelSel === "auto" && <p className="text-xs text-muted-foreground">The included model's context window isn't configured yet.</p>}
        {!limit && modelSel !== "auto" && <p className="text-xs"><button type="button" onClick={() => setSettingsTab("models")} className="cursor-pointer text-primary underline-offset-2 hover:underline">Set this model's context window</button> to see how full it is.</p>}
      </div>}
    </Popover>
  </>
}

function ContextBar({ fraction }: { fraction: number }) {
  return (
    <span aria-hidden className="block h-1.5 w-full overflow-hidden rounded-full bg-muted-foreground/20">
      <span
        className={cn("block h-full rounded-full transition-[width] duration-300", fraction >= 0.9 ? "bg-destructive" : "bg-primary")}
        style={{ width: `${fraction * 100}%` }}
      />
    </span>
  )
}
