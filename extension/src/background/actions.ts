import {
  applyClear,
  applyEdit,
  applyWrongField,
  dismissPageEdit,
  feedbackFor,
  markMoved,
  notePageEdit,
  sameValue,
} from "../shared/review"
import type { Corrected, FieldDescriptor, PageMessage, ProblemReport, Review, ReviewRow } from "../shared/types"
import type { Api } from "./api"
import { cleanDescriptor, collectPage, split, type Scripting, type TabInfo } from "./fill"
import { cleanProgress } from "./progress"
import type { Store } from "./store"

type Value = string | string[] | null

export interface ActionResult {
  review: Review
  /** Set when the page changed but Blesser couldn't record the feedback. */
  warning: string | null
}

const MAX_NOTE = 2000
const message = (err: unknown) => (err instanceof Error ? err.message : "Blesser didn't answer.")

/** Review actions from the panel and events from the page; every change goes through the stored review. */
export class Actions {
  private api: Api
  private store: Store
  private scripting: Scripting

  constructor(api: Api, store: Store, scripting: Scripting) {
    this.api = api
    this.store = store
    this.scripting = scripting
  }

  private async row(tabId: number, key: string): Promise<{ review: Review; row: ReviewRow }> {
    const review = await this.store.review(tabId)
    const row = review?.rows.find((r) => r.key === key)
    if (!review || !row) throw new Error("That field isn't in this review any more. Fill the page again.")
    return { review, row }
  }

  private async onPage(tabId: number, key: string, value: Value): Promise<Value> {
    const { frameId, local } = split(key)
    const result = await this.scripting.write(tabId, frameId, local, value).catch(() => null)
    if (!result) throw new Error("The page changed. Fill this step again.")
    if (!result.ok) throw new Error(result.reason)
    return result.value
  }

  private async send(review: Review, row: ReviewRow, corrected: Corrected): Promise<string | null> {
    try {
      await this.api.feedback(feedbackFor(review, row, corrected))
      return null
    } catch (err) {
      return `Changed on the page, but Blesser couldn't remember it: ${message(err)}`
    }
  }

  private async save(tabId: number, change: (review: Review) => Review): Promise<Review> {
    const next = await this.store.updateReview(tabId, change)
    if (!next) throw new Error("This review is gone. Fill the page again.")
    return next
  }

  async edit(tabId: number, key: string, value: Value): Promise<ActionResult> {
    const { review, row } = await this.row(tabId, key)
    const written = await this.onPage(tabId, key, value)
    const kept = written ?? value
    const next = await this.save(tabId, (r) => applyEdit(r, key, kept))
    const warning = sameValue(row.value, kept) ? null : await this.send(review, row, { value: kept })
    return { review: next, warning }
  }

  async clear(tabId: number, key: string): Promise<ActionResult> {
    await this.row(tabId, key)
    await this.onPage(tabId, key, null)
    return { review: await this.save(tabId, (r) => applyClear(r, key)), warning: null }
  }

  async wrongField(tabId: number, key: string): Promise<ActionResult> {
    const { review, row } = await this.row(tabId, key)
    await this.onPage(tabId, key, null).catch(() => null)
    const next = await this.save(tabId, (r) => applyWrongField(r, key))
    return { review: next, warning: await this.send(review, row, { wrong_field: true }) }
  }

  async remember(tabId: number, key: string): Promise<ActionResult> {
    const { review, row } = await this.row(tabId, key)
    if (!row.pageEdit) return { review, warning: null }
    const value = row.pageEdit.value
    const warning = await this.send(review, row, { value })
    if (warning) return { review, warning: warning.replace("Changed on the page, but ", "") }
    return { review: await this.save(tabId, (r) => applyEdit(r, key, value)), warning: null }
  }

  async dismissEdit(tabId: number, key: string): Promise<Review> {
    return this.save(tabId, (r) => dismissPageEdit(r, key))
  }

  /** A message from the content script in one frame of the tab. */
  async fromPage(tabId: number, frameId: number, msg: PageMessage) {
    if (msg.type === "blesser.edited") await this.store.updateReview(tabId, (r) => notePageEdit(r, `${frameId}:${msg.key}`, msg.value))
    else if (msg.type === "blesser.step" && msg.added > 0) await this.store.updateReview(tabId, (r) => markMoved(r, "step"))
    else if (msg.type === "blesser.progress") await this.store.updateProgress(tabId, frameId, cleanProgress(msg.fields))
  }

  async navigated(tabId: number) {
    await this.store.updateReview(tabId, (r) => markMoved(r, "navigated"))
  }

  async reportPreview(tab: TabInfo): Promise<ProblemReport> {
    const { fields } = await collectPage(this.scripting, tab)
    const url = new URL(tab.url)
    return { page: { url: tab.url, host: url.hostname, title: tab.title.slice(0, 500) }, fields, note: "" }
  }

  async report(report: ProblemReport) {
    const fields: FieldDescriptor[] = report.fields.slice(0, 300).map(cleanDescriptor)
    if (!fields.length) throw new Error("There are no fields to report on this page.")
    const page = { url: report.page.url.slice(0, 2000), host: report.page.host.slice(0, 255), title: report.page.title.slice(0, 500) }
    await this.api.report({ page, fields, note: report.note.trim().slice(0, MAX_NOTE) })
  }

  async markApplied(tabId: number): Promise<Review> {
    const review = await this.store.review(tabId)
    if (!review?.matchedOpportunityId) throw new Error("This page isn't linked to an application you track.")
    const match = (await this.api.applications()).find((a) => a.opportunity_id === review.matchedOpportunityId)
    if (!match) throw new Error("This page isn't linked to an application you track.")
    await this.api.markSubmitted(match.id)
    return this.save(tabId, (r) => ({ ...r, applied: true }))
  }
}
