/** Provider config backed by the registry API (seeded from the supported
 * list, governed from settings). Keys are write-only; reads only report whether one is set. */
import * as React from "react"
import { useQuery, useQueryClient } from "@tanstack/react-query"
import * as api from "./api"
import { useAuth } from "./auth"
import { loadModelSel } from "./gradis"
import type { ProviderConfig } from "./types"

const KEY = ["provider-configs"]
const CATALOG_KEY = ["provider-catalog"]

export function useProviderConfigs() {
  const qc = useQueryClient()
  const query = useQuery({ queryKey: KEY, queryFn: api.listProviders })
  const refresh = React.useCallback(
    () => qc.invalidateQueries({ queryKey: KEY }),
    [qc],
  )
  const update = React.useCallback(
    async (
      provider: string,
      body: Parameters<typeof api.updateProvider>[1],
    ) => {
      await api.updateProvider(provider, body)
      // The chat composer's usage bar reads the saved context window.
      void qc.invalidateQueries({ queryKey: ["chat-model-info"] })
      await refresh()
    },
    [qc, refresh],
  )
  return { configs: query.data ?? [], isLoading: query.isLoading, isError: query.isError, update, refresh }
}

export function useProviderCatalog() {
  const query = useQuery({ queryKey: CATALOG_KEY, queryFn: api.getProviderCatalog })
  return {
    catalog: query.data ?? null,
    providers: query.data?.providers ?? [],
    system: query.data?.system ?? null,
    isLoading: query.isLoading,
    isError: query.isError,
  }
}

export type { ProviderConfig }

/** Own models a run or chat can use: configured with a model and enabled. */
export function usableConfigs(configs: ProviderConfig[]): ProviderConfig[] {
  return configs.filter((c) => c.model && c.enabled !== false)
}

/** The model an unset choice means: "system" (Auto), or the default
 * own model when "Use my model by default" is on and that model is configured.
 * Configuring a model alone never changes this. */
export function useDefaultModel(): string {
  const { user } = useAuth()
  const { configs } = useProviderConfigs()
  if (!user?.prefer_own_model) return "system"
  return usableConfigs(configs).find((c) => c.is_active)?.provider ?? "system"
}

/** The model the chat picker has chosen, as a request's `model`:
 * "system" (Auto) or an own model still configured and on. Lets other
 * model calls (the CV editor's suggestions) use the same pick as Gradis. */
export function useChatModel(): { provider: string } {
  const fallback = useDefaultModel()
  const { configs, isLoading, isError } = useProviderConfigs()
  const picked = loadModelSel()
  const requested = picked == null ? "default" : picked === "auto" ? "system" : picked
  return { provider: usableRunModel(requested, configs, !isLoading && !isError, fallback) }
}

/** A run's model choice as sent: "system" or an own model still configured
 * and on. "default" (not picked) is the account default; a removed or off
 * model falls back to it, matching what the picker shows. */
export function usableRunModel(
  model: string,
  configs: ProviderConfig[],
  loaded: boolean,
  fallback: string,
): string {
  if (model === "default") return fallback
  if (!loaded || model === "system") return model
  return usableConfigs(configs).some((c) => c.provider === model) ? model : fallback
}
