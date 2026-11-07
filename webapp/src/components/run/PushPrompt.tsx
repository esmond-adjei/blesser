import * as React from "react"
import { useQuery } from "@tanstack/react-query"
import { BellRing, X } from "lucide-react"
import * as api from "../../lib/api"
import { currentSubscription, enablePush, permission, pushSupport } from "../../lib/push"
import { toastInfo, toastSuccess } from "../../lib/toast"
import { Button } from "../ui/button"

const DISMISSED_KEY = "graduator:push-prompt-dismissed"

function readDismissed(): boolean {
  try {
    return localStorage.getItem(DISMISSED_KEY) === "1"
  } catch {
    return false
  }
}

/** Asked on a running run, where the permission prompt makes sense; gone for good once dismissed, answered or subscribed. */
export function PushPrompt({ running }: { running: boolean }) {
  const [dismissed, setDismissed] = React.useState(readDismissed)
  const [subscribed, setSubscribed] = React.useState<boolean | null>(null)
  const support = pushSupport()
  const config = useQuery({
    queryKey: ["push-config"],
    queryFn: api.getPushConfig,
    enabled: running && !dismissed && support !== "unsupported",
    staleTime: 5 * 60_000,
  })

  React.useEffect(() => {
    let live = true
    void currentSubscription().then((sub) => {
      if (live) setSubscribed(!!sub)
    })
    return () => {
      live = false
    }
  }, [])

  const dismiss = () => {
    setDismissed(true)
    try {
      localStorage.setItem(DISMISSED_KEY, "1")
    } catch {
      /* storage unavailable: hidden for this page only */
    }
  }

  if (!running || dismissed || subscribed !== false || !config.data?.enabled) return null
  if (support === "unsupported" || permission() === "denied") return null

  async function turnOn() {
    const result = await enablePush().catch(() => "unavailable" as const)
    if (result === "ok") {
      toastSuccess("We'll notify this browser when the run finishes")
      setSubscribed(true)
    } else if (result === "denied") {
      toastInfo("Notifications are blocked. You can allow them later in the browser's site settings.")
      dismiss()
    } else {
      toastInfo("This browser can't receive push notifications.")
      dismiss()
    }
  }

  return (
    <div className="relative flex flex-col gap-2 rounded-lg border border-border bg-muted/40 p-3 pr-10 text-sm sm:flex-row sm:items-center">
      <BellRing className="hidden size-4 shrink-0 text-primary sm:block" />
      <div className="min-w-0 flex-1">
        <p className="font-medium">Notify me when it's done?</p>
        <p className="text-xs text-muted-foreground">
          {support === "ios-needs-home-screen"
            ? "On iPhone and iPad, add Blesser to your Home Screen first (Share, then Add to Home Screen), open it from there, and turn notifications on in Settings."
            : "Runs take a while. Get a browser notification when this one finishes, so you can close the tab."}
        </p>
      </div>
      {support === "supported" && (
        <Button data-tooltip="Get browser notifications when your research needs attention" size="sm" onClick={turnOn} className="self-start sm:self-auto">
          Turn on notifications
        </Button>
      )}
      <button
        type="button"
        onClick={dismiss}
        aria-label="Dismiss"
        data-tooltip="Dismiss"
        className="absolute right-2 top-2 flex size-7 cursor-pointer items-center justify-center rounded-md text-muted-foreground hover:bg-accent"
      >
        <X className="size-4" />
      </button>
    </div>
  )
}
