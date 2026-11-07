import { friendlyToolText } from "./toolActivity"
import { toast } from "sonner"
import { ApiError, apiMessage } from "./api"

/** Uniform toast alerts. Errors go through apiMessage so backend detail strings
 * (including structured 409s) read the same everywhere; plain strings pass through. */
export function toastError(err: unknown, prefix?: string) {
  // Plan gates (402) already opened the upgrade prompt; don't double up.
  if (err instanceof ApiError && err.status === 402) return
  const message = typeof err === "string" ? err : apiMessage(err)
  toast.error(friendlyToolText(prefix ? `${prefix}: ${message}` : message))
}

export function toastSuccess(message: string) {
  toast.success(friendlyToolText(message))
}

export function toastInfo(message: string) {
  toast.info(friendlyToolText(message))
}
