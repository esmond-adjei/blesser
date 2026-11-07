import { ProviderIcon } from "../ui/ProviderIcon"
import * as React from "react"
import { useQuery } from "@tanstack/react-query"
import { useProviderCatalog, useProviderConfigs } from "../../lib/providers"
import * as api from "../../lib/api"
import { useAuth } from "../../lib/auth"
import { toastError, toastSuccess } from "../../lib/toast"
import { Alert, AlertDescription, SkeletonStack } from "../ui/feedback"
import { Badge } from "../ui/badge"
import { Button } from "../ui/button"
import { Field, Input } from "../ui/input"
import { Select } from "../ui/select"
import { Cpu, KeyRound, Pencil, Plus, Star, Trash2 } from "lucide-react"
import { RowMenu } from "../ui/row-menu"
import { MenuItem, MenuSeparator } from "../ui/menu"
import { SettingRow, SettingSection, SettingsPanel, Switch } from "./controls"
import type { ProviderCatalogEntry } from "../../lib/types"

function providerLabel(provider: string) {
  const labels: Record<string, string> = { openai: "OpenAI", anthropic: "Anthropic", gemini: "Google Gemini", ollama: "Ollama", openai_compatible: "OpenAI compatible" }
  return labels[provider] ?? provider.replace(/[_-]/g, " ").replace(/^./, (letter) => letter.toUpperCase())
}

