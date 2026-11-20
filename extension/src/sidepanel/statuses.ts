import type { ApplicationStatus, PageDetails } from "../shared/types"

/** The member app's labels, so a status reads the same in both. */
export const STATUSES: { value: ApplicationStatus; label: string }[] = [
  { value: "saved", label: "Saved" },
  { value: "preparing", label: "Preparing" },
  { value: "submitted", label: "Submitted" },
  { value: "interview", label: "Interview" },
  { value: "accepted", label: "Accepted" },
  { value: "rejected", label: "Not this time" },
]

export const statusLabel = (status: ApplicationStatus) => STATUSES.find((s) => s.value === status)?.label ?? "Tracked"

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

/** "2026-11-30" as "30 Nov 2026", the order the app shows dates in. */
export function deadlineText(iso: string): string {
  const [y, m, d] = iso.split("-").map(Number)
  return y && m && d ? `${d} ${MONTHS[m - 1]} ${y}` : ""
}

/** Enough to save without asking: a title and either a dated or a rolling deadline. */
export const confident = (details: PageDetails) => !!details.title && !!(details.deadline?.date || details.deadline?.rolling)
