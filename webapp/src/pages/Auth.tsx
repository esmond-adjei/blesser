import { Checkbox } from "../components/ui/checkbox"
import * as React from "react"
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom"
import { useQueryClient } from "@tanstack/react-query"
import { useAuth } from "../lib/auth"
import * as api from "../lib/api"
import { apiMessage } from "../lib/api"
import { toastError, toastSuccess } from "../lib/toast"
import { authHref, trackAfterAuth, trackParam, trackedMessage, trackedTitle } from "../lib/track"
import { CheckCircle2, MailCheck } from "lucide-react"
import { Button, Field, Input, LOGO, Logo, Wordmark } from "@blesser/ui"
import { Alert, AlertDescription } from "../components/ui/feedback"
import { OAUTH_STATE_KEY, OAuthButtons } from "../components/auth/OAuthButtons"
import { PasswordInput } from "../components/auth/PasswordInput"

// Desktop only: phones never request the photo.
function AuthPhoto() {
  return (
    <picture>
      <source media="(min-width: 1024px)" srcSet="/auth/coding-together.webp" type="image/webp" />
      <img
        src="data:image/gif;base64,R0lGODlhAQABAAD/ACwAAAAAAQABAAACADs="
        alt=""
        width={1200}
        height={800}
        className="absolute inset-0 h-full w-full object-cover object-right"
      />
    </picture>
  )
}

function AuthShell({
  title,
  subtitle,
  children,
}: {
  title: string
  subtitle: React.ReactNode
  children: React.ReactNode
}) {
  return (
    <div className="min-h-dvh bg-canvas lg:grid lg:grid-cols-2 lg:gap-4 lg:p-4">
      <div aria-hidden="true" className="relative hidden overflow-hidden rounded-lg bg-surface-sunk lg:block">
        <AuthPhoto />
        <svg viewBox="0 0 32 32" className="absolute inset-[7.5%] size-[85%]" fill="none" strokeWidth={4} strokeLinejoin="round">
          <g transform={LOGO.fill}>
            <path d="M9 17.2a7 7 0 0 1 14 0" stroke="var(--sun)" strokeLinecap="round" vectorEffect="non-scaling-stroke" />
            <path d={LOGO.steps} stroke="#ffffff" vectorEffect="non-scaling-stroke" />
          </g>
        </svg>
      </div>
      <div className="mx-auto flex min-h-dvh w-full max-w-[448px] flex-col justify-center gap-6 px-4 py-8 lg:min-h-[calc(100dvh-2rem)]">
        <div className="flex w-full flex-col items-center gap-4 text-center">
          <Link to="/" aria-label="Blesser" className="inline-flex items-center gap-1 rounded-sm focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-focus">
            <Logo title="" className="size-9" />
            <Wordmark className="text-[30px]" />
          </Link>
          <h1 className="type-title-2 text-ink">{title}</h1>
        </div>
        <div className="space-y-4 rounded-lg border border-separator bg-surface p-6">
          {children}
        </div>
        <p className="text-center text-callout text-ink-secondary">{subtitle}</p>
      </div>
    </div>
  )
}

/** Where a signed-in visitor goes from the auth pages: ?track= tracks first and opens Applications, else ?next=. */
function useAfterAuth() {
  const { user, ready } = useAuth()
  const navigate = useNavigate()
  const client = useQueryClient()
  const [searchParams] = useSearchParams()
  const next = searchParams.get("next") || "/opportunities"
  const track = trackParam(searchParams)
  // Set while a submit owns the redirect, so the signed-in effect doesn't race it.
  const handling = React.useRef(false)

  const finish = React.useCallback(
    async (tracked?: { title: string | null }) => {
      if (!track) return navigate(next, { replace: true })
      if (tracked) {
        toastSuccess(trackedMessage(tracked.title))
      } else {
        try {
          toastSuccess(trackedMessage(await trackAfterAuth(track)))
        } catch (err) {
          toastError(err, "That opportunity didn't track")
        }
      }
      void client.invalidateQueries({ queryKey: ["applications"] })
      void client.invalidateQueries({ queryKey: ["opportunities", "tracked"] })
      navigate("/applications", { replace: true })
    },
    [track, next, navigate, client],
  )

  React.useEffect(() => {
    if (!ready || !user || handling.current) return
    handling.current = true
    void finish()
  }, [ready, user, finish])

  const claim = React.useCallback((owned: boolean) => {
    handling.current = owned
  }, [])

  return { next, track, claim, finish }
}

