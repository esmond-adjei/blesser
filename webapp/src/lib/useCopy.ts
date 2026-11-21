import { useEffect, useState } from "react"
import { toastError } from "./toast"

export function useCopy(text: () => string) {
  const [copied, setCopied] = useState(false)
  useEffect(() => {
    if (!copied) return
    const timer = window.setTimeout(() => setCopied(false), 1600)
    return () => window.clearTimeout(timer)
  }, [copied])
  const copy = () => navigator.clipboard.writeText(text()).then(() => setCopied(true), () => toastError("Couldn't copy"))
  return { copied, copy }
}
