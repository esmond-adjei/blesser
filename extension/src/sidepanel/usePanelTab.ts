import * as React from "react"
import type { Review } from "../shared/types"
import { send } from "../shared/ui"

const reviewKey = (tabId: number) => `review:${tabId}`

function forcedTab(): number | null {
  if (!__TEST_BUILD__) return null
  return Number(new URLSearchParams(location.search).get("tab")) || null
}

/** The tab the panel works on (the active tab of its window) and that tab's stored review, kept live. */
export function usePanelTab() {
  const [tabId, setTabId] = React.useState<number | null>(forcedTab)
  const [page, setPage] = React.useState<{ tabId: number; title: string } | null>(null)
  const [stored, setStored] = React.useState<{ tabId: number; review: Review | null } | null>(null)

  React.useEffect(() => {
    if (forcedTab()) return
    let windowId: number | null = null
    void chrome.tabs.query({ active: true, currentWindow: true }).then(([tab]) => {
      windowId = tab?.windowId ?? null
      setTabId(tab?.id ?? null)
    })
    const onActivated = (info: chrome.tabs.OnActivatedInfo) => {
      if (windowId === null || info.windowId === windowId) setTabId(info.tabId)
    }
    chrome.tabs.onActivated.addListener(onActivated)
    return () => chrome.tabs.onActivated.removeListener(onActivated)
  }, [])

  React.useEffect(() => {
    if (tabId === null) return
    let live = true
    void chrome.tabs.get(tabId).then((tab) => {
      if (live) setPage((current) => current?.tabId === tabId ? current : { tabId, title: tab.title ?? "" })
    }, () => {})
    const onUpdated = (id: number, changes: chrome.tabs.OnUpdatedInfo, tab: chrome.tabs.Tab) => {
      if (id === tabId && (changes.status || changes.title !== undefined)) {
        setPage({ tabId, title: tab.title ?? "" })
      }
    }
    chrome.tabs.onUpdated.addListener(onUpdated)
    return () => {
      live = false
      chrome.tabs.onUpdated.removeListener(onUpdated)
      setPage((current) => current?.tabId === tabId ? null : current)
    }
  }, [tabId])

  React.useEffect(() => {
    if (tabId === null) return
    let live = true
    void send<Review | null>({ type: "review", tabId }).then((review) => live && setStored({ tabId, review }), () => {})
    const onChanged = (changes: Record<string, chrome.storage.StorageChange>, area: string) => {
      const change = changes[reviewKey(tabId)]
      if (area === "session" && change) setStored({ tabId, review: (change.newValue as Review | undefined) ?? null })
    }
    chrome.storage.onChanged.addListener(onChanged)
    return () => {
      live = false
      chrome.storage.onChanged.removeListener(onChanged)
    }
  }, [tabId])

  return { tabId, pageTitle: page?.tabId === tabId ? page.title : "", review: stored && stored.tabId === tabId ? stored.review : null }
}
