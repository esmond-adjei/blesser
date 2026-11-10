// End-to-end: builds a test copy of the extension, connects it through the member app and fills a fixture form.
// Needs an API (MAIL_BACKEND=console) at E2E_API_URL and the member app at E2E_APP_URL proxying to it.
import assert from "node:assert/strict"
import { execFileSync } from "node:child_process"
import { existsSync, mkdirSync, mkdtempSync, readFileSync, readdirSync } from "node:fs"
import { createServer } from "node:http"
import { homedir, tmpdir } from "node:os"
import { join } from "node:path"
import { chromium } from "playwright-core"

const root = new URL("..", import.meta.url).pathname
const API = process.env.E2E_API_URL ?? "http://localhost:8010"
const APP = process.env.E2E_APP_URL ?? "http://localhost:5180"
const SITE_PORT = Number(process.env.E2E_SITE_PORT ?? 5190)
const SITE = `http://localhost:${SITE_PORT}`
const OUT = process.env.E2E_SCREENSHOTS ?? join(root, "dist-e2e-shots")
const DIST = join(root, "dist-e2e")
mkdirSync(OUT, { recursive: true })

function chromiumPath() {
  if (process.env.CHROMIUM_PATH) return process.env.CHROMIUM_PATH
  const cache = join(homedir(), ".cache/ms-playwright")
  const dir = readdirSync(cache).filter((d) => /^chromium-\d+$/.test(d)).sort().pop()
  assert(dir, "No Playwright Chromium in ~/.cache/ms-playwright")
  for (const sub of ["chrome-linux64/chrome", "chrome-linux/chrome"]) if (existsSync(join(cache, dir, sub))) return join(cache, dir, sub)
  throw new Error("Chromium binary not found")
}

const openapi = await (await fetch(`${API}/openapi.json`)).json()
for (const path of ["/api/app/extension/connect", "/api/app/extension/me", "/api/app/autofill/fill"])
  assert(openapi.paths[path], `The API at ${API} has no ${path}`)

const env = { ...process.env, BLESSER_API_URL: API, BLESSER_APP_URL: APP, BLESSER_E2E_HOSTS: `${SITE}/*`, BLESSER_OUT_DIR: DIST }
execFileSync("npx", ["vite", "build", "--logLevel", "warn"], { cwd: root, env, stdio: "inherit" })
execFileSync("npx", ["vite", "build", "-c", "vite.content.config.ts", "--logLevel", "warn"], { cwd: root, env, stdio: "inherit" })

const site = createServer((req, res) => {
  const name = (req.url ?? "/").split("?")[0].replace(/^\/+/, "") || "form.html"
  const file = join(root, "e2e/site", name.replace(/[^a-z0-9.-]/gi, ""))
  if (!existsSync(file)) return res.writeHead(404).end()
  res.writeHead(200, { "Content-Type": "text/html; charset=utf-8" }).end(readFileSync(file))
})
await new Promise((resolve) => site.listen(SITE_PORT, "127.0.0.1", resolve))

const email = `ext-e2e-${Date.now()}@example.com`
const password = "e2e-Passw0rd!"
async function call(method, path, token, body, raw = false) {
  const res = await fetch(`${API}${path}`, {
    method,
    headers: { ...(token ? { Authorization: `Bearer ${token}` } : {}), ...(body && !(body instanceof FormData) ? { "Content-Type": "application/json" } : {}) },
    body: body instanceof FormData ? body : body ? JSON.stringify(body) : undefined,
  })
  const text = await res.text()
  if (!res.ok) throw new Error(`${method} ${path} -> ${res.status} ${text.slice(0, 300)}`)
  return raw ? text : text ? JSON.parse(text) : null
}

