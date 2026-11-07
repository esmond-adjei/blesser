import * as React from "react"

/** A clock ticking every `everyMs` (a second by default), only while `active`. */
export function useNow(active: boolean, everyMs = 1000): number {
  const [now, setNow] = React.useState(() => Date.now())
  React.useEffect(() => {
    if (!active) return
    const id = window.setInterval(() => setNow(Date.now()), everyMs)
    return () => window.clearInterval(id)
  }, [active, everyMs])
  return now
}
