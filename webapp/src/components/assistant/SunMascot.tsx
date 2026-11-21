import { useEffect, useRef } from "react"
import { cn } from "@blesser/ui"

const RAYS = Array.from({ length: 8 }, (_, i) => i * 45)

/** The Assistant's face: a sun whose eyes follow the pointer. */
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
        const reach = Math.min(2.6, distance / 90)
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
    <svg ref={root} viewBox="0 0 64 64" width={size} height={size} aria-hidden="true" className={cn("overflow-visible", className)}>
      <g className="origin-center motion-safe:animate-[spin_40s_linear_infinite]" style={{ transformOrigin: "32px 32px" }}>
        {RAYS.map((angle) => (
          <rect key={angle} x="30" y="2" width="4" height="9" rx="2" className="fill-sun" transform={`rotate(${angle} 32 32)`} />
        ))}
      </g>
      <circle cx="32" cy="32" r="19" className="fill-sun" />
      <g ref={eyes} className="transition-transform duration-100 ease-out">
        <ellipse cx="25.5" cy="30" rx="2.4" ry="3.2" className="fill-on-sun" />
        <ellipse cx="38.5" cy="30" rx="2.4" ry="3.2" className="fill-on-sun" />
      </g>
      <path d="M26 38.5c2.2 2.6 9.8 2.6 12 0" fill="none" strokeWidth="2.2" strokeLinecap="round" className="stroke-on-sun" />
    </svg>
  )
}
