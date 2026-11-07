import * as React from "react"
import { useLocation, useNavigate } from "react-router-dom"
import { Sparkles } from "lucide-react"
import { UPGRADE_EVENT, type UpgradeRequired } from "../../lib/api"
import { Button } from "../ui/button"
import { Dialog, DialogBody, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "../ui/dialog"

/** The single upgrade prompt, opened by any server 402 plan gate so features never hand-roll paywall UI. */
export function UpgradePrompt() {
  const [gate, setGate] = React.useState<UpgradeRequired | null>(null)
  const navigate = useNavigate()
  const location = useLocation()

  React.useEffect(() => {
    const on = (e: Event) => setGate((e as CustomEvent<UpgradeRequired>).detail)
    window.addEventListener(UPGRADE_EVENT, on)
    return () => window.removeEventListener(UPGRADE_EVENT, on)
  }, [])

  function seePlans() {
    setGate(null)
    const params = new URLSearchParams(location.search)
    params.set("settings", "usage")
    navigate(`${location.pathname}?${params.toString()}`)
  }

  const pct = gate?.used != null && gate.limit ? Math.min(100, Math.round((gate.used / gate.limit) * 100)) : null
  return (
    <Dialog open={gate !== null} onOpenChange={(o) => !o && setGate(null)}>
      <DialogContent onClose={() => setGate(null)} className="max-w-md">
        {gate && (
          <>
            <DialogHeader>
              <span className="mb-1 flex size-9 items-center justify-center rounded-full bg-primary/10 text-primary" aria-hidden>
                <Sparkles className="size-4" />
              </span>
              <DialogTitle>
                {gate.kind === "quota"
                  ? `You've used this month's ${gate.noun ?? gate.label.toLowerCase()}`
                  : `${gate.label} is part of ${gate.upgrade_to === "pro" ? "Pro" : gate.upgrade_to}`}
              </DialogTitle>
              <DialogDescription>{gate.message}</DialogDescription>
            </DialogHeader>
            {pct !== null && (
              <DialogBody className="py-4">
                <div>
                  <div className="h-1.5 overflow-hidden rounded-full bg-muted" aria-hidden>
                    <div className="h-full rounded-full bg-caution" style={{ width: `${pct}%` }} />
                  </div>
                  <p className="mt-1.5 text-xs tabular-nums text-muted-foreground">
                    {gate.used!.toLocaleString()} of {gate.limit!.toLocaleString()} used, resets on the 1st
                  </p>
                </div>
              </DialogBody>
            )}
            <DialogFooter>
              <Button variant="ghost" onClick={() => setGate(null)}>Not now</Button>
              <Button onClick={seePlans}>See plans</Button>
            </DialogFooter>
          </>
        )}
      </DialogContent>
    </Dialog>
  )
}
