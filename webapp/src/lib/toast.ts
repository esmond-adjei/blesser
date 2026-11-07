import { toast } from "sonner"
import { apiMessage } from "./api"

/** Uniform toast alerts; backend detail strings read the same everywhere. */
export function toastError(err: unknown, prefix?: string) {
  const message = typeof err === "string" ? err : apiMessage(err)
  toast.error(prefix ? `${prefix}: ${message}` : message)
}

export function toastSuccess(message: string) {
  toast.success(message)
}

export function toastInfo(message: string) {
  toast.info(message)
}
