// End-to-end: builds a test copy of the extension, connects it through the member app, then works the side panel against fixture forms.
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
const PROXY_PORT = Number(process.env.E2E_PROXY_PORT ?? 5191)
const SITE = `http://localhost:${SITE_PORT}`
const PROXY = `http://localhost:${PROXY_PORT}`
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
const V2 = process.env.E2E_MOCK_V2 !== "1" && ["/api/app/autofill/feedback", "/api/app/autofill/reports", "/api/app/autofill/corrections"].every((p) => openapi.paths[p])

// The extension talks to the API through this proxy, which records feedback and reports, and answers them itself when the API has no such routes yet.
const recorded = { feedback: [], reports: [] }
const proxy = createServer(async (req, res) => {
  const chunks = []
  for await (const chunk of req) chunks.push(chunk)
  const body = Buffer.concat(chunks)
  const path = (req.url ?? "/").split("?")[0]
  const kind = req.method === "POST" && path === "/api/app/autofill/feedback" ? "feedback" : req.method === "POST" && path === "/api/app/autofill/reports" ? "reports" : null
  if (kind) recorded[kind].push(JSON.parse(body.toString() || "null"))
  if (kind && !V2) return res.writeHead(204, { "Access-Control-Allow-Origin": req.headers.origin ?? "*" }).end()
  const headers = Object.fromEntries(Object.entries(req.headers).filter(([k]) => !["host", "connection", "content-length"].includes(k)))
  try {
    const upstream = await fetch(`${API}${req.url}`, { method: req.method, headers, body: ["GET", "HEAD"].includes(req.method) ? undefined : body })
    const out = Object.fromEntries([...upstream.headers].filter(([k]) => !["content-encoding", "content-length", "transfer-encoding", "connection"].includes(k)))
    const payload = Buffer.from(await upstream.arrayBuffer())
    if (kind && !upstream.ok) {
      recorded.failures = [...(recorded.failures ?? []), `${path} ${upstream.status} ${payload.toString().slice(0, 500)}`]
      console.error(`[proxy] ${path} -> ${upstream.status} ${payload.toString().slice(0, 500)}\n${body.toString().slice(0, 1500)}`)
    }
    res.writeHead(upstream.status, out).end(payload)
  } catch (err) {
    res.writeHead(502).end(String(err))
  }
})
await new Promise((resolve) => proxy.listen(PROXY_PORT, "127.0.0.1", resolve))

