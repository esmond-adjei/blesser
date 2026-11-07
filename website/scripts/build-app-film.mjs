/**
 * Render the alternative product film, a recording of the real app.
 *
 *   node website/scripts/build-app-film.mjs
 *
 * Seeds an invented demo account (video/seed_demo.py), drives the running app
 * through one search in headless Chrome, and saves every frame: each frame
 * sets the scroll, typing, cursor and camera for its moment before the
 * screenshot, so a build is repeatable. Title cards and crossfades come from
 * video/titles.html. GStreamer encodes VP9 in WebM and H.264 in MP4, and the
 * demo account is dropped afterwards. The outputs are committed, like og.png,
 * so the site build needs none of this.
 *
 * Needs: the dev API and webapp running (APP_URL, default
 * http://localhost:5173), api/.venv, playwright-core with a Chrome (CHROME),
 * and gst-launch-1.0 with vp9enc, openh264enc and mp4mux.
 */
import { execFileSync } from "node:child_process"
import { mkdirSync, readFileSync, rmSync, statSync } from "node:fs"
import { tmpdir } from "node:os"
import { dirname, resolve } from "node:path"
import { fileURLToPath, pathToFileURL } from "node:url"
import { chromium } from "playwright-core"

const here = dirname(fileURLToPath(import.meta.url))
const api = resolve(here, "../../api")
const media = resolve(here, "../public/media")
const work = resolve(tmpdir(), "graduator-app-film")
const frames = resolve(work, "frames")
const tokenFile = resolve(work, "token")
const APP = (process.env.APP_URL || "http://localhost:5173").replace(/\/+$/, "")

const FPS = 30
// Laid out at 1440x810, captured at 10/9: 1600x900 frames.
const W = 1440
const H = 810
const SCALE = 10 / 9
const FADE = 0.4
// In the ranking shot, with the top match under the cursor.
const POSTER_AT = 3.2
const INTEREST = "Reinforcement learning for agile legged robots, PhD in Europe"
const REST = [W - 40, H * 0.45]
const ENTER = [W - 120, H - 300]

const seed = (args) =>
  execFileSync(resolve(api, ".venv/bin/python"), [resolve(here, "video/seed_demo.py"), ...args], {
    cwd: api,
    env: { ...process.env, PYTHONPATH: "." },
    encoding: "utf8",
  })

const clamp = (x) => Math.min(Math.max(x, 0), 1)
const ease = (x) => ((x = clamp(x)), x < 0.5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2)
const span = (t, from, to) => ease((t - from) / (to - from))
const mix = (a, b, k) => a + (b - a) * k
/** Eased position along [[time, [x, y]], ...]. */
const path = (t, keys) => {
  if (t <= keys[0][0]) return keys[0][1]
  for (let i = 1; i < keys.length; i++) {
    const [t0, p0] = keys[i - 1]
    const [t1, p1] = keys[i]
    if (t <= t1) {
      const k = span(t, t0, t1)
      return [mix(p0[0], p1[0], k), mix(p0[1], p1[1], k)]
    }
  }
  return keys.at(-1)[1]
}
const center = (box) => [box.x + box.width / 2, box.y + box.height / 2]

// Lives outside <body>, so the camera (a transform on body) never moves the
// cursor or caption off the screen coordinates the mouse uses.
const OVERLAY = () => {
  if (document.getElementById("film-cursor")) return
  const font = getComputedStyle(document.body).fontFamily
  const style = document.createElement("style")
  style.textContent = `
    *, *::before, *::after { transition: none !important; animation: none !important; caret-color: transparent !important; }
    body { transform-origin: 0 0; will-change: transform; }
    #film-cursor { position: fixed; z-index: 2147483647; left: 0; top: 0; width: 26px; height: 26px; pointer-events: none; filter: drop-shadow(0 2px 3px rgb(0 0 0 / .25)); }
    #film-ripple { position: fixed; z-index: 2147483646; width: 44px; height: 44px; margin: -22px 0 0 -22px; border-radius: 50%; pointer-events: none; background: rgb(31 87 184 / .28); }
    #film-caption { position: fixed; z-index: 2147483645; left: 50%; bottom: 34px; padding: 14px 26px; border-radius: 999px; pointer-events: none;
      background: rgb(11 26 46 / .9); color: #fff; font: 500 21px/1.3 ${font}; letter-spacing: -0.01em; white-space: nowrap; box-shadow: 0 10px 30px rgb(11 26 46 / .25); }`
  document.head.append(style)
  const cursor = document.createElement("div")
  cursor.id = "film-cursor"
  cursor.innerHTML = `<svg viewBox="0 0 26 26"><path d="M5 2.5v19.2l5.1-4.7 3.3 7.4 3.4-1.5-3.3-7.3 6.9-.4z" fill="#0b1a2e" stroke="#fff" stroke-width="1.6" stroke-linejoin="round"/></svg>`
  const ripple = document.createElement("div")
  ripple.id = "film-ripple"
  const caption = document.createElement("div")
  caption.id = "film-caption"
  document.documentElement.append(ripple, cursor, caption)
  window.__film = ({ cursor: c, ripple: r, caption: text, captionIn, zoom }) => {
    cursor.style.display = c ? "block" : "none"
    if (c) cursor.style.transform = `translate(${c[0] - 5}px, ${c[1] - 2}px)`
    ripple.style.display = r ? "block" : "none"
    if (r) {
      ripple.style.left = `${r.at[0]}px`
      ripple.style.top = `${r.at[1]}px`
      ripple.style.transform = `scale(${0.4 + r.k * 1.2})`
      ripple.style.opacity = String(1 - r.k)
    }
    caption.style.display = text ? "block" : "none"
    caption.textContent = text || ""
    caption.style.opacity = String(captionIn)
    caption.style.transform = `translate(-50%, ${(1 - captionIn) * 14}px)`
    const [s, x, y] = zoom || [1, 0, 0]
    document.body.style.transform = s === 1 ? "" : `translate(${x * (1 - s)}px, ${y * (1 - s)}px) scale(${s})`
  }
}

