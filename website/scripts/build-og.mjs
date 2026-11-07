/**
 * Render the social card (og.png) from the real brand assets.
 *
 *   node website/scripts/build-og.mjs
 *
 * A static PNG is committed so the site needs no image pipeline at build
 * time and the card is identical on every deploy.
 */
import { execFileSync } from "node:child_process"
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs"
import { tmpdir } from "node:os"
import { dirname, resolve } from "node:path"
import { fileURLToPath } from "node:url"

const here = dirname(fileURLToPath(import.meta.url))
const repo = resolve(here, "../..")
// The navy-ink mark: the card is a light background.
const logo = resolve(repo, "webapp/public/logo-dark.svg")
// Gradis, as the site shows it.
const mascot = resolve(repo, "webapp/public/mascot-states/happy.png")
const out = resolve(repo, "website/public/og.png")
const tmp = resolve(tmpdir(), "graduator-og-build")

mkdirSync(tmp, { recursive: true })

const mark = readFileSync(logo, "utf8").replace(/^<\?xml.*?\?>/, "").trim()
const gradis = `data:image/png;base64,${readFileSync(mascot).toString("base64")}`

const html = `<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <link rel="preconnect" href="https://fonts.googleapis.com" />
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
    <link
      rel="stylesheet"
      href="https://fonts.googleapis.com/css2?family=Newsreader:opsz,wght@6..72,600&family=Noto+Sans:wght@400;500&display=block"
    />
    <style>
      * { margin: 0; padding: 0; box-sizing: border-box; }
      body {
        width: 1200px; height: 630px;
        background: linear-gradient(135deg, #f7f9fb 0%, #eef2f7 100%);
        font-family: "Noto Sans", "DejaVu Sans", "Helvetica Neue", Arial, sans-serif;
        position: relative; overflow: hidden;
        color: #10325e;
        display: flex; flex-direction: column; justify-content: space-between;
        padding: 64px 72px;
      }
      .mark { width: 84px; height: 80px; }
      .mark svg { width: 100%; height: 100%; display: block; }
      h1 {
        font-family: "Newsreader", Georgia, serif; font-optical-sizing: auto;
        font-size: 70px; line-height: 1.04; letter-spacing: -0.015em; font-weight: 600; max-width: 15ch;
      }
      p { margin-top: 24px; font-size: 26px; line-height: 1.45; color: #3c4d6b; max-width: 40ch; }
      .foot { display: flex; align-items: center; gap: 18px; font-size: 23px; color: #10325e; }
      .rule { width: 56px; height: 6px; border-radius: 3px; background: #eda41d; }
      .glow {
        position: absolute; right: -120px; top: 60px; width: 620px; height: 620px; border-radius: 50%;
        background: radial-gradient(circle, rgba(237, 164, 29, 0.28) 0%, rgba(237, 164, 29, 0) 65%);
      }
      .gradis { position: absolute; right: 80px; bottom: 70px; width: 330px; }
    </style>
  </head>
  <body>
    <div class="glow"></div>
    <img class="gradis" src="${gradis}" alt="" />
    <div class="mark">${mark}</div>
    <div>
      <h1>Find the professors you actually want to work with.</h1>
      <p>It reads their papers, ranks them by fit and drafts the first email. You decide what gets sent.</p>
    </div>
    <div class="foot"><span class="rule"></span><span>Graduator. Free to start.</span></div>
  </body>
</html>`

const htmlPath = resolve(tmp, "og.html")
writeFileSync(htmlPath, html)

// CHROME points at any Chrome or Chromium binary when none is on the usual paths.
const chrome = [process.env.CHROME, "/usr/bin/google-chrome", "/usr/bin/chromium", "/usr/bin/chromium-browser"].find(
  (bin) => bin && existsSync(bin),
)
if (!chrome) throw new Error("no chrome binary found for the social card")

execFileSync(chrome, [
  "--headless=new",
  "--disable-gpu",
  "--no-sandbox",
  "--hide-scrollbars",
  "--force-device-scale-factor=1",
  "--window-size=1200,630",
  // Give the web fonts time to arrive before the shot.
  "--virtual-time-budget=8000",
  `--screenshot=${out}`,
  `file://${htmlPath}`,
])

console.log(`og: ${out}`)
