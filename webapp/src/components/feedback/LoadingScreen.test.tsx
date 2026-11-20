import { Logo, Wordmark } from "@blesser/ui"
import { renderToStaticMarkup } from "react-dom/server"
import * as React from "react"
import { describe, expect, it } from "vitest"
import { LoadingScreen } from "./LoadingScreen"

// Vitest compiles the design-system package (outside this app's tsconfig) with the classic JSX runtime.
Object.assign(globalThis, { React })

describe("logo motion", () => {
  it("draws the loader as the Climb loop with three steps and a clipped sun", () => {
    const html = renderToStaticMarkup(<LoadingScreen />)
    expect(html).toContain('role="status"')
    expect(html).toContain("bl-logo-climb")
    for (const step of [1, 2, 3]) expect(html).toContain(`bl-logo-step-${step}`)
    const clip = html.match(/clipPath id="([^"]+)"/)?.[1]
    expect(clip).toBeTruthy()
    expect(html).toContain(`clip-path="url(#${clip})"`)
  })

  it("gives each animated logo its own horizon clip", () => {
    const html = renderToStaticMarkup(
      <>
        <Logo motion="sunrise" />
        <Logo motion="sunrise" />
      </>,
    )
    const ids = [...html.matchAll(/clipPath id="([^"]+)"/g)].map((m) => m[1])
    expect(ids).toHaveLength(2)
    expect(new Set(ids).size).toBe(2)
  })

  it("leaves the still logo and wordmark unchanged without motion", () => {
    expect(renderToStaticMarkup(<Logo />)).not.toContain("bl-logo-")
    expect(renderToStaticMarkup(<Wordmark />)).not.toContain("bl-wordmark")
    expect(renderToStaticMarkup(<Wordmark motion="sunrise" />)).toContain("bl-wordmark-sunrise")
  })
})