/** Email/password sign-in; lands on ?next= or the dossier. Errors show the backend message. */
export function Login() {
  const { ready, signIn } = useAuth()
  const [searchParams] = useSearchParams()
  const [email, setEmail] = React.useState("")
  const [password, setPassword] = React.useState("")
  const [busy, setBusy] = React.useState(false)
  const [err, setErr] = React.useState<string | null>(null)
  const { next, track, claim, finish } = useAfterAuth()
  const oauthError = searchParams.get("oauth_error")

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault()
    setBusy(true)
    setErr(null)
    claim(true)
    try {
      await signIn(email.trim(), password)
    } catch (e2) {
      claim(false)
      setErr(apiMessage(e2))
      setBusy(false)
      return
    }
    await finish()
  }

  if (!ready) return null
  return (
    <AuthShell
      title="Welcome back"
      subtitle={
        <>
          No account yet?{" "}
          <Link to={authHref("/register", { next, track })} className="font-semibold text-link hover:underline">
            Create one
          </Link>
        </>
      }
    >
      {oauthError && (
        <Alert variant="destructive">
          <AlertDescription>{oauthError}</AlertDescription>
        </Alert>
      )}
      <OAuthButtons next={track ? authHref("/login", { track }) : next} />
      <form onSubmit={onSubmit} className="space-y-3">
        <Field label="Email">
          <Input type="email" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
        </Field>
        <div className="flex justify-end">
          <Link
            to={`/forgot-password${email.trim() ? `?email=${encodeURIComponent(email.trim())}` : ""}`}
            className="-mb-2 text-footnote font-semibold text-link hover:underline"
          >
            Forgot password?
          </Link>
        </div>
        <Field label="Password">
          <PasswordInput
            autoComplete="current-password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </Field>
        {err && (
          <Alert variant="destructive">
            <AlertDescription>{err}</AlertDescription>
          </Alert>
        )}
        <Button type="submit" variant="primary" size="lg" className="w-full" disabled={busy}>
          {busy ? "Signing in…" : "Sign in"}
        </Button>
      </form>
    </AuthShell>
  )
}

/** Registration: one account per email, straight into a session. */
export function Register() {
  const { ready, signUp } = useAuth()
  const [email, setEmail] = React.useState("")
  const [password, setPassword] = React.useState("")
  const [agreed, setAgreed] = React.useState(false)
  const [busy, setBusy] = React.useState(false)
  const [err, setErr] = React.useState<string | null>(null)
  const { next, track, claim, finish } = useAfterAuth()

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault()
    setBusy(true)
    setErr(null)
    claim(true)
    try {
      await signUp(email.trim(), password, agreed, track)
    } catch (e2) {
      claim(false)
      setErr(apiMessage(e2))
      setBusy(false)
      return
    }
    // The register call already tracked it; the lookup only fetches the title for the toast.
    await finish(track ? { title: await trackedTitle(track) } : undefined)
  }

  if (!ready) return null
  return (
    <AuthShell
      title="Create your account"
      subtitle={
        <>
          Already have an account?{" "}
          <Link to={authHref("/login", { next, track })} className="font-semibold text-link hover:underline">
            Sign in
          </Link>
        </>
      }
    >
      <OAuthButtons next={track ? authHref("/login", { track }) : next} />
      <form onSubmit={onSubmit} className="space-y-3">
        <Field label="Email">
          <Input type="email" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
        </Field>
        <Field label="Password">
          <PasswordInput
            autoComplete="new-password"
            required
            minLength={8}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </Field>
        <label className="flex items-start gap-2 text-footnote text-ink-secondary">
          <Checkbox
            required
            className="mt-0.5"
            checked={agreed}
            onCheckedChange={(value) => setAgreed(value === true)}
          />
          <span>
            I agree to the{" "}
            <Link to="/terms" target="_blank" className="font-semibold text-link hover:underline">Terms</Link> and the{" "}
            <Link to="/privacy" target="_blank" className="font-semibold text-link hover:underline">Privacy notice</Link>.
          </span>
        </label>
        {err && (
          <Alert variant="destructive">
            <AlertDescription>{err}</AlertDescription>
          </Alert>
        )}
        <Button type="submit" variant="primary" size="lg" className="w-full" disabled={busy || !agreed}>
          {busy ? "Creating…" : "Create account"}
        </Button>
      </form>
    </AuthShell>
  )
}

