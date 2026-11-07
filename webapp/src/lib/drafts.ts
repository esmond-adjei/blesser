import { ApiError, apiMessage } from "./api"

export function hasDraft(c: {
  draft_id?: string | null
  draft_subject?: string | null
}): boolean {
  return c.draft_id != null || c.draft_subject != null
}

/** A draft as plain text to paste into an email app. */
export function draftEmailText(d: { subject: string; body: string }): string {
  return `Subject: ${d.subject}\n\n${d.body}`
}

/** True while the candidate's draft_email task is still working. */
export function isDraftInProgress(status: string | null | undefined): boolean {
  return status === "pending" || status === "running"
}

/** Friendly message for a draft request failure (409 = already in flight). */
export function draftRequestMessage(err: unknown): string {
  if (err instanceof ApiError && err.status === 409)
    return "Draft already in progress. Track it under Tasks."
  return apiMessage(err)
}
