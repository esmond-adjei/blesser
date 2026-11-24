/** Match profile ("Your feed" in Settings) and saved searches. */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import * as api from "./api"
import { CATEGORY_LABELS, KIND_LABELS, isCategory, isKind } from "./opportunities"
import type { AlertFrequency, MatchLevel, SavedSearch, SearchFilters } from "./types"

export const LEVEL_LABELS: Record<MatchLevel, string> = {
  undergraduate: "Undergraduate",
  masters: "Masters",
  phd: "PhD",
  postdoc: "Postdoc or early-career researcher",
  founder: "Early-stage founder",
}
export const LEVELS = Object.keys(LEVEL_LABELS) as MatchLevel[]

export const ALERT_LABELS: Record<AlertFrequency, string> = {
  daily: "Daily",
  weekly: "Weekly",
  off: "Off",
}
export const ALERTS = Object.keys(ALERT_LABELS) as AlertFrequency[]

export function useMatchProfile() {
  return useQuery({ queryKey: ["match-profile"], queryFn: api.getMatchProfile, staleTime: 60_000 })
}

export function useSavedSearches() {
  return useQuery({ queryKey: ["saved-searches"], queryFn: api.listSavedSearches, staleTime: 60_000 })
}

export function useSavedSearchMutations() {
  const client = useQueryClient()
  const refresh = () => void client.invalidateQueries({ queryKey: ["saved-searches"] })
  return {
    create: useMutation({ mutationFn: api.createSavedSearch, onSuccess: refresh }),
    update: useMutation({
      mutationFn: ({ id, ...body }: { id: string; name?: string; alerts?: AlertFrequency }) => api.updateSavedSearch(id, body),
      onSuccess: refresh,
    }),
    remove: useMutation({ mutationFn: api.deleteSavedSearch, onSuccess: refresh }),
  }
}

/** URL query params for a saved search's filters, as the Opportunities page reads them. */
export function filtersToParams(filters: SearchFilters): URLSearchParams {
  const params = new URLSearchParams()
  if (filters.q) params.set("q", filters.q)
  if (filters.category) params.set("category", filters.category)
  if (filters.kind) params.set("kind", filters.kind)
  if (filters.country) params.set("country", filters.country)
  if (filters.closing_within != null) params.set("soon", "1")
  return params
}

/** "Words: climate, Grant, Researchers" for a saved search. */
export function describeFilters(filters: SearchFilters): string {
  const parts: string[] = []
  if (filters.q) parts.push(`"${filters.q}"`)
  if (filters.kind && isKind(filters.kind)) parts.push(KIND_LABELS[filters.kind])
  if (filters.category && isCategory(filters.category)) parts.push(CATEGORY_LABELS[filters.category])
  if (filters.country) parts.push(filters.country)
  if (filters.closing_within != null) parts.push(`closing within ${filters.closing_within} days`)
  return parts.length ? parts.join(", ") : "Everything open"
}

/** A short default name for the current filters. */
export function suggestName(filters: SearchFilters): string {
  const name = describeFilters(filters).replaceAll('"', "")
  return name.length > 60 ? `${name.slice(0, 57)}...` : name
}

export function sameFilters(a: SearchFilters, b: SearchFilters): boolean {
  return filtersToParams(a).toString() === filtersToParams(b).toString()
}

export type { SavedSearch }
