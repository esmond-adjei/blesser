import { Link } from "react-router-dom"
import { useProviderCatalog, useProviderConfigs, usableConfigs, usableRunModel, useDefaultModel } from "../../lib/providers"
import { ModelDropup } from "../ui/ModelDropup"

/* Stores "system" (Auto) or an account model; "default" resolves to the account's default unless "Use my model by default" is on. */

const toShown = (value: string) => (value === "system" ? "auto" : value)
const fromShown = (sel: string) => (sel === "auto" ? "system" : sel)

/** Composer control: the chat's model picker. Unpicked or removed models read as the account default. */
export function RunModelDropup({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  const fallback = useDefaultModel()
  const { configs, isLoading, isError } = useProviderConfigs()
  const shown = toShown(usableRunModel(value, configs, !isLoading && !isError, fallback))
  return (
    <ModelDropup
      value={shown}
      onChange={(sel) => onChange(fromShown(sel))}
      placement="down"
    />
  )
}

/** Edit dialog control: a select, since a menu would be clipped by the dialog's scrolling body. */
export function RunModelSelect({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  const fallback = useDefaultModel()
  const { configs } = useProviderConfigs()
  const { system } = useProviderCatalog()
  const shown = toShown(value === "default" ? fallback : value)
  const options = [
    { value: "auto", label: "Auto", detail: system?.model ? `System model, ${system.provider}, ${system.model}` : "No model configured" },
    ...usableConfigs(configs).map((c) => ({ value: c.provider, label: c.provider, detail: c.model })),
  ]
  if (!options.some((o) => o.value === shown)) {
    // Picked earlier, then removed or switched off: show it rather than hide it.
    options.push({ value: shown, label: shown, detail: "Removed or switched off in settings: pick another" })
  }
  const current = options.find((o) => o.value === shown) ?? options[0]
  return (
    <div className="max-w-md space-y-1.5">
      <div className="flex items-center gap-3">
        <select
          aria-label="Model"
          value={current.value}
          onChange={(e) => onChange(fromShown(e.target.value))}
          className="h-9 min-w-0 flex-1 cursor-pointer rounded-md border border-input bg-background px-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          {options.map((o) => (
            <option key={o.value} value={o.value}>{o.label}</option>
          ))}
        </select>
        <Link to="?settings=models" className="shrink-0 text-xs text-primary hover:underline">Manage Models</Link>
      </div>
      <p className="truncate type-caption">{current.detail}</p>
    </div>
  )
}
