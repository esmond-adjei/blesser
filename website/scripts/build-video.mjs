/**
 * Render the product film from scripts/video/scene.html.
 *
 *   node website/scripts/build-video.mjs
 *
 * The scene draws any moment of the film with render(t), so this steps
 * through it at 30 frames a second in headless Chrome, saves each frame,
 * and encodes them with GStreamer: VP9 in WebM for most browsers and
 * H.264 in MP4 for older Safari. A still from the dossier scene becomes
 * the poster. The outputs are committed, like og.png, so the site build
 * needs none of this.
 *
 * Needs: playwright-core (a dev dependency), a Chrome or Chromium (CHROME
 * overrides the one Playwright installed), and gst-launch-1.0 with the
 * vp9enc, openh264enc and mp4mux elements.
 */
import { execFileSync } from "node:child_process"
import { mkdirSync, rmSync, statSync } from "node:fs"
import { tmpdir } from "node:os"
import { dirname, resolve } from "node:path"
import { fileURLToPath, pathToFileURL } from "node:url"
import { chromium } from "playwright-core"

const here = dirname(fileURLToPath(import.meta.url))
const scene = resolve(here, "video/scene.html")
const media = resolve(here, "../public/media")
const frames = resolve(tmpdir(), "graduator-film-frames")

const FPS = 30
// 1200x675 laid out, captured at 4/3: 1600x900 frames.
const WIDTH = 1200
const HEIGHT = 675
const SCALE = 4 / 3
// The dossier, sorted, with a paper open.
const POSTER_AT = 16.9

rmSync(frames, { recursive: true, force: true })
mkdirSync(frames, { recursive: true })
mkdirSync(media, { recursive: true })

const browser = await chromium.launch({ executablePath: process.env.CHROME || undefined })
const page = await browser.newPage({ viewport: { width: WIDTH, height: HEIGHT }, deviceScaleFactor: SCALE })
await page.goto(pathToFileURL(scene).href, { waitUntil: "networkidle" })
const duration = await page.evaluate(async () => {
  await window.ready
  return window.DURATION
})

const total = Math.round(duration * FPS)
for (let frame = 0; frame < total; frame++) {
  await page.evaluate((t) => window.render(t), frame / FPS)
  await page.screenshot({ path: `${frames}/${String(frame).padStart(5, "0")}.jpg`, type: "jpeg", quality: 92 })
  if (frame % 150 === 0) console.log(`frame ${frame}/${total}`)
}

await page.evaluate((t) => window.render(t), POSTER_AT)
await page.screenshot({ path: `${media}/graduator-film-poster.jpg`, type: "jpeg", quality: 86 })
await browser.close()

const source = [
  "multifilesrc",
  `location=${frames}/%05d.jpg`,
  "index=0",
  `caps=image/jpeg,framerate=${FPS}/1`,
  "!",
  "jpegdec",
  "!",
  "videoconvert",
  "!",
  // JPEG frames are full range; say so, and convert to the limited-range
  // BT.709 that players assume, or H.264 comes out washed out.
  "video/x-raw,format=I420,colorimetry=bt709",
  "!",
]

const encode = (name, elements) => {
  const out = `${media}/${name}`
  execFileSync("gst-launch-1.0", ["-q", ...source, ...elements, "!", "filesink", `location=${out}`], { stdio: "inherit" })
  console.log(`${name}: ${(statSync(out).size / 1e6).toFixed(1)} MB`)
}

// Mostly flat, near-white UI: at lower rates both encoders leave faint
// smears where a card has just moved off, so keep some headroom and a
// keyframe every two seconds.
encode("graduator-film.webm", [
  "vp9enc",
  "end-usage=vbr",
  "target-bitrate=1800000",
  "deadline=1",
  "cpu-used=2",
  "threads=8",
  "row-mt=true",
  "keyframe-max-dist=60",
  "!",
  "webmmux",
])

encode("graduator-film.mp4", [
  "openh264enc",
  "bitrate=2200000",
  "rate-control=bitrate",
  "complexity=high",
  "gop-size=60",
  "!",
  "h264parse",
  "!",
  "mp4mux",
  "faststart=true",
])

rmSync(frames, { recursive: true, force: true })