const session = await call("POST", "/api/app/auth/register", null, { email, password, accept_terms: true })
const token = session.tokens.access_token
const results = { email, steps: [] }
let context
try {
  await call("PUT", "/api/app/profile", token, {
    given_name: "Ama", family_name: "Mensah", pronouns: "she/her", email: "ama.mensah@example.com", phone: "+233 24 555 0101",
    city: "Kumasi", country_of_residence: "Ghana", nationality: "Ghanaian", linkedin_url: "https://www.linkedin.com/in/ama-mensah-e2e",
  })
  await call("POST", "/api/app/projects", token, {
    name: "Siwa", tagline: "Solar cold rooms for market traders", website_url: "https://siwa.example.test", stage: "prototype",
    country: "Ghana", city: "Kumasi", sector: "Agriculture",
    problem: "Tomato and pepper traders in Kumasi lose up to 40 percent of their stock to heat before it sells.",
    traction: "Two pilot cold rooms at Kejetia market serve 38 traders.", women_led: true, amount_sought: "25000", currency: "USD",
  })
  const form = new FormData()
  form.append("file", new Blob([readFileSync(join(root, "e2e/site/cv.pdf"))], { type: "application/pdf" }), "Ama-Mensah-CV.pdf")
  form.append("kind", "cv")
  form.append("title", "Ama Mensah CV")
  form.append("is_default", "true")
  await call("POST", "/api/app/documents", token, form)
  results.steps.push("kit seeded")

  const profileDir = mkdtempSync(join(tmpdir(), "blesser-e2e-"))
  context = await chromium.launchPersistentContext(profileDir, {
    executablePath: chromiumPath(),
    headless: false,
    viewport: { width: 1100, height: 900 },
    args: ["--headless=new", `--disable-extensions-except=${DIST}`, `--load-extension=${DIST}`, "--no-first-run"],
  })
  context.on("page", (page) => page.on("pageerror", (err) => console.error(`[pageerror] ${page.url()}: ${err.message}`)))
  const worker = context.serviceWorkers()[0] ?? (await context.waitForEvent("serviceworker"))
  const extId = new URL(worker.url()).host
  results.extensionId = extId

  const popup = await context.newPage()
  popup.on("console", (m) => m.type() === "error" && console.error(`[popup] ${m.text()}`))
  await popup.setViewportSize({ width: 360, height: 520 })
  await popup.goto(`chrome-extension://${extId}/popup.html`)
  await popup.getByRole("button", { name: "Connect to Blesser" }).waitFor()
  await popup.screenshot({ path: join(OUT, "01-popup-signed-out.png") })

  const connectTab = context.waitForEvent("page")
  await popup.getByRole("button", { name: "Connect to Blesser" }).click()
  const app = await connectTab
  await app.waitForURL(/\/login\?next=/)
  await app.getByLabel("Email").fill(email)
  await app.getByLabel("Password").fill(password)
  await app.getByRole("button", { name: /sign in/i }).click()
  await app.waitForURL(/\/connect\/extension\?ext=/)
  await app.getByRole("button", { name: "Allow" }).waitFor()
  await app.screenshot({ path: join(OUT, "02-connect-page.png") })
  await app.getByRole("button", { name: "Allow" }).click()
  await app.getByText("Extension connected").waitFor()
  await app.screenshot({ path: join(OUT, "03-connected.png") })
  results.steps.push("connected through the app")

  const tabPage = await context.newPage()
  await tabPage.goto(`${SITE}/form.html`)
  await tabPage.frameLocator("iframe").locator("#city").waitFor()
  await tabPage.screenshot({ path: join(OUT, "04-form-before.png"), fullPage: true })
  const [tab] = await worker.evaluate((url) => chrome.tabs.query({ url }), `${SITE}/form.html`)

  const panel = await context.newPage()
  await panel.setViewportSize({ width: 360, height: 640 })
  await panel.goto(`chrome-extension://${extId}/popup.html?tab=${tab.id}`)
  await panel.getByRole("button", { name: "Fill this page" }).waitFor()
  await panel.getByLabel("Fill as").selectOption({ label: "Siwa" })
  if (process.env.E2E_DRAFTING === "0") await panel.getByRole("switch", { name: "Draft answers I haven't saved" }).click()
  await panel.screenshot({ path: join(OUT, "05-popup-ready.png") })
  const started = Date.now()
  await panel.getByRole("button", { name: "Fill this page" }).click()
  await panel.getByRole("region", { name: "Results" }).or(panel.getByRole("alert")).first().waitFor({ timeout: 90_000 })
  results.fillMs = Date.now() - started
  const alert = await panel.getByRole("alert").allTextContents()
  assert.equal(alert.length, 0, `Fill failed: ${alert.join(" ")}`)
  const left = panel.getByRole("button", { name: "Show what's left" })
  if (await left.count()) await left.click()
  await panel.screenshot({ path: join(OUT, "06-popup-results.png"), fullPage: true })
  await panel.emulateMedia({ colorScheme: "dark" })
  await panel.screenshot({ path: join(OUT, "06b-popup-results-dark.png"), fullPage: true })

  await tabPage.bringToFront()
  await tabPage.waitForTimeout(300)
  await tabPage.screenshot({ path: join(OUT, "07-form-after.png"), fullPage: true })
  const values = await tabPage.evaluate(() => {
    const v = (id) => document.getElementById(id)
    return {
      first: v("first").value, last: v("last").value, email: v("email").value, phone: v("phone").value,
      venture: v("venture").value, site: v("site").value, stage: v("stage").value, country: v("country").value,
      problem: v("problem").value, support: v("mentor").value, traction: v("traction").value, amount: v("amount").value,
      womenLed: document.querySelector('input[name="women_led"]:checked')?.value ?? null,
      cv: v("cv").files[0]?.name ?? null, card: v("card").value, title: document.title,
      drafted: document.querySelectorAll('[data-blesser-fill="drafted"]').length,
      filled: document.querySelectorAll('[data-blesser-fill="filled"]').length,
    }
  })
  values.frame = await tabPage.frameLocator("iframe").locator("body").evaluate(() => ({
    city: document.getElementById("city").value,
    linkedin: document.getElementById("linkedin").value,
  }))
  results.values = values
  results.summary = await panel.getByRole("region", { name: "Results" }).innerText()
  assert.equal(values.first, "Ama")
  assert.equal(values.venture, "Siwa")
  assert.equal(values.card, "", "card number must stay empty")
  assert.equal(values.cv, "Ama-Mensah-CV.pdf")
  assert.notEqual(values.title, "SUBMITTED", "the form must never be submitted")
  results.steps.push("filled")

  await app.goto(`${APP}/settings/account`)
  await app.getByRole("heading", { name: "Connected browsers" }).waitFor()
  await app.getByRole("button", { name: "Disconnect" }).first().waitFor()
  await app.getByRole("heading", { name: "Connected browsers" }).scrollIntoViewIfNeeded()
  await app.screenshot({ path: join(OUT, "08-settings-connected-browsers.png"), fullPage: true })
  results.steps.push("settings lists the browser")
} catch (err) {
  for (const [i, page] of (context?.pages() ?? []).entries()) await page.screenshot({ path: join(OUT, `fail-${i}.png`) }).catch(() => {})
  throw err
} finally {
  await context?.close().catch(() => {})
  site.close()
  await call("DELETE", "/api/app/auth/account", token, { password }).then(() => results.steps.push("account deleted"), (e) => results.steps.push(`delete failed: ${e.message}`))
  console.log(JSON.stringify(results, null, 2))
}
