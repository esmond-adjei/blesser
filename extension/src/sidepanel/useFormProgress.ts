import * as React from "react"
import type { FormProgress } from "../shared/types"
import { send } from "../shared/ui"

const progressKey = (tabId: number) => `progress:${tabId}`

/** Live progress for the panel's tab: starts the count when the tab or its fill changes, then follows storage. */
export function useFormProgress(tabId: number | null, refresh: string | null) {
  const [stored, setStored] = React.useState<{ tabId: number; progress: FormProgress | null } | null>(null)

  React.useEffect(() => {
    if (tabId === null) return
    let live = true
    // Pages Blesser can't reach yet simply show no progress; filling grants access and starts the count.
    const start = () => void send<FormProgress>({ type: "progress", tabId }).then((progress) => live && setStored({ tabId, progress }), () => {})
    start()
    const onUpdated = (id: number, changes: chrome.tabs.OnUpdatedInfo) => {
      if (id === tabId && changes.status === "complete") start()
    }
    const onChanged = (changes: Record<string, chrome.storage.StorageChange>, area: string) => {
      const change = changes[progressKey(tabId)]
      if (area === "session" && change) setStored({ tabId, progress: (change.newValue as FormProgress | undefined) ?? null })
    }
    chrome.tabs.onUpdated.addListener(onUpdated)
    chrome.storage.onChanged.addListener(onChanged)
    return () => {
      live = false
      chrome.tabs.onUpdated.removeListener(onUpdated)
      chrome.storage.onChanged.removeListener(onChanged)
    }
  }, [tabId, refresh])

  return stored && stored.tabId === tabId ? stored.progress : null
}