function ModelForm({
  provider,
  providerLocked,
  hasKey,
  catalogProviders,
  initial,
  activateOnSave,
  onDone,
}: {
  provider: string
  providerLocked: boolean
  hasKey: boolean
  catalogProviders: ProviderCatalogEntry[]
  initial: { model: string; apiKey: string; baseUrl: string; contextWindow: number | null }
  activateOnSave: boolean
  onDone: () => void
}) {
  const { update } = useProviderConfigs()
  const [selected, setSelected] = React.useState(provider)
  const [model, setModel] = React.useState(initial.model)
  const [apiKey, setApiKey] = React.useState(initial.apiKey)
  const [baseUrl, setBaseUrl] = React.useState(initial.baseUrl)
  const [contextWindow, setContextWindow] = React.useState(initial.contextWindow?.toString() ?? "")
  const [busy, setBusy] = React.useState<string | null>(null)
  const [testResult, setTestResult] = React.useState<string | null>(null)

  const entry = catalogProviders.find((p) => p.provider === selected)
  const showBaseUrl = (entry?.base_url_required ?? false) || initial.baseUrl !== ""
  const modelPlaceholder = entry?.default_model || "Model id"

  async function onSave() {
    setBusy("save")
    try {
      const body: Parameters<typeof update>[1] = {
        model: model.trim(),
        context_window: windowTokens,
      }
      if (apiKey) body.api_key = apiKey
      if (showBaseUrl) body.base_url = baseUrl.trim()
      if (activateOnSave) body.is_active = true
      await update(selected, body)
      toastSuccess(activateOnSave ? `${providerLabel(selected)} model added` : "Model saved")
      onDone()
    } catch (err) {
      toastError(err)
    } finally {
      setBusy(null)
    }
  }

  async function onTest() {
    setBusy("test")
    setTestResult(null)
    try {
      const result = await api.testProvider(selected, {
        base_url: showBaseUrl ? baseUrl.trim() || undefined : undefined,
        api_key: apiKey || undefined,
      })
      if (result.ok) {
        setTestResult(
          result.count > 0
            ? `Connected. ${result.count} model${result.count === 1 ? "" : "s"}: ${result.models.slice(0, 5).join(", ")}${result.count > 5 ? "…" : ""}`
            : "Connected. the provider answered but listed no models.",
        )
        toastSuccess("Connection works")
      } else {
        setTestResult(result.error || "Unreachable.")
        toastError(result.error || "Connection failed")
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : "Connection failed"
      setTestResult(message)
      toastError(err)
    } finally {
      setBusy(null)
    }
  }

  // Blank is "not set"; anything else must be a whole number of tokens.
  const windowTokens = contextWindow.trim() === "" ? null : Number(contextWindow)
  const windowValid = windowTokens === null || (Number.isInteger(windowTokens) && windowTokens >= 1 && windowTokens <= 10_000_000)
  const canSave = model.trim() !== "" && windowValid && busy === null

  return (
    <div className="space-y-4 rounded-xl border border-border bg-muted/30 p-4">
      <div>
        <h3 className="text-sm font-semibold">{activateOnSave ? "Add a connection" : "Connection details"}</h3>
        <p className="mt-1 text-xs leading-relaxed text-muted-foreground">Choose a provider and model, then test the connection before saving.</p>
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Provider">
          {providerLocked ? (
            <Input value={providerLabel(selected)} disabled spellCheck={false} />
          ) : (
            <Select
              value={selected}
              onChange={(e) => {
                const next = e.target.value
                setSelected(next)
                setTestResult(null)
                const nextEntry = catalogProviders.find((p) => p.provider === next)
                if (nextEntry && !model) setModel(nextEntry.default_model)
              }}
              aria-label="Provider"
            >
              {catalogProviders.map((p) => (
                <option key={p.provider} value={p.provider}>
                  {providerLabel(p.provider)}
                </option>
              ))}
            </Select>
          )}
        </Field>
        <Field label="Model">
          <Input
            value={model}
            onChange={(e) => setModel(e.target.value)}
            placeholder={modelPlaceholder}
            spellCheck={false}
          />
        </Field>
        <Field label={hasKey ? "API key (saved, leave blank to keep)" : "API key"}>
          <Input
            type="password"
            autoComplete="off"
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
            placeholder={entry?.key_required ? "Required" : "Optional for local servers"}
          />
        </Field>
        <Field label="Context window (tokens)">
          <Input
            type="number"
            inputMode="numeric"
            min={1}
            max={10_000_000}
            step={1}
            value={contextWindow}
            onChange={(e) => setContextWindow(e.target.value)}
            placeholder="Optional, e.g. 128000"
            aria-invalid={!windowValid}
          />
        </Field>
        {showBaseUrl && (
          <Field label="Server address">
            <Input
              value={baseUrl}
              onChange={(e) => setBaseUrl(e.target.value)}
              placeholder={entry?.default_base_url || "https://…"}
              spellCheck={false}
            />
          </Field>
        )}
      </div>
      {!showBaseUrl && entry?.default_base_url && (
        <p className="type-caption">
          The default server address is {entry.default_base_url}. No setup needed.
        </p>
      )}
      {!windowValid && <p className="type-caption text-destructive">Enter the context window as a whole number of tokens, up to 10,000,000.</p>}
      <p className="type-caption">
        The context window sets how full the chat's usage bar reads. Find it on the model's page at your provider. Leave it blank if you don't know it.
      </p>
      {testResult && <p className="type-caption">{testResult}</p>}
      <div className="flex flex-wrap gap-2">
        <Button data-tooltip="Save this model and its connection settings" size="sm" disabled={!canSave} onClick={() => void onSave()}>
          {busy === "save" ? "Saving…" : activateOnSave ? "Add model" : "Save"}
        </Button>
        <Button data-tooltip="Check that Graduator can connect to this model" size="sm" variant="outline" disabled={busy !== null} onClick={() => void onTest()}>
          {busy === "test" ? "Testing…" : "Test connection"}
        </Button>
        <Button size="sm" variant="ghost" disabled={busy !== null} onClick={onDone}>
          Cancel
        </Button>
      </div>
    </div>
  )
}

/** Default chooses Auto or your own model; "Your models" are configured rows. */
export function ModelsPanel() {
  const { configs, isLoading, isError, update } = useProviderConfigs()
  const { providers, system, isLoading: catLoading, isError: catError } = useProviderCatalog()
  const { user, updateUser } = useAuth()
  const { data: plan } = useQuery({ queryKey: ["plan"], queryFn: api.getPlan, staleTime: 60_000 })
  const [adding, setAdding] = React.useState(false)
  const [editing, setEditing] = React.useState<string | null>(null)
  const preferOwn = !!user?.prefer_own_model
  const allowance = plan?.system_model

  async function run(label: string, fn: () => Promise<unknown>) {
    try {
      await fn()
      toastSuccess(label)
    } catch (err) {
      toastError(err)
    }
  }

  // The registry seeds one row per provider; "yours" are the ones you set up.
  const mine = configs.filter((c) => c.model !== "" || c.has_key)
  const loading = isLoading || catLoading
  const error = isError || catError

  const ownDefault = mine.find((config) => config.is_active && config.enabled !== false && config.model)

  return (
    <SettingsPanel
      title="Models"
      description="Choose the AI for new chats and research. Use the included model, or connect one of your own."
      action={!adding && <Button size="sm" onClick={() => { setAdding(true); setEditing(null) }}><Plus /> Add model</Button>}
    >
      {loading ? (
        <SkeletonStack className="mt-6 space-y-3" blocks={["h-24", "h-48"]} />
      ) : error ? (
        <Alert variant="destructive" className="mt-6"><AlertDescription>Couldn't load your models. Please try again.</AlertDescription></Alert>
      ) : <>
        {adding && <div className="mt-6"><ModelForm
          provider={providers[0]?.provider ?? "openai"} providerLocked={false} hasKey={false}
          catalogProviders={providers} initial={{ model: "", apiKey: "", baseUrl: "", contextWindow: null }} activateOnSave onDone={() => setAdding(false)}
        /></div>}

        <SettingSection title="Start new work with" description="You can choose a different model for any chat or research run.">
          <div className="flex items-start gap-3 py-4">
            <span className="rounded-lg bg-primary/10 p-2 text-primary"><Cpu className="size-5" /></span>
            <div className="min-w-0 flex-1">
              <p className="text-sm font-semibold">{preferOwn && ownDefault ? providerLabel(ownDefault.provider) : "Auto"}</p>
              <p className="mt-1 break-words text-xs text-muted-foreground">{preferOwn && ownDefault ? ownDefault.model : "The included model, ready to use without your own API key."}</p>
              {preferOwn && !ownDefault && <p className="mt-1 text-xs text-muted-foreground">Auto is used until your default model is available.</p>}
            </div>
            <Badge variant="secondary">Current default</Badge>
          </div>
          <SettingRow title="Use my model by default"
            description={ownDefault ? `Use ${providerLabel(ownDefault.provider)} for new chats and runs. Turn this off to start with Auto.` : "Add a model and make it your default to use it for new work."}
            control={<Switch checked={preferOwn} disabled={!ownDefault && !preferOwn} label="Use my model by default" onChange={(next) => void run(next ? "New work uses your model" : "New work uses Auto", async () => updateUser(await api.setPreferOwnModel(next)))} />}
          />
        </SettingSection>

        <SettingSection title="Your connections" description="Saved models stay available in the model picker when switched on.">
          {mine.length === 0 ? <div className="py-7 text-center">
            <KeyRound className="mx-auto size-6 text-muted-foreground" />
            <p className="mt-3 text-sm font-medium">Bring your own model</p>
            <p className="mx-auto mt-1 max-w-sm text-xs leading-relaxed text-muted-foreground">Connect a hosted provider with an API key, or use a local model server.</p>
            {!adding && <Button variant="outline" size="sm" className="mt-4" onClick={() => setAdding(true)}><Plus /> Add model</Button>}
          </div> : mine.map((cfg) => {
            const entry = providers.find((provider) => provider.provider === cfg.provider)
            return <div key={cfg.provider} className="py-5">
              <div className="flex items-start gap-3">
                <span className="rounded-lg bg-muted p-2 text-muted-foreground"><ProviderIcon provider={cfg.provider} className="size-4" /></span>
                <div className="min-w-0 flex-1">
                  <h4 className="text-sm font-semibold">{providerLabel(cfg.provider)}</h4>
                  <p className="mt-1 break-words text-sm text-muted-foreground">{cfg.model || "Choose a model to finish setup"}</p>
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {cfg.is_active && <Badge variant="secondary"><Star className="mr-1 size-3" /> Your default</Badge>}
                    <Badge variant="outline">{cfg.has_key ? "API key saved" : entry?.key_required ? "API key needed" : "No API key needed"}</Badge>
                    {cfg.model && <Badge variant="outline">{cfg.context_window ? `${cfg.context_window.toLocaleString()} token context` : "Context window not set"}</Badge>}
                    {cfg.enabled === false && <Badge variant="outline">Switched off</Badge>}
                  </div>
                </div>
                <div className="flex shrink-0 items-center gap-1">
                  {cfg.model && <Switch checked={cfg.enabled !== false} label={`Use ${providerLabel(cfg.provider)}`} title="Make this model available in chats and research" onChange={(next) => void run(`${providerLabel(cfg.provider)} ${next ? "switched on" : "switched off"}`, () => update(cfg.provider, { enabled: next }))} />}
                  <RowMenu variant="header" label={`Manage ${providerLabel(cfg.provider)}`}>
                    {!cfg.is_active && cfg.model && <MenuItem onSelect={() => void run(`${providerLabel(cfg.provider)} is your default model`, () => update(cfg.provider, { is_active: true }))}><Star /> Make default</MenuItem>}
                    <MenuItem onSelect={() => { setEditing(cfg.provider); setAdding(false) }}><Pencil /> Edit connection</MenuItem>
                    <MenuSeparator />
                    <MenuItem destructive onSelect={() => void run("Model removed", () => update(cfg.provider, { model: "", api_key: "", base_url: "", context_window: null, is_active: false }))}><Trash2 /> Remove</MenuItem>
                  </RowMenu>
                </div>
              </div>
              {cfg.enabled === false && <p className="mt-3 text-xs leading-relaxed text-muted-foreground">This connection is saved. Chats and runs that selected it use Auto while it is off.</p>}
              {editing === cfg.provider && <div className="mt-4"><ModelForm provider={cfg.provider} providerLocked hasKey={cfg.has_key} catalogProviders={providers} initial={{ model: cfg.model, apiKey: "", baseUrl: cfg.base_url, contextWindow: cfg.context_window }} activateOnSave={false} onDone={() => setEditing(null)} /></div>}
            </div>
          })}
        </SettingSection>

        {system && <SettingSection title="Included model" description="Auto is managed by Graduator and stays available alongside your own connections.">
          <div className="py-4">
            <div className="flex flex-wrap items-center gap-2"><p className="text-sm font-semibold">Auto</p><Badge variant="outline">Included</Badge></div>
            <p className="mt-2 break-words text-xs text-muted-foreground">{providerLabel(system.provider)}{system.model ? `, ${system.model}` : ""}{system.context_window ? `, ${system.context_window.toLocaleString()} token context` : ""}</p>
            {allowance && <p className="mt-3 text-xs leading-relaxed text-muted-foreground">{allowance.daily_limit == null ? "Unlimited on your plan." : `${Math.max(allowance.daily_limit - allowance.used_today, 0).toLocaleString()} of ${allowance.daily_limit.toLocaleString()} included tokens left today.`}</p>}
          </div>
        </SettingSection>}
      </>}
    </SettingsPanel>
  )
}
