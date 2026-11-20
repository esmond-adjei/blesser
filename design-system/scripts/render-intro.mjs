// Renders motion/horizon.html to MP4 at 60fps, one screenshot per frame, then encodes with ffmpeg.
// Needs ffmpeg on PATH and a Chromium: CHROMIUM_PATH=/path/to/chrome node scripts/render-intro.mjs [texture=rings|none]
// Writes assets/motion/blesser-intro-16x9.mp4, -1x1.mp4 and a poster PNG for each.
import { execFileSync } from "node:child_process"
import { mkdirSync, mkdtempSync, rmSync } from "node:fs"
import { tmpdir } from "node:os"
import { join } from "node:path"
import { fileURLToPath } from "node:url"
import { chromium } from "playwright-core"

const FPS = 60
const HOLD_MS = 1200 // the finished lockup stays on screen after the animation ends
const root = fileURLToPath(new URL("../", import.meta.url))
const page_url = new URL("../motion/horizon.html", import.meta.url).href
const out = join(root, "assets/motion")
mkdirSync(out, { recursive: true })

// Pass texture=rings or texture=none to render the other grounds (files get a suffix).
const texture = process.argv.find((a) => a.startsWith("texture="))?.slice(8)
const suffix = texture && texture !== "grain" ? `-${texture}` : ""
const extra = texture ? `texture=${texture}` : ""
const cuts = [
  { name: `16x9${suffix}`, query: `?${extra}`, width: 1920, height: 1080 },
  { name: `1x1${suffix}`, query: `?ratio=square&${extra}`, width: 1080, height: 1080 },
]

const browser = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH, args: ["--no-sandbox"] })
try {
  for (const cut of cuts) {
    const page = await browser.newPage({ viewport: { width: cut.width, height: cut.height } })
    await page.goto(page_url + cut.query)
    await page.evaluate(() => window.ready)
    const total = (await page.evaluate(() => window.TOTAL)) + HOLD_MS
    const frames = mkdtempSync(join(tmpdir(), "blesser-intro-"))
    const count = Math.round((total / 1000) * FPS)
    for (let i = 0; i <= count; i++) {
      await page.evaluate((ms) => window.seek(ms), (i * 1000) / FPS)
      await page.screenshot({ path: join(frames, `${String(i).padStart(4, "0")}.png`) })
    }
    const file = join(out, `blesser-intro-${cut.name}`)
    execFileSync("ffmpeg", ["-y", "-loglevel", "error", "-framerate", String(FPS), "-i", join(frames, "%04d.png"),
      "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18", "-preset", "slow", "-movflags", "+faststart", `${file}.mp4`])
    execFileSync("ffmpeg", ["-y", "-loglevel", "error", "-i", join(frames, `${String(count).padStart(4, "0")}.png`), `${file}-poster.png`])
    rmSync(frames, { recursive: true })
    await page.close()
    console.log(`${file}.mp4 (${count + 1} frames)`)
  }
} finally {
  await browser.close()
}