const env = { ...process.env, BLESSER_API_URL: PROXY, BLESSER_APP_URL: APP, BLESSER_E2E_HOSTS: `${SITE}/*`, BLESSER_OUT_DIR: DIST }
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
const results = { email, backend: V2 ? "real v2 routes" : "feedback and reports mocked by the e2e proxy", steps: [] }
async function shot(page, name, full = false) {
  if (!full) return page.screenshot({ path: join(OUT, name) })
  // Sized to the content rather than fullPage, which crops a page laid out with a scrollbar.
  const size = page.viewportSize()
  await page.setViewportSize({ width: size.width, height: await page.evaluate(() => document.documentElement.scrollHeight) })
  await page.screenshot({ path: join(OUT, name) })
  await page.setViewportSize(size)
}
let context
try {
  await call("PUT", "/api/app/profile", token, {
    given_name: "Ama", family_name: "Mensah", pronouns: "she/her", email: "ama.mensah@example.com", phone: "+233 24 555 0101",
    city: "Kumasi", country_of_residence: "Ghana", nationality: "Ghanaian", gender: "Male", linkedin_url: "https://www.linkedin.com/in/ama-mensah-e2e",
    education: [{ institution: "Kwame Nkrumah University of Science and Technology", qualification: "BSc", field: "Agricultural Engineering", start: null, end: null, grade: "", country: "Ghana" }],
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

  const manifest = await worker.evaluate(() => chrome.runtime.getManifest())
  assert.equal(manifest.side_panel?.default_path, "sidepanel.html")
  assert(!manifest.action.default_popup, "the toolbar button must open the side panel, not a popup")
  assert(manifest.permissions.includes("sidePanel"))
  const behavior = await worker.evaluate(async () => {
    for (let i = 0; i < 20; i++) {
      const b = await chrome.sidePanel.getPanelBehavior()
      if (b.openPanelOnActionClick) return b
      await new Promise((r) => setTimeout(r, 100))
    }
    return chrome.sidePanel.getPanelBehavior()
  })
  assert.equal(behavior.openPanelOnActionClick, true)
  results.steps.push("toolbar click opens the side panel")

  // Automation can't open Chrome's side panel, so the panel page runs in a tab bound to the form's tab with ?tab= (test builds only).
  const panel = await context.newPage()
  panel.on("console", (m) => m.type() === "error" && console.error(`[panel] ${m.text()}`))
  await panel.setViewportSize({ width: 360, height: 760 })
  await panel.goto(`chrome-extension://${extId}/sidepanel.html`)
  await panel.getByRole("button", { name: "Connect to Blesser" }).waitFor()
  await shot(panel, "01-panel-signed-out.png")

  const connectTab = context.waitForEvent("page")
  await panel.getByRole("button", { name: "Connect to Blesser" }).click()
  const app = await connectTab
  await app.waitForURL(/\/login\?next=/)
  await app.getByLabel("Email").fill(email)
  await app.getByLabel("Password", { exact: true }).fill(password)
  await app.getByRole("button", { name: /sign in/i }).click()
  await app.waitForURL(/\/connect\/extension\?ext=/)
  await app.getByRole("button", { name: "Allow" }).click()
  await app.getByText("Extension connected").waitFor()
  results.steps.push("connected through the app")

  const tabPage = await context.newPage()
  await tabPage.goto(`${SITE}/form.html`)
  await tabPage.frameLocator("iframe").locator("#city").waitFor()
  const [tab] = await worker.evaluate((url) => chrome.tabs.query({ url }), `${SITE}/form.html`)

  await panel.goto(`chrome-extension://${extId}/sidepanel.html?tab=${tab.id}`)
  await panel.bringToFront()
  await panel.getByRole("button", { name: "Fill this page" }).waitFor()
  await panel.getByRole("combobox").first().selectOption({ label: "Siwa" })
  if (process.env.E2E_DRAFTING === "0") await panel.getByRole("switch", { name: "Draft answers I haven't saved" }).click()
  await shot(panel, "02-panel-ready-light.png")
  await panel.emulateMedia({ colorScheme: "dark" })
  await shot(panel, "03-panel-ready-dark.png")
  await panel.emulateMedia({ colorScheme: "light" })

  const started = Date.now()
  await panel.getByRole("button", { name: "Fill this page" }).click()
  await panel.getByRole("region", { name: "Review" }).or(panel.getByRole("alert")).first().waitFor({ timeout: 90_000 })
  results.fillMs = Date.now() - started
  const alert = await panel.getByRole("alert").allTextContents()
  assert.equal(alert.length, 0, `Fill failed: ${alert.join(" ")}`)
  await shot(panel, "04-review-list-light.png", true)
  await panel.emulateMedia({ colorScheme: "dark" })
  await shot(panel, "05-review-list-dark.png", true)
  await panel.emulateMedia({ colorScheme: "light" })

  const values = await tabPage.evaluate(() => {
    const v = (id) => document.getElementById(id)
    return {
      first: v("first").value, last: v("last").value, phone: v("phone").value, venture: v("venture").value,
      cv: v("cv").files[0]?.name ?? null, card: v("card").value, title: document.title,
    }
  })
  results.values = values
  assert.equal(values.first, "Ama")
  assert.equal(values.venture, "Siwa")
  assert.equal(values.card, "", "card number must stay empty")
  assert.equal(values.cv, "Ama-Mensah-CV.pdf")
  assert.notEqual(values.title, "SUBMITTED", "the form must never be submitted")
  results.steps.push("filled")

  const row = (label) => panel.getByRole("region", { name: "Review" }).locator("li").filter({ has: panel.getByText(label, { exact: true }) })

  await row("First name").getByRole("button", { name: "Actions for First name" }).click()
  await panel.getByRole("menuitem", { name: "Edit" }).click()
  const editor = row("First name").getByRole("form", { name: "Edit First name" })
  await editor.getByRole("textbox").fill("Ama Serwaa")
  await shot(panel, "06-edit-in-place.png")
  await editor.getByRole("button", { name: "Save to page" }).click()
  await row("First name").getByText("Your change, remembered for this site").waitFor()
  assert.equal(await tabPage.locator("#first").inputValue(), "Ama Serwaa")
  assert.deepEqual(await row("First name").getByRole("alert").allTextContents(), [])
  const edit = recorded.feedback.at(-1)
  assert.deepEqual(edit.corrected, { value: "Ama Serwaa" })
  assert.equal(edit.filled.value, "Ama")
  assert.equal(edit.field.label, "First name")
  assert.equal(edit.page.host, "localhost")
  results.steps.push("edit in place wrote to the page and sent feedback")

  await row("Phone").getByRole("button", { name: "Actions for Phone" }).click()
  await panel.getByRole("menuitem", { name: "Wrong field" }).click()
  await row("Phone").getByText(/Marked as the wrong field/).waitFor()
  assert.equal(await tabPage.locator("#phone").inputValue(), "")
  assert.deepEqual(recorded.feedback.at(-1).corrected, { wrong_field: true })
  assert.deepEqual(await row("Phone").getByRole("alert").allTextContents(), [])
  results.steps.push("wrong field cleared the page and sent feedback")

  await tabPage.bringToFront()
  await tabPage.locator("#last").fill("Mensah-Owusu")
  await tabPage.locator("#last").blur()
  await panel.bringToFront()
  const remember = row("Last name").getByRole("button", { name: "Remember this correction" })
  await remember.waitFor({ timeout: 10_000 })
  await shot(panel, "07-page-edit-noticed.png")
  await remember.click()
  await row("Last name").getByText("Your change, remembered for this site").waitFor()
  assert.deepEqual(recorded.feedback.at(-1).corrected, { value: "Mensah-Owusu" })
  results.steps.push("noticed a page edit and remembered it")

  await tabPage.evaluate(() => {
    const row = document.createElement("div")
    row.className = "row"
    row.innerHTML = '<label for="birthplace">Place of birth</label><input id="birthplace" name="place_of_birth" type="text">'
    document.querySelector("#apply").insertBefore(row, document.querySelector("#apply button"))
  })
  await panel.getByRole("button", { name: "Fill this step" }).waitFor({ timeout: 10_000 })
  await shot(panel, "08-new-step-noticed.png")
  results.steps.push("noticed a new form step")

  await panel.getByRole("button", { name: "Account actions" }).click()
  await panel.getByRole("menuitem", { name: "Report a problem" }).click()
  const dialog = panel.getByRole("dialog", { name: "Report a problem" })
  await dialog.getByRole("button", { name: /See what's sent/ }).click()
  await dialog.getByLabel("What went wrong?").fill("Phone went into the wrong field.")
  await shot(panel, "09-report-dialog.png")
  await dialog.getByRole("button", { name: "Send report" }).click()
  await panel.getByText("Thanks. Your report was sent.").waitFor()
  const report = recorded.reports.at(-1)
  assert.equal(report.note, "Phone went into the wrong field.")
  assert(report.fields.length >= 10, "the report carries the page's field descriptors")
  const reportText = JSON.stringify(report)
  for (const secret of ["Ama Serwaa", "Mensah-Owusu", "ama.mensah@example.com", "+233"]) assert(!reportText.includes(secret), `report leaked a value: ${secret}`)
  assert(report.fields.every((f) => !("value" in f)))
  results.steps.push("report sent descriptors only")

  await tabPage.goto(`${SITE}/step2.html`)
  await panel.bringToFront()
  await panel.getByText("You're on a new page or step.").waitFor({ timeout: 10_000 })
  await panel.getByRole("button", { name: "Fill this step" }).click()
  await panel.getByText("You're on a new page or step.").waitFor({ state: "detached", timeout: 90_000 })
  assert.equal(await tabPage.locator("#s2email").inputValue(), "ama.mensah@example.com")
  results.steps.push("followed navigation to step 2 and filled it")

  await tabPage.goto(`${SITE}/v2.html`)
  await panel.getByText("You're on a new page or step.").waitFor({ timeout: 10_000 })
  await panel.getByRole("combobox").first().selectOption({ label: "Me" })
  await panel.getByRole("button", { name: "Fill this step" }).click()
  await panel.getByText("You're on a new page or step.").waitFor({ state: "detached", timeout: 90_000 })
  await panel.getByRole("region", { name: "Review" }).waitFor()
  const owner = await tabPage.evaluate(() => {
    const v = (id) => document.getElementById(id)
    const label = (id) => v(id).selectedOptions[0]?.textContent ?? ""
    return { first: v("fname").value, gender: label("gender"), countryOfBirth: label("cob"), countryOfBirthText: v("cob_text").value, institution: v("inst").value, institutionCountry: label("inst_country") }
  })
  results.ownerCases = owner
  results.ownerRows = await panel.getByRole("region", { name: "Review" }).innerText()
  await shot(panel, "10-owner-cases-review.png", true)
  await tabPage.bringToFront()
  await shot(tabPage, "11-owner-cases-form.png", true)
  if (V2) {
    assert.equal(owner.gender, "Man", "Male must pick Man")
    assert.equal(owner.countryOfBirth, "Ghana", "Ghanaian must give Ghana as country of birth")
    if (owner.countryOfBirthText !== "Ghana") results.matcherGaps = [`"Country of birth (as on your passport)" text field got "${owner.countryOfBirthText}"`]
    assert.equal(owner.institutionCountry, "Ghana", "Country of institution takes the education entry's country")
    assert.notEqual(owner.institution, "", "Name of institution is filled")
    assert.equal(owner.first, "Ama Serwaa", "the earlier correction for First name on this site applies")
    results.steps.push("owner failure cases pass against the real backend")
  } else results.steps.push("owner failure cases recorded only: the API has no v2 routes yet")

  if (!V2) {
    const corrections = recorded.feedback.map((f, i) => ({
      id: `c${i}`, host: f.page.host, label: f.field.label, field_type: f.field.type,
      value: "value" in f.corrected ? f.corrected.value : null, wrong_field: "wrong_field" in f.corrected, updated_at: new Date(Date.now() - i * 60_000).toISOString(),
    }))
    await app.route("**/api/app/autofill/corrections**", (route) =>
      route.request().method() === "DELETE" ? route.fulfill({ status: 204 }) : route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(corrections) }),
    )
  }
  await app.bringToFront()
  await app.setViewportSize({ width: 1100, height: 760 })
  await app.goto(`${APP}/kit/corrections`)
  await app.getByRole("heading", { name: "localhost" }).waitFor()
  await app.getByText("Mensah-Owusu").waitFor()
  await shot(app, "12-webapp-corrections.png", true)
  await app.emulateMedia({ colorScheme: "dark" })
  await shot(app, "13-webapp-corrections-dark.png", true)
  await app.emulateMedia({ colorScheme: "light" })
  const before = await app.getByRole("button", { name: /^Forget the correction/ }).count()
  await app.getByRole("button", { name: /^Forget the correction for Last name/ }).click()
  await app.getByText("Mensah-Owusu").waitFor({ state: "detached" })
  assert.equal(await app.getByRole("button", { name: /^Forget the correction/ }).count(), before - 1)
  results.steps.push("corrections listed and deleted in the Apply kit")

  await app.goto(`${APP}/kit/profile`)
  await app.getByLabel("Country of birth").waitFor()
  await app.getByLabel("Place of birth").fill("Kumasi")
  await app.locator("#kit-identity").scrollIntoViewIfNeeded()
  await app.waitForTimeout(1500)
  await shot(app, "14-webapp-profile-birth.png")
  const saved = await call("GET", "/api/app/profile", token)
  if ("place_of_birth" in saved) assert.equal(saved.place_of_birth, "Kumasi")
  results.steps.push("Apply kit has country and place of birth")
} catch (err) {
  for (const [i, page] of (context?.pages() ?? []).entries()) await page.screenshot({ path: join(OUT, `fail-${i}.png`) }).catch(() => {})
  throw err
} finally {
  await context?.close().catch(() => {})
  site.close()
  proxy.close()
  results.feedbackSent = recorded.feedback.length
  results.reportsSent = recorded.reports.length
  await call("DELETE", "/api/app/auth/account", token, { password }).then(() => results.steps.push("account deleted"), (e) => results.steps.push(`delete failed: ${e.message}`))
  console.log(JSON.stringify(results, null, 2))
}