/** Requests a reset link. The response never reveals whether the email has an account. */
export function ForgotPassword() {
  const [searchParams] = useSearchParams()
  const [email, setEmail] = React.useState(searchParams.get("email") ?? "")
  const [busy, setBusy] = React.useState(false)
  const [sent, setSent] = React.useState(false)
  const [err, setErr] = React.useState<string | null>(null)

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault()
    setBusy(true)
    setErr(null)
    try {
      await api.forgotPassword(email.trim())
      setSent(true)
    } catch (e2) {
      setErr(apiMessage(e2))
    } finally {
      setBusy(false)
    }
  }

  return (
    <AuthShell
      title="Reset your password"
      subtitle={<Link to="/login" className="font-semibold text-link hover:underline">Back to sign in</Link>}
    >
      {sent ? (
        <div className="space-y-2 text-center">
          <MailCheck className="mx-auto size-10 text-link" strokeWidth={1.75} aria-hidden />
          <p className="text-headline text-ink">Check your email</p>
          <p className="text-callout text-ink-secondary">
            If an account exists for <span className="font-medium text-ink">{email.trim()}</span>, a reset
            link is on its way. It works once and expires in 30 minutes.
          </p>
        </div>
      ) : (
        <form onSubmit={onSubmit} className="space-y-3">
          <p className="text-callout text-ink-secondary">
            Enter your account's email and we'll send you a link to choose a new password.
          </p>
          <Field label="Email">
            <Input type="email" autoComplete="email" required autoFocus value={email} onChange={(e) => setEmail(e.target.value)} />
          </Field>
          {err && (
            <Alert variant="destructive">
              <AlertDescription>{err}</AlertDescription>
            </Alert>
          )}
          <Button type="submit" variant="primary" size="lg" className="w-full" disabled={busy}>
            {busy ? "Sending…" : "Send reset link"}
          </Button>
        </form>
      )}
    </AuthShell>
  )
}

/** Choose a new password from an emailed link (?token=). */
export function ResetPassword() {
  const [searchParams] = useSearchParams()
  const token = searchParams.get("token") ?? ""
  const [password, setPassword] = React.useState("")
  const [confirm, setConfirm] = React.useState("")
  const [busy, setBusy] = React.useState(false)
  const [done, setDone] = React.useState(false)
  const [err, setErr] = React.useState<string | null>(null)
  const mismatch = confirm !== "" && confirm !== password

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (mismatch || password.length < 8) return
    setBusy(true)
    setErr(null)
    try {
      await api.resetPassword(token, password)
      setDone(true)
    } catch (e2) {
      setErr(apiMessage(e2))
    } finally {
      setBusy(false)
    }
  }

  return (
    <AuthShell
      title="Choose a new password"
      subtitle={<Link to="/login" className="font-semibold text-link hover:underline">Back to sign in</Link>}
    >
      {done ? (
        <div className="space-y-3 text-center">
          <CheckCircle2 className="mx-auto size-10 text-positive" aria-hidden />
          <p className="text-headline text-ink">Password updated</p>
          <p className="text-callout text-ink-secondary">For safety, every device was signed out.</p>
          <Link to="/login" className="inline-block text-callout font-semibold text-link hover:underline">Sign in</Link>
        </div>
      ) : !token ? (
        <Alert variant="destructive">
          <AlertDescription>
            This link is missing its token. <Link to="/forgot-password" className="underline">Request a new one</Link>.
          </AlertDescription>
        </Alert>
      ) : (
        <form onSubmit={onSubmit} className="space-y-3">
          <Field label="New password">
            <PasswordInput autoComplete="new-password" required minLength={8} autoFocus value={password} onChange={(e) => setPassword(e.target.value)} placeholder="At least 8 characters" />
          </Field>
          <Field label="Confirm new password">
            <PasswordInput autoComplete="new-password" required value={confirm} onChange={(e) => setConfirm(e.target.value)} />
          </Field>
          {mismatch && <p className="text-footnote font-medium text-critical">Passwords don't match.</p>}
          {err && (
            <Alert variant="destructive">
              <AlertDescription>
                {err} {err.includes("expired") && <Link to="/forgot-password" className="underline">Get a new link</Link>}
              </AlertDescription>
            </Alert>
          )}
          <Button type="submit" variant="primary" size="lg" className="w-full" disabled={busy || mismatch || password.length < 8}>
            {busy ? "Saving…" : "Set new password"}
          </Button>
        </form>
      )}
    </AuthShell>
  )
}

