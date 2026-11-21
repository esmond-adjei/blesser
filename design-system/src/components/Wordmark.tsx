import { cn } from "../lib"

const WORDMARK = "font-sans text-[27px] leading-none font-extrabold tracking-[-0.04em] text-[var(--logo-ink,#0f4f3b)]"

/**
 * The lowercase "blesser" set beside the logo; size it with a text-* class.
 * motion="sunrise" slides it out from behind the mark, after <Logo motion="sunrise" />.
 */
export function Wordmark({ className, motion }: { className?: string; motion?: "sunrise" }) {
  if (motion === "sunrise")
    return (
      <span className={cn(WORDMARK, "bl-wordmark-mask", className)}>
        <span className="bl-wordmark-sunrise">blesser</span>
      </span>
    )
  return <span className={cn(WORDMARK, className)}>blesser</span>
}
