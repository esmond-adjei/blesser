import * as React from "react"
import { Link } from "react-router-dom"
import * as api from "../../lib/api"
import { toastError } from "../../lib/toast"
import { Button } from "../ui/button"

export const OAUTH_STATE_KEY = "graduator.oauth.state"

/** Google "G" mark (brand guidelines: always the four-colour glyph). */
function GoogleMark() {
  return (
    <svg viewBox="0 0 48 48" aria-hidden className="size-4">
      <path fill="#FFC107" d="M43.6 20.5H42V20H24v8h11.3C33.7 32.7 29.2 36 24 36c-6.6 0-12-5.4-12-12s5.4-12 12-12c3.1 0 5.8 1.2 7.9 3.1l5.7-5.7C34 6.1 29.3 4 24 4 12.9 4 4 12.9 4 24s8.9 20 20 20 20-8.9 20-20c0-1.3-.1-2.4-.4-3.5z" />
      <path fill="#FF3D00" d="M6.3 14.7l6.6 4.8C14.7 15.1 19 12 24 12c3.1 0 5.8 1.2 7.9 3.1l5.7-5.7C34 6.1 29.3 4 24 4 16.3 4 9.7 8.3 6.3 14.7z" />
      <path fill="#4CAF50" d="M24 44c5.2 0 9.9-2 13.4-5.2l-6.2-5.2C29.2 35.1 26.7 36 24 36c-5.2 0-9.6-3.3-11.3-8l-6.5 5C9.5 39.6 16.2 44 24 44z" />
      <path fill="#1976D2" d="M43.6 20.5H42V20H24v8h11.3c-.8 2.2-2.2 4.2-4.1 5.6l6.2 5.2C37 39.2 44 34 44 24c0-1.3-.1-2.4-.4-3.5z" />
    </svg>
  )
}

const MARKS: Record<string, React.ReactNode> = { google: <GoogleMark /> }

/** Only server-configured providers render; with none, the divider is omitted too. */
export function OAuthButtons({ next }: { next: string }) {
  const [providers, setProviders] = React.useState<api.OAuthProvider[]>([])
  const [busy, setBusy] = React.useState<string | null>(null)

  React.useEffect(() => {
    let cancelled = false
    api.oauthProviders().then((p) => !cancelled && setProviders(p)).catch(() => {})
    return () => {
      cancelled = true
    }
  }, [])

  async function go(id: string) {
    setBusy(id)
    try {
      const { authorize_url, state } = await api.oauthStart(id, next)
      // Echo check on return: the callback must carry this exact state.
      sessionStorage.setItem(OAUTH_STATE_KEY, state)
      window.location.assign(authorize_url)
    } catch (err) {
      toastError(err)
      setBusy(null)
    }
  }

  if (providers.length === 0) return null
  return (
    <div className="space-y-3">
      {providers.map((p) => (
        <Button key={p.id} type="button" variant="outline" className="w-full" disabled={busy !== null} onClick={() => void go(p.id)}>
          {MARKS[p.id]} {busy === p.id ? "Redirecting…" : `Continue with ${p.label}`}
        </Button>
      ))}
      <p className="text-center type-caption">
        By continuing you agree to the{" "}
        <Link to="/terms" className="text-primary hover:underline">Terms</Link> and the{" "}
        <Link to="/privacy" className="text-primary hover:underline">Privacy notice</Link>.
      </p>
      <div className="flex items-center gap-3 type-caption" aria-hidden>
        <span className="h-px flex-1 bg-border" /> or <span className="h-px flex-1 bg-border" />
      </div>
    </div>
  )
}