/** Confirm an email from its link (?token=). Works signed in or out. */
export function VerifyEmail() {
  const [searchParams] = useSearchParams()
  const token = searchParams.get("token") ?? ""
  const { user, updateUser } = useAuth()
  const [state, setState] = React.useState<"working" | "done" | "error">(token ? "working" : "error")
  const [err, setErr] = React.useState<string | null>(token ? null : "This link is missing its token.")
  const started = React.useRef(false)

  React.useEffect(() => {
    if (!token || started.current) return
    started.current = true
    api
      .verifyEmail(token)
      .then((fresh) => {
        if (user && user.id === fresh.id) updateUser(fresh)
        setState("done")
      })
      .catch((e2) => {
        setErr(apiMessage(e2))
        setState("error")
      })
  }, [token, user, updateUser])

  return (
    <AuthShell
      title="Confirm your email"
      subtitle={<Link to={user ? "/new" : "/login"} className="font-semibold text-link hover:underline">{user ? "Back to Blesser" : "Sign in"}</Link>}
    >
      {state === "working" ? (
        <p className="text-center text-callout text-ink-secondary">Confirming…</p>
      ) : state === "done" ? (
        <div className="space-y-2 text-center">
          <CheckCircle2 className="mx-auto size-10 text-positive" aria-hidden />
          <p className="text-headline text-ink">Email confirmed</p>
          <p className="text-callout text-ink-secondary">Thanks. Everything in your account is unlocked.</p>
        </div>
      ) : (
        <Alert variant="destructive">
          <AlertDescription>
            {err} {user ? "Resend it from the banner in the app." : "Sign in to request a new one."}
          </AlertDescription>
        </Alert>
      )}
    </AuthShell>
  )
}

/** A button, not an automatic request, so mail scanners that open the link can't unsubscribe anyone. */
export function UnsubscribeEmail() {
  const [searchParams] = useSearchParams()
  const token = searchParams.get("token") ?? ""
  const { user } = useAuth()
  const [state, setState] = React.useState<"idle" | "working" | "done" | "error">(token ? "idle" : "error")
  const [label, setLabel] = React.useState("")
  const [err, setErr] = React.useState<string | null>(token ? null : "This link is missing its token.")

  async function confirm() {
    setState("working")
    try {
      const result = await api.unsubscribeNotificationEmail(token)
      setLabel(result.label)
      setState("done")
    } catch (e2) {
      setErr(apiMessage(e2))
      setState("error")
    }
  }

  return (
    <AuthShell
      title="Email notifications"
      subtitle={<Link to={user ? "/new?settings=notifications" : "/login"} className="font-semibold text-link hover:underline">{user ? "Notification settings" : "Sign in"}</Link>}
    >
      {state === "done" ? (
        <div className="space-y-2 text-center">
          <CheckCircle2 className="mx-auto size-10 text-positive" aria-hidden />
          <p className="text-headline text-ink">Unsubscribed</p>
          <p className="text-callout text-ink-secondary">
            No more {label ? `"${label}"` : "of these"} emails. Turn them back on any time in Settings, Notifications.
          </p>
        </div>
      ) : state === "error" ? (
        <Alert variant="destructive">
          <AlertDescription>{err} You can change email settings in Settings, Notifications.</AlertDescription>
        </Alert>
      ) : (
        <div className="space-y-3 text-center">
          <p className="text-callout text-ink-secondary">Stop emails like the one you followed this link from?</p>
          <Button variant="primary" onClick={confirm} disabled={state === "working"}>
            {state === "working" ? "Unsubscribing…" : "Unsubscribe"}
          </Button>
        </div>
      )}
    </AuthShell>
  )
}

