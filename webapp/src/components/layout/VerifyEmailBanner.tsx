import * as React from "react"
import { MailWarning, X } from "lucide-react"
import * as api from "../../lib/api"
import { useAuth } from "../../lib/auth"
import { toastError, toastSuccess } from "../../lib/toast"

const DISMISS_KEY = "graduator.verifyBanner.dismissed"

/** Sensitive actions (data export, account linking) stay locked until confirmed; dismissal lasts for the session. */
export function VerifyEmailBanner() {
  const { user } = useAuth()
  const [dismissed, setDismissed] = React.useState(() => {
    try {
      return sessionStorage.getItem(DISMISS_KEY) === user?.id
    } catch {
      return false
    }
  })
  const [busy, setBusy] = React.useState(false)
  if (!user || user.email_verified || dismissed) return null

  async function resend() {
    setBusy(true)
    try {
      const r = await api.resendVerification()
      toastSuccess(r.status)
    } catch (err) {
      toastError(err)
    } finally {
      setBusy(false)
    }
  }

  function dismiss() {
    setDismissed(true)
    try {
      sessionStorage.setItem(DISMISS_KEY, user?.id ?? "")
    } catch {
      /* private mode */
    }
  }

  return (
    <div role="status" className="flex items-center gap-3 border-b border-separator bg-caution-soft px-4 py-2 text-sm text-label">
      <MailWarning className="size-4 shrink-0 text-caution" aria-hidden />
      <p className="min-w-0 flex-1">
        Confirm <span className="font-medium">{user.email}</span> to unlock data export. Check your inbox for our link.
      </p>
      <button
        type="button"
        onClick={() => void resend()}
        disabled={busy}
        className="shrink-0 cursor-pointer font-medium underline-offset-2 hover:underline disabled:opacity-50"
      >
        {busy ? "Sending…" : "Resend link"}
      </button>
      <button
        type="button"
        onClick={dismiss}
        aria-label="Dismiss until next session"
        className="shrink-0 cursor-pointer rounded p-1 opacity-70 hover:opacity-100"
      >
        <X className="size-3.5" />
      </button>
    </div>
  )
}
