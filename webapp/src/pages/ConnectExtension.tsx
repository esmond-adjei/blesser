import * as React from "react"
import { Link, Navigate, useLocation, useSearchParams } from "react-router-dom"
import { CheckCircle2, FileText, FolderKanban, ListChecks, MessageSquareText, Sparkles, UserRound } from "lucide-react"
import { Button, Logo, buttonVariants } from "@blesser/ui"
import * as api from "../lib/api"
import { useAuth } from "../lib/auth"
import { accountName } from "../lib/format"
import { browserName, handToExtension, parseConnectParams } from "../lib/extension"
import { LoadingScreen } from "../components/feedback/LoadingScreen"
import { Alert, AlertDescription } from "../components/ui/feedback"

const ACCESS = [
  { icon: UserRound, text: "Your Apply kit profile, including ID numbers for fields that ask for exactly those" },
  { icon: FolderKanban, text: "Your projects, such as the ventures you apply with" },
  { icon: FileText, text: "Your documents, to attach them to upload fields" },
  { icon: MessageSquareText, text: "Your saved answers" },
  { icon: ListChecks, text: "Your tracked applications, to mark one as applied" },
  { icon: Sparkles, text: "Drafting answers you haven't saved, within your daily limit" },
]

type Phase = { step: "ask" } | { step: "working" } | { step: "done" } | { step: "failed"; message: string }

const FAILURES: Record<string, string> = {
  unreachable: "Blesser couldn't reach the extension. Check it's installed and switched on in this browser, then press Connect in the extension again.",
  state_mismatch: "This connect link has expired or was opened twice. Press Connect in the extension again.",
  rejected: "The extension turned the connection down. Check its options point at this Blesser, then try again.",
}

function Frame({ children }: { children: React.ReactNode }) {
  return (
    <div className="mx-auto flex min-h-dvh w-full max-w-[480px] flex-col justify-center gap-6 px-4 py-8">
      <Logo className="size-10" />
      <div className="space-y-5 rounded-lg border border-separator bg-surface p-6 shadow-elevation-1">{children}</div>
    </div>
  )
}

export function ConnectExtension() {
  const { user, ready } = useAuth()
  const location = useLocation()
  const [searchParams] = useSearchParams()
  const params = React.useMemo(() => parseConnectParams(searchParams), [searchParams])
  const [phase, setPhase] = React.useState<Phase>({ step: "ask" })

  if (!ready) return <LoadingScreen />
  if (!user) return <Navigate to={`/login?next=${encodeURIComponent(location.pathname + location.search)}`} replace />

  if (!params) {
    return (
      <Frame>
        <h1 className="font-display text-3xl font-bold text-ink">This connect link isn't complete</h1>
        <p className="text-callout text-ink-secondary">Open the Blesser extension from your browser's toolbar and press Connect to start again.</p>
        <Link to="/opportunities" className={buttonVariants({ size: "sm", variant: "secondary" })}>Back to Blesser</Link>
      </Frame>
    )
  }

  const allow = async () => {
    setPhase({ step: "working" })
    let grant: api.ExtensionGrant
    try {
      grant = await api.connectExtension(browserName(navigator.userAgent, navigator.platform))
    } catch (err) {
      setPhase({ step: "failed", message: api.apiMessage(err) })
      return
    }
    const result = await handToExtension(params, grant)
    if (result.ok) {
      setPhase({ step: "done" })
      return
    }
    // The tokens never reached the extension, so don't leave a live session behind.
    await api.revokeExtensionSession(grant.session.id).catch(() => undefined)
    setPhase({ step: "failed", message: FAILURES[result.reason] })
  }

  if (phase.step === "done") {
    return (
      <Frame>
        <CheckCircle2 className="size-8 text-positive" aria-hidden="true" />
        <div className="space-y-1.5">
          <h1 className="font-display text-3xl font-bold text-ink">Extension connected</h1>
          <p className="text-callout text-ink-secondary">
            Open an application form and press <span className="font-semibold text-ink">Fill this page</span> in the extension. You can close this tab.
          </p>
        </div>
        <p className="text-footnote text-ink-secondary">
          To disconnect later, use the extension's menu or <Link to="/settings/account" className="font-medium text-link">Settings, Account and security</Link>.
        </p>
      </Frame>
    )
  }

  return (
    <Frame>
      <div className="space-y-1.5">
        <h1 className="font-display text-3xl font-bold text-ink">Connect the Blesser extension?</h1>
        <p className="text-callout text-ink-secondary">
          Signed in as <span className="font-medium text-ink">{accountName(user)}</span>. The extension fills application forms in this browser from your Apply kit.
        </p>
      </div>
      <div>
        <h2 className="text-callout font-semibold text-ink">It can use</h2>
        <ul className="mt-2 space-y-2">
          {ACCESS.map(({ icon: Icon, text }) => (
            <li key={text} className="flex gap-2.5 text-callout text-ink">
              <Icon className="mt-0.5 size-4 shrink-0 text-ink-secondary" strokeWidth={1.75} aria-hidden="true" />
              {text}
            </li>
          ))}
        </ul>
      </div>
      <p className="text-footnote text-ink-secondary">
        It can't change your account, see your password or read pages until you press Fill. It never submits a form for you.
      </p>
      {phase.step === "failed" ? (
        <Alert variant="destructive">
          <AlertDescription>{phase.message}</AlertDescription>
        </Alert>
      ) : null}
      <div className="flex justify-end gap-2">
        <Link to="/opportunities" className={buttonVariants({ size: "md", variant: "quiet" })}>Cancel</Link>
        <Button variant="brand" disabled={phase.step === "working"} onClick={() => void allow()}>
          {phase.step === "working" ? "Connecting…" : "Allow"}
        </Button>
      </div>
    </Frame>
  )
}
