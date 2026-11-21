import { useEffect, useRef } from "react"
import { cn } from "@blesser/ui"

/** The logo's half sun with a face; its eyes follow the pointer. */
export function SunMascot({ size = 64, className }: { size?: number; className?: string }) {
  const eyes = useRef<SVGGElement>(null)
  const root = useRef<SVGSVGElement>(null)
  useEffect(() => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches || !window.matchMedia("(pointer: fine)").matches) return
    let frame = 0
    const look = (event: PointerEvent) => {
      cancelAnimationFrame(frame)
      frame = requestAnimationFrame(() => {
        const box = root.current?.getBoundingClientRect()
        if (!box || !eyes.current) return
        const dx = event.clientX - (box.left + box.width / 2)
        const dy = event.clientY - (box.top + box.height / 2)
        const distance = Math.hypot(dx, dy) || 1
        const reach = Math.min(2.4, distance / 90)
        eyes.current.style.transform = `translate(${(dx / distance) * reach}px, ${(dy / distance) * reach}px)`
      })
    }
    window.addEventListener("pointermove", look, { passive: true })
    return () => {
      window.removeEventListener("pointermove", look)
      cancelAnimationFrame(frame)
    }
  }, [])
  return (
    <svg ref={root} viewBox="0 0 64 32" width={size} height={size / 2} aria-hidden="true" className={cn("overflow-visible", className)}>
      <path d="M2 32a30 30 0 0 1 60 0Z" className="fill-sun" />
      <g ref={eyes} className="transition-transform duration-100 ease-out">
        <ellipse cx="23" cy="22" rx="2.3" ry="3.1" className="fill-on-sun" />
        <ellipse cx="41" cy="22" rx="2.3" ry="3.1" className="fill-on-sun" />
        <path d="M19.5 14.6 26.5 16.2M44.5 14.6 37.5 16.2" fill="none" strokeWidth="2.2" strokeLinecap="round" className="stroke-on-sun" />
      </g>
    </svg>
  )
}
