import { readFile } from "node:fs/promises"
import { createRequire } from "node:module"
import { dirname, join } from "node:path"
import type { SatoriOptions } from "satori"

type Font = SatoriOptions["fonts"][number]

const require = createRequire(import.meta.url)
const dir = (pkg: string) => join(dirname(require.resolve(`${pkg}/package.json`)), "files")

const BRAND = ["latin", "latin-ext"]
// Noto Sans only fills glyphs the brand faces lack, such as Akan's ɛ and ɔ.
const FALLBACK = ["latin-ext"]

const FACES: { name: string; pkg: string; file: string; weight: Font["weight"]; subsets?: string[] }[] = [
  { name: "Bricolage Grotesque", pkg: "@fontsource/bricolage-grotesque", file: "bricolage-grotesque", weight: 700 },
  { name: "Bricolage Grotesque", pkg: "@fontsource/bricolage-grotesque", file: "bricolage-grotesque", weight: 800 },
  { name: "Figtree", pkg: "@fontsource/figtree", file: "figtree", weight: 400 },
  { name: "Figtree", pkg: "@fontsource/figtree", file: "figtree", weight: 600 },
  { name: "Figtree", pkg: "@fontsource/figtree", file: "figtree", weight: 700 },
  { name: "Noto Sans", pkg: "@fontsource/noto-sans", file: "noto-sans", weight: 400, subsets: FALLBACK },
  { name: "Noto Sans", pkg: "@fontsource/noto-sans", file: "noto-sans", weight: 700, subsets: FALLBACK },
  { name: "Noto Sans", pkg: "@fontsource/noto-sans", file: "noto-sans", weight: 800, subsets: FALLBACK },
]

let loaded: Promise<Font[]> | null = null

/** Static WOFF faces: Satori reads neither WOFF2 nor variable axes. */
export function fonts(): Promise<Font[]> {
  loaded ??= Promise.all(
    FACES.flatMap((f) =>
      (f.subsets ?? BRAND).map(async (subset) => ({
        name: f.name,
        weight: f.weight,
        style: "normal" as const,
        data: await readFile(join(dir(f.pkg), `${f.file}-${subset}-${f.weight}-normal.woff`)),
      })),
    ),
  ).catch((err) => {
    loaded = null
    throw err
  })
  return loaded
}
