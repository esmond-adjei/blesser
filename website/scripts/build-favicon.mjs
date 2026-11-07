/**
 * Build the site favicon from the app's logo component.
 *
 *   node website/scripts/build-favicon.mjs
 *
 * The favicon is the app's own mark on a mist tile, the same artwork the
 * app and the site already share, so the tab and the brand cannot drift
 * apart. The app's React component is the source; this turns it into a
 * standalone SVG.
 */
import { mkdirSync, readFileSync, writeFileSync } from "node:fs"
import { tmpdir } from "node:os"
import { dirname, resolve } from "node:path"
import { fileURLToPath } from "node:url"
import { optimize } from "svgo"

const here = dirname(fileURLToPath(import.meta.url))
const repo = resolve(here, "../..")
const source = resolve(repo, "webapp/src/components/layout/AppLogo.tsx")
const target = resolve(repo, "website/public/favicon.svg")
const tmp = resolve(tmpdir(), "graduator-favicon-build")

mkdirSync(tmp, { recursive: true })

const component = readFileSync(source, "utf8")
const start = component.indexOf("<svg")
const end = component.lastIndexOf("</svg>") + "</svg>".length
if (start < 0 || end < 0) throw new Error("no <svg> found in AppLogo.tsx")

let svg = component.slice(start, end)

// The React bits have no place in a static file.
svg = svg.replace(/className=\{cn\("[^"]*", className\)\}/, "")
svg = svg.replace(/id=\{clipId\}/g, 'id="graduator-mark"')
svg = svg.replace(/clipPath=\{`url\(#\$\{clipId\}\)`\}/g, 'clip-path="url(#graduator-mark)"')
svg = svg.replace(/fillRule=/g, "fill-rule=")
// The mark's own ink: navy, as it reads on a light tile.
svg = svg.replace(/fill="currentColor"/g, 'fill="#10325e"')

// The mark's box (90 109 736 701) centred on a square tile with a margin.
const TILE = 1020
const MARGIN = 52
svg = svg.replace(/viewBox="90 109 736 701"/, `viewBox="0 0 ${TILE} ${TILE}"`)
svg = svg.replace(/<svg/, '<svg xmlns="http://www.w3.org/2000/svg"')
svg = svg.replace(
  /(<svg[^>]*>)/,
  `$1<rect width="${TILE}" height="${TILE}" rx="210" fill="#e8ecf0"/><g transform="translate(${MARGIN} 50)">`,
)
svg = svg.replace(/<\/svg>$/, "</g></svg>")

const { data: optimized } = optimize(svg, {
  multipass: true,
  plugins: [
    { name: "removeViewBox", active: false },
    // The mark is drawn at 736px wide; a tenth of a unit is invisible at
    // any size we use it, and it takes the path from 43 KB to 11 KB.
    { name: "convertPathData", params: { floatPrecision: 1 } },
    { name: "cleanupNumericValues", params: { floatPrecision: 1 } },
  ],
})

writeFileSync(target, optimized)
console.log(`favicon: ${target} (${optimized.length} bytes)`)
