/** Samples a damped spring into a CSS `linear()` easing. */
export function springEasing(damping: number, points = 48): string {
  const w = 9
  const wd = w * Math.sqrt(1 - damping * damping)
  const stops = Array.from({ length: points + 1 }, (_, i) => {
    const t = i / points
    const x =
      1 -
      Math.exp(-damping * w * t) *
        (Math.cos(wd * t) + ((damping * w) / wd) * Math.sin(wd * t))
    return (i === points ? 1 : x).toFixed(4)
  })
  return `linear(${stops.join(", ")})`
}

/** Whether the browser accepts `linear()` timing functions. */
export const LINEAR_OK =
  typeof CSS !== "undefined" && CSS.supports("transition-timing-function", "linear(0, 1)")