rmSync(work, { recursive: true, force: true })
mkdirSync(frames, { recursive: true })
mkdirSync(media, { recursive: true })

const ids = JSON.parse(seed([tokenFile]).trim().split("\n").at(-1))
const token = readFileSync(tokenFile, "utf8").trim()
const browser = await chromium.launch({ executablePath: process.env.CHROME || undefined })

let count = 0
const frameFile = (n) => `${frames}/${String(n).padStart(5, "0")}.jpg`

try {
  const context = await browser.newContext({ viewport: { width: W, height: H }, deviceScaleFactor: SCALE })
  // Only the first load takes the token; the app rotates it after that.
  await context.addInitScript((t) => {
    if (!localStorage.getItem("graduator.refresh_token")) localStorage.setItem("graduator.refresh_token", t)
  }, token)
  const app = await context.newPage()
  const cards = await context.newPage()
  await cards.goto(pathToFileURL(resolve(here, "video/titles.html")).href)
  await cards.evaluate(() => document.fonts.ready)

  const snap = async (page) => {
    await page.screenshot({ path: frameFile(count++), type: "jpeg", quality: 92 })
  }

  /** A shot's first frame, crossfaded in from the previous shot's last. */
  const begin = async (page) => {
    if (count === 0) return snap(page)
    const last = frameFile(count - 1)
    const first = `${work}/cut-${count}.jpg`
    await page.screenshot({ path: first, type: "jpeg", quality: 92 })
    const steps = Math.round(FADE * FPS)
    for (let i = 1; i <= steps; i++) {
      await cards.evaluate(([a, b, k]) => window.blend(a, b, k), [pathToFileURL(last).href, pathToFileURL(first).href, i / steps])
      await snap(cards)
    }
  }

  const title = async (name, seconds) => {
    for (let f = 0; f < Math.round(seconds * FPS); f++) {
      await cards.evaluate(([t, n]) => window.title(t, n), [f / FPS, name])
      await (f === 0 ? begin(cards) : snap(cards))
    }
  }

  /** One shot in the app: open `route`, then call `frame(t)` before each screenshot. */
  const shot = async (route, seconds, frame) => {
    // Live pages hold an event stream open, so "networkidle" never comes.
    await app.goto(APP + route, { waitUntil: "load" })
    // Park the real mouse in the empty right margin so no hover tooltip lingers.
    await app.mouse.move(...REST)
    await app.waitForTimeout(2500)
    await app.evaluate(OVERLAY)
    for (let f = 0; f < Math.round(seconds * FPS); f++) {
      const state = (await frame(f / FPS)) || {}
      await app.evaluate((s) => window.__film(s), state)
      await (f === 0 ? begin(app) : snap(app))
    }
  }

  const box = async (locator) => center(await locator.first().boundingBox())
  const scroller = (top) => app.evaluate((y) => document.querySelector("main").scrollTo(0, y), top)
  const caption = (text, t) => ({ caption: text, captionIn: span(t, 0.2, 0.7) })
  const click = (t, at, when) => (t >= when && t < when + 0.45 ? { ripple: { at, k: (t - when) / 0.45 } } : {})

  await title("open", 2.6)

  // 1. The question
  {
    let typed = 0
    let field, send
    await shot("/new", 6.4, async (t) => {
      field ??= await box(app.getByLabel("Research interest"))
      send ??= await box(app.getByLabel("Start run"))
      const start = [field[0] - 120, field[1]]
      const aside = [field[0] + 140, field[1] + 150]
      const at = path(t, [[0, ENTER], [0.4, ENTER], [1.1, start], [1.4, start], [2, aside], [4.6, aside], [5.4, send]])
      if (t >= 1.2 && typed === 0) await app.getByLabel("Research interest").focus()
      const want = Math.round(INTEREST.length * clamp((t - 1.3) / 3))
      if (want > typed) {
        await app.keyboard.insertText(INTEREST.slice(typed, want))
        typed = want
      }
      return { ...caption("Describe the research you want to do", t), cursor: at, ...click(t, start, 1.15), ...click(t, send, 5.55) }
    })
  }

  // 2. The run
  {
    let tab
    await shot(`/runs/${ids.run}`, 5.6, async (t) => {
      tab ??= await box(app.getByRole("tab", { name: /Professor agents/ }))
      const at = path(t, [[0, ENTER], [2.4, ENTER], [3.2, tab]])
      if (t >= 3.4 && t < 3.4 + 1 / FPS) await app.getByRole("tab", { name: /Professor agents/ }).click()
      return {
        ...caption("Gradis finds programmes and reads every professor's papers", t),
        cursor: at,
        ...click(t, tab, 3.4),
        zoom: [mix(1, 1.03, span(t, 0, 5.6)), 600, 300],
      }
    })
  }

  // 3. The ranking
  {
    let row
    await shot("/dossier", 5, async (t) => {
      row ??= await box(app.getByText("Amara Reyes"))
      const at = path(t, [[0, ENTER], [1.4, ENTER], [2.6, row]])
      await app.mouse.move(...at)
      if (Math.abs(t - POSTER_AT) < 0.5 / FPS) await app.screenshot({ path: `${media}/graduator-app-film-poster.jpg`, type: "jpeg", quality: 86 })
      return { ...caption("Every professor ranked by how well they fit", t), cursor: at, ...click(t, row, 3.9) }
    })
  }

  // 4. The evidence
  await shot(`/dossier/${ids.best_candidate}`, 7.2, async (t) => {
    await scroller(Math.round(mix(0, 330, span(t, 3.4, 6.4))))
    const z = t < 3 ? span(t, 0.3, 1.8) : 1 - span(t, 2.6, 3.4)
    return { ...caption("See the papers behind every score", t), zoom: [mix(1, 1.15, z), 480, 150] }
  })

  // 5. The email
  {
    let approve
    await shot(`/outbox/${ids.draft}`, 6.2, async (t) => {
      approve ??= await box(app.getByRole("button", { name: "Approve" }))
      const at = path(t, [[0, ENTER], [2.6, ENTER], [3.6, approve]])
      await app.mouse.move(...at)
      if (t >= 3.9 && t < 3.9 + 1 / FPS) await app.getByRole("button", { name: "Approve" }).click()
      return { ...caption("A first email that cites their work. You approve it.", t), cursor: at, ...click(t, approve, 3.9) }
    })
  }

  // 6. Gradis
  await shot(`/chat/${ids.conversation}`, 5, async (t) => ({
    ...caption("Ask Gradis about any match", t),
    zoom: [mix(1, 1.06, span(t, 0.3, 4.6)), 860, 260],
  }))

  // 7. The applications
  {
    let card
    await shot("/applications", 5, async (t) => {
      card ??= await box(app.getByText("PhD in Robotics", { exact: true }))
      const at = path(t, [[0, ENTER], [1.6, ENTER], [2.8, card]])
      await app.mouse.move(...at)
      return { ...caption("Track every deadline and requirement", t), cursor: at }
    })
  }

  await title("close", 3.6)
} finally {
  await browser.close()
  seed(["--drop"])
}

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

// Mostly flat, near-white UI: below these rates both encoders leave faint smears after a cut.
encode("graduator-app-film.webm", [
  "vp9enc", "end-usage=vbr", "target-bitrate=600000", "deadline=1", "cpu-used=2", "threads=8", "row-mt=true",
  "keyframe-max-dist=300", "!", "webmmux",
])
encode("graduator-app-film.mp4", [
  "openh264enc", "bitrate=1300000", "rate-control=bitrate", "complexity=high", "gop-size=60", "!", "h264parse", "!",
  "mp4mux", "faststart=true",
])

// KEEP_FRAMES=1 leaves them in the temp folder to check by eye.
if (!process.env.KEEP_FRAMES) rmSync(work, { recursive: true, force: true })
