#!/usr/bin/env node
// Builds the offline gallery from the component previews: each
// components/<Name>/preview.html becomes gallery/<Name>.html with the fonts,
// tokens, bundle (and app-patterns.css when the preview links it) and a theme
// switch from ?theme=; gallery/index.html lists them by their @dsCard group.
//
//   node docs/design-system/gallery.mjs          write the gallery
//   node docs/design-system/gallery.mjs --check  list what is out of date
//
// Edit the previews, never the gallery pages. Touches docs/design-system only.
import fs from "node:fs"
import path from "node:path"
import { fileURLToPath } from "node:url"

const ds = path.dirname(fileURLToPath(import.meta.url))
const check = process.argv.includes("--check")
const INJECT = '<head><link rel="stylesheet" href="../fonts/fonts.css"><link rel="stylesheet" href="../tokens/tokens.css"><link rel="stylesheet" href="../components/bundle.css">'
const THEME = '<script>document.documentElement.dataset.theme=new URLSearchParams(location.search).get("theme")||"light"</script>'
// The artifact host serves assets as blobs; the gallery reads them from assets/.
const BLOBS = {
  e35a4a27277b0f21c1985c32042fe0f6: "../assets/mascot/search-empty.png",
  af02ec9ade2ebd7e5f2bd123e197a9f4: "../assets/logos/logo-dark.svg",
  "9843c101f41c95c604a70d3f25f8206f": "../assets/logos/logo-light.svg",
  "8b704577d2ab11348e7cd54b03a64fa5": "../assets/logos/logo-on-navy.png",
}
const ORDER = ["Brand", "Actions", "Inputs", "Status", "Content", "Chat", "Entity cards", "Overlays", "Navigation", "Landing page", "Pitch deck"]

const comps = fs.readdirSync(path.join(ds, "components")).filter((n) => fs.existsSync(path.join(ds, "components", n, "preview.html"))).sort()
const cards = []
let diffs = 0
for (const name of comps) {
  const src = fs.readFileSync(path.join(ds, "components", name, "preview.html"), "utf8")
  const meta = src.match(/<!-- @dsCard([^>]*)-->/)[1]
  const attr = (k) => (meta.match(new RegExp(k + '="([^"]*)"')) || meta.match(new RegExp(k + "=(\\d+)")) || [])[1]
  // A preview that needs the app patterns links them beside itself; the gallery sits one level up.
  const appLink = '<link rel="stylesheet" href="../app-patterns.css">'
  const needsApp = src.includes(appLink)
  let out = src.replace(appLink, "")
    .replace(/\/_blob\/([0-9a-f]{32})/g, (m, id) => BLOBS[id] ?? m)
    .replaceAll('src="../../assets/', 'src="../assets/').replace("<head>", INJECT + (needsApp ? '<link rel="stylesheet" href="../components/app-patterns.css">' : "") + THEME)
  const file = path.join(ds, "gallery", name + ".html")
  const have = fs.existsSync(file) ? fs.readFileSync(file, "utf8") : null
  if (have !== out) {
    diffs++
    if (check) console.log("differs:", name)
    else fs.writeFileSync(file, out)
  }
  cards.push({ name, group: attr("group") || "Brand", height: +attr("height"), width: attr("width"), subtitle: attr("subtitle") || "" })
}

const head = fs.readFileSync(path.join(ds, "gallery/index.html"), "utf8").split('<h2 class="grp">')[0]
const tail = "\n</div>\n<script>" + fs.readFileSync(path.join(ds, "gallery/index.html"), "utf8").split("\n</div>\n<script>")[1]
let body = ""
for (const g of ORDER) {
  const list = cards.filter((c) => c.group === g)
  if (!list.length) continue
  body += `<h2 class="grp">${g}</h2>`
  for (const c of list)
    body += `<section class="card"><header><h3>${c.name}</h3><p>${c.subtitle}</p><a href="../components/${c.name}/README.md">Guidelines</a></header><div class="frame"><iframe title="${c.name} preview" data-src="${c.name}.html" style="height:${c.height + 48}px;width:${c.width ? c.width + "px" : "100%"}" loading="lazy"></iframe></div></section>`
}
const unknown = cards.filter((c) => !ORDER.includes(c.group))
if (unknown.length) console.log("unknown groups:", unknown.map((c) => c.name + ":" + c.group))
const index = head + body + tail
const idxFile = path.join(ds, "gallery/index.html")
if (fs.readFileSync(idxFile, "utf8") !== index) {
  diffs++
  if (check) console.log("differs: index")
  else fs.writeFileSync(idxFile, index)
}
for (const f of fs.readdirSync(path.join(ds, "gallery")))
  if (f !== "index.html" && !comps.includes(f.replace(/\.html$/, ""))) console.log("orphan gallery page:", f)
console.log(check ? `${diffs} gallery file(s) out of date` : `wrote ${diffs} file(s)`)
if (check && diffs) process.exit(1)
