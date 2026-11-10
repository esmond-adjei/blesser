import type { CollectedField, FillInstruction, FillOutcome, FillSummary, PopupMessage, Reply, Status } from "../shared/types"
import { Api, SignedOut } from "./api"
import { acceptConnect, connectUrl, newState } from "./connect"
import { runFill, type Scripting } from "./fill"
import { Store, type Area } from "./store"

const store = new Store(chrome.storage.local as unknown as Area, chrome.storage.session as unknown as Area)
const api = new Api(store)

const scripting: Scripting = {
  async collect(tabId) {
    await chrome.scripting.executeScript({ target: { tabId, allFrames: true }, files: ["content.js"] })
    const runs = await chrome.scripting.executeScript({
      target: { tabId, allFrames: true },
      func: () => window.__blesser?.collect() ?? [],
    })
    return runs.map((r) => ({ frameId: r.frameId, result: (r.result ?? []) as CollectedField[] }))
  },
  async fill(tabId, frameId, instructions) {
    const [run] = await chrome.scripting.executeScript({
      target: { tabId, frameIds: [frameId] },
      func: (list: FillInstruction[]) => window.__blesser?.fill(list) ?? [],
      args: [instructions],
    })
    return (run?.result ?? []) as FillOutcome[]
  },
}

async function status(): Promise<Status> {
  const [settings, prefs, auth] = await Promise.all([store.settings(), store.prefs(), store.auth()])
  if (!auth) return { settings, prefs, connected: false, me: null, error: null }
  try {
    return { settings, prefs, connected: true, me: await api.me(), error: null }
  } catch (err) {
    if (err instanceof SignedOut) return { settings, prefs, connected: false, me: null, error: null }
    return { settings, prefs, connected: true, me: null, error: err instanceof Error ? err.message : "Blesser didn't answer." }
  }
}

async function handle(message: PopupMessage): Promise<unknown> {
  switch (message.type) {
    case "status":
      return status()
    case "connect": {
      const state = newState()
      await store.beginConnect(state)
      const { appUrl } = await store.settings()
      await chrome.tabs.create({ url: connectUrl(appUrl, chrome.runtime.id, state) })
      return null
    }
    case "disconnect":
      await api.logout()
      return null
    case "prefs":
      await store.savePrefs(message.prefs)
      return null
    case "settings":
      return store.saveSettings(message.settings)
    case "lastResult":
      return (await store.result(message.tabId)) ?? null
    case "fill": {
      const tab = await chrome.tabs.get(message.tabId)
      const summary = await runFill(api, scripting, { id: message.tabId, url: tab.url ?? "", title: tab.title ?? "" }, await store.prefs())
      await store.saveResult(summary)
      return summary
    }
    case "focus": {
      const at = message.key.indexOf(":")
      const [run] = await chrome.scripting.executeScript({
        target: { tabId: message.tabId, frameIds: [Number(message.key.slice(0, at))] },
        func: (key: string) => window.__blesser?.focus(key) ?? false,
        args: [message.key.slice(at + 1)],
      })
      return run?.result ?? false
    }
    case "markApplied": {
      const summary = await store.result(message.tabId)
      if (!summary?.matchedOpportunityId) throw new Error("This page isn't linked to an application you track.")
      const match = (await api.applications()).find((a) => a.opportunity_id === summary.matchedOpportunityId)
      if (!match) throw new Error("This page isn't linked to an application you track.")
      await api.markSubmitted(match.id)
      const next: FillSummary = { ...summary, applied: true }
      await store.saveResult(next)
      return next
    }
  }
}

chrome.runtime.onMessage.addListener((message: PopupMessage, sender, respond: (reply: Reply<unknown>) => void) => {
  // Only the extension's own pages; content scripts share the id but run on web origins.
  if (sender.id !== chrome.runtime.id || !sender.url?.startsWith(chrome.runtime.getURL(""))) return false
  handle(message).then(
    (data) => respond({ ok: true, data }),
    (err: unknown) => respond({ ok: false, error: err instanceof Error ? err.message : "Something went wrong." }),
  )
  return true
})

chrome.runtime.onMessageExternal.addListener((message: unknown, sender, respond: (reply: { ok: boolean; error?: string }) => void) => {
  acceptConnect(store, message, sender.url ?? sender.origin).then(respond, () => respond({ ok: false, error: "failed" }))
  return true
})
