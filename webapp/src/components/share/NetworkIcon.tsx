import * as React from "react"
import { Mail } from "lucide-react"
import { cn } from "@blesser/ui"
import facebook from "../../assets/social/facebook.svg"
import linkedin from "../../assets/social/linkedin.svg"
import whatsapp from "../../assets/social/whatsapp.svg"
import x from "../../assets/social/x.svg"
import type { ShareNetwork } from "../../lib/share"

/**
 * Official brand colours for each network's mark. These are third-party
 * logos, so they keep the platform's colour instead of the link colour.
 * X is black, and turns white in dark mode the way X renders its own mark.
 */
const MARKS = {
  whatsapp: { src: whatsapp, tint: "bg-[#25d366]" },
  x: { src: x, tint: "bg-black dark:bg-white" },
  linkedin: { src: linkedin, tint: "bg-[#0a66c2]" },
  facebook: { src: facebook, tint: "bg-[#0866ff]" },
} as const

/** A network's brand mark in the platform's own colour. */
export function NetworkIcon({ name, className }: { name: ShareNetwork; className?: string }) {
  if (name === "email") {
    return <Mail aria-hidden="true" strokeWidth={1.75} className={cn("size-4 shrink-0", className)} />
  }
  const mark = `url("${MARKS[name].src}") center / contain no-repeat`
  return (
    <span
      aria-hidden="true"
      className={cn("inline-block size-4 shrink-0", MARKS[name].tint, className)}
      style={{ WebkitMask: mark, mask: mark } as React.CSSProperties}
    />
  )
}