/** OAuth redirect target: verifies state, then signs in or asks for the existing account's password (link, never fork). */
export function OAuthCallback() {
  const { provider = "" } = useParams<{ provider: string }>()
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()
  const { adoptSession } = useAuth()
  const [link, setLink] = React.useState<{ data: api.OAuthLinkRequired; next: string } | null>(null)
  const [password, setPassword] = React.useState("")
  const [busy, setBusy] = React.useState(false)
  const [err, setErr] = React.useState<string | null>(null)
  const started = React.useRef(false)

  React.useEffect(() => {
    if (started.current) return
    started.current = true
    const fail = (message: string) =>
      navigate(`/login?oauth_error=${encodeURIComponent(message)}`, { replace: true })
    const error = searchParams.get("error")
    if (error) {
      fail(error === "access_denied" ? "Sign-in was cancelled." : "Sign-in didn't complete. Try again.")
      return
    }
    const code = searchParams.get("code")
    const state = searchParams.get("state")
    let expected: string | null = null
    try {
      expected = sessionStorage.getItem(OAUTH_STATE_KEY)
      sessionStorage.removeItem(OAUTH_STATE_KEY)
    } catch {
      /* private mode */
    }
    if (!code || !state || state !== expected) {
      fail("This sign-in attempt expired or didn't start here. Try again.")
      return
    }
    api
      .oauthCallback(provider, code, state)
      .then((r) => {
        if ("link_required" in r) setLink({ data: r.link_required, next: r.next })
        else {
          adoptSession(r)
          navigate(r.next || "/", { replace: true })
        }
      })
      .catch((e2) => fail(apiMessage(e2)))
  }, [provider, searchParams, navigate, adoptSession])

  async function onLink(e: React.FormEvent) {
    e.preventDefault()
    if (!link) return
    setBusy(true)
    setErr(null)
    try {
      adoptSession(await api.oauthLink(link.data.link_token, password))
      navigate(link.next || "/", { replace: true })
    } catch (e2) {
      setErr(apiMessage(e2))
    } finally {
      setBusy(false)
    }
  }

  if (!link) {
    return (
      <AuthShell title="Signing you in" subtitle={<Link to="/login" className="font-semibold text-link hover:underline">Back to sign in</Link>}>
        <p className="text-center text-callout text-ink-secondary">Finishing sign-in…</p>
      </AuthShell>
    )
  }
  return (
    <AuthShell
      title={`Link ${link.data.provider}`}
      subtitle={<Link to="/login" className="font-semibold text-link hover:underline">Cancel</Link>}
    >
      <form onSubmit={onLink} className="space-y-3">
        <p className="text-callout text-ink-secondary">
          <span className="font-medium text-ink">{link.data.email}</span> already has a Blesser account.
          Enter its password once to link {link.data.provider}; after that you can use either to sign in.
        </p>
        <Field label="Password">
          <PasswordInput autoComplete="current-password" required autoFocus value={password} onChange={(e) => setPassword(e.target.value)} />
        </Field>
        {err && (
          <Alert variant="destructive">
            <AlertDescription>{err}</AlertDescription>
          </Alert>
        )}
        <Button type="submit" variant="primary" size="lg" className="w-full" disabled={busy || !password}>
          {busy ? "Linking…" : `Link ${link.data.provider} and sign in`}
        </Button>
        <p className="text-center text-footnote text-ink-secondary">
          Forgot it? <Link to={`/forgot-password?email=${encodeURIComponent(link.data.email)}`} className="font-semibold text-link hover:underline">Reset your password</Link>
        </p>
      </form>
    </AuthShell>
  )
}
