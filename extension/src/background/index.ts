import type { CollectedField, FillInstruction, FillOutcome, PageMessage, PanelMessage, Reply, Status, WriteResult } from "../shared/types"
import { Actions } from "./actions"
import { Api, SignedOut } from "./api"
import { acceptConnect, connectUrl, newState } from "./connect"
import { runFill, type Scripting, NO_ACCESS } from "./fill"
import { FILL_REQUEST } from "../shared/ui"
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
  async write(tabId, frameId, key, value) {
    const [run] = await chrome.scripting.executeScript({
      target: { tabId, frameIds: [frameId] },
      func: (k: string, v: string | string[] | null) => window.__blesser?.write(k, v) ?? null,
      args: [key, value],
    })
    if (!run?.result) throw new Error("The page changed. Fill this step again.")
    return run.result as WriteResult
  },
}
const actions = new Actions(api, store, scripting)

const NO_ACCESS_ERROR = /cannot access|cannot be scripted|must request permission|no tab with id|frame with id/i

async function tabInfo(tabId: number) {
  const tab = await chrome.tabs.get(tabId)
  return { id: tabId, url: tab.url ?? "", title: tab.title ?? "" }
}

/** Chrome's own errors when activeTab doesn't cover the tab, in words a member can act on. */
function explain(err: unknown): never {
  const text = err instanceof Error ? err.message : String(err)
  if (NO_ACCESS_ERROR.test(text)) throw new Error(NO_ACCESS)
  throw err instanceof Error ? err : new Error(text)
}

void chrome.sidePanel?.setPanelBehavior({ openPanelOnActionClick: true }).catch(() => {})

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

async function handle(message: PanelMessage): Promise<unknown> {
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
    case "review":
      return (await store.review(message.tabId)) ?? null
    case "fill": {
      const review = await runFill(api, scripting, await tabInfo(message.tabId), await store.prefs()).catch(explain)
      await store.saveReview(review)
      return review
    }
    case "focus": {
      const at = message.key.indexOf(":")
      const [run] = await chrome.scripting.executeScript({
        target: { tabId: message.tabId, frameIds: [Number(message.key.slice(0, at))] },
        func: (key: string) => window.__blesser?.focus(key) ?? false,
        args: [message.key.slice(at + 1)],
      }).catch(explain)
      if (!run?.result) throw new Error("That field isn't on the page any more.")
      return true
    }
    case "markApplied":
      return actions.markApplied(message.tabId)
    case "edit":
      return actions.edit(message.tabId, message.key, message.value)
    case "clear":
      return actions.clear(message.tabId, message.key)
    case "wrongField":
      return actions.wrongField(message.tabId, message.key)
    case "remember":
      return actions.remember(message.tabId, message.key)
    case "dismissEdit":
      return actions.dismissEdit(message.tabId, message.key)
    case "reportPreview":
      return actions.reportPreview(await tabInfo(message.tabId)).catch(explain)
    case "report":
      return actions.report(message.report)
  }
}

const isPageMessage = (message: unknown): message is PageMessage =>
  !!message && typeof message === "object" && ["blesser.edited", "blesser.step"].includes((message as { type?: string }).type ?? "")

chrome.runtime.onMessage.addListener((message: PanelMessage, sender, respond: (reply: Reply<unknown>) => void) => {
  if (sender.id !== chrome.runtime.id) return false
  // Content scripts share the id but run on web origins: they may only report page events, never drive actions.
  if (!sender.url?.startsWith(chrome.runtime.getURL(""))) {
    if (sender.tab?.id !== undefined && isPageMessage(message)) void actions.fromPage(sender.tab.id, sender.frameId ?? 0, message).catch(() => {})
    return false
  }
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

chrome.tabs.onUpdated.addListener((tabId, info) => {
  if (info.status === "loading") void actions.navigated(tabId).catch(() => {})
})

chrome.tabs.onRemoved.addListener((tabId) => void store.dropReview(tabId))

// Shortcut and context menu grant activeTab on the page, which the side panel's own button can't.
function fillFromGesture(tabId: number | undefined) {
  if (tabId === undefined) return
  void chrome.sidePanel.open({ tabId }).catch(() => {})
  void chrome.storage.session.set({ [FILL_REQUEST]: { tabId, at: Date.now() } })
}

chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.create({ id: "blesser-fill", title: "Fill with Blesser", contexts: ["page", "editable", "frame"] }, () => void chrome.runtime.lastError)
})
chrome.contextMenus.onClicked.addListener((info, tab) => {
  if (info.menuItemId === "blesser-fill") fillFromGesture(tab?.id)
})
chrome.commands.onCommand.addListener((command, tab) => {
  if (command === "fill-page") fillFromGesture(tab?.id)
})
