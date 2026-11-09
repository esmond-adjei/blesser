import assert from "node:assert/strict";
import { mkdir, writeFile } from "node:fs/promises";

const app = process.env.ADMIN_SMOKE_URL ?? "http://127.0.0.1:5174";
const debug = process.env.CHROME_DEBUG_URL ?? "http://127.0.0.1:9234";
const output = new URL("../.agent-logs/", import.meta.url);
await mkdir(output, { recursive: true });
const targets = await (await fetch(`${debug}/json/list`)).json();
const target = targets.find((item) => item.type === "page");
assert(target, "Start Chrome with --headless=new --remote-debugging-port=9234");
const ws = new WebSocket(target.webSocketDebuggerUrl);
await new Promise((resolve, reject) => {
  ws.onopen = resolve;
  ws.onerror = reject;
});
let serial = 0;
const pending = new Map();
const errors = [];
const requests = [];
const passed = [];
function send(method, params = {}) {
  return new Promise((resolve, reject) => {
    const id = ++serial;
    pending.set(id, { resolve, reject });
    ws.send(JSON.stringify({ id, method, params }));
  });
}
const now = "2026-11-09T12:00:00Z";
let currentRole = "admin";
const person = {
  id: "admin-1",
  email: "admin@example.test",
  display_name: "Ama Mensah",
  role: "admin",
  email_verified: true,
  disabled: false,
  created_at: now,
  scans_last_30_days: 3,
};
const editor = {
  ...person,
  id: "editor-1",
  email: "editor@example.test",
  display_name: "Kwame Owusu",
  role: "editor",
};
const audit = {
  id: "audit-1",
  actor_id: person.id,
  actor_email: person.email,
  action: "opportunity.update",
  entity_type: "opportunity",
  entity_id: "opp-1",
  before: { status: "draft", title: "Climate fund" },
  after: { status: "in_review", title: "Climate venture grant" },
  at: now,
};
const opportunity = {
  id: "opp-1",
  slug: "climate-venture-grant",
  title: "Climate venture grant",
  organization: "Green Futures Foundation",
  category: "startup",
  kind: "grant",
  summary: "Funding and mentoring for early stage climate ventures in Ghana.",
  eligibility: "Ghana-based teams with an operating prototype.",
  benefits: "Up to GHS 50,000 and six months of mentoring.",
  location: "Accra, Ghana",
  countries: ["Ghana"],
  requirements: ["Company profile", "Project budget"],
  tags: ["climate", "early stage"],
  deadline: "30 November 2026",
  deadline_date: "2026-11-30",
  rolling: false,
  link: "https://example.test/apply",
  source_url: "https://example.test/grants",
  verified_at: now,
  published_at: null,
  is_open: true,
  days_left: 21,
  closed: false,
  audience: "members",
  found_by: "community",
  created_at: now,
  is_new: true,
  status: "in_review",
  review_reason: "new_submission",
  editor_note: "Confirm the eligibility wording before publishing.",
  featured_rank: null,
  source: "community",
  scan_id: null,
  created_by: person.id,
  published_by: null,
  updated_at: now,
  dedupe_key: "climate-fund",
};
let opportunities = [
  opportunity,
  {
    ...opportunity,
    id: "opp-2",
    slug: "research-fellowship",
    title: "West Africa research fellowship",
    category: "research",
    kind: "fellowship",
    found_by: "agent",
    source: "agent",
    status: "published",
    review_reason: "agent_find",
  },
  {
    ...opportunity,
    id: "opp-3",
    slug: "student-scholarship",
    title: "Graduate study scholarship",
    category: "student",
    kind: "scholarship",
    audience: "public",
    source: "staff",
    found_by: "staff",
    status: "published",
    featured_rank: 0,
    review_reason: null,
  },
];
let collections = [
  {
    id: "collection-1",
    slug: "for-students",
    title: "For students",
    intro: "Study opportunities for your next step.",
    audience: "public",
    filter: null,
    item_ids: ["opp-3"],
    position: 0,
    published: true,
  },
];
let site = {
  hero_title: "Your next opportunity is out there",
  hero_subtitle: "Find funding, fellowships and more in Ghana.",
  announcement: null,
};
let settings = {
  agent_default: { status: "published", audience: "members" },
  community_default: { status: "in_review" },
  auto_archive: true,
  member_scan_limits: { per_hour: 3, per_day: 10 },
  sweep_hours: 24,
};
let reports = [
  {
    id: "report-1",
    opportunity_id: "opp-1",
    reason: "The source lists an updated eligibility requirement.",
    email: null,
    resolved: false,
    created_at: now,
  },
];
let scans = [
  {
    id: "scan-1",
    region: "Ghana",
    categories: ["startup"],
    focus: "Climate funding",
    status: "done",
    created_at: now,
    opportunities_added: 3,
    owner_email: person.email,
    tasks: [
      {
        id: "task-1",
        task_type: "discovery",
        target: "Climate grants",
        status: "done",
        error: null,
        final_text: "Verified three official sources.",
        log: [{ turn: 1, note: "Checked the official source", at: now }],
      },
    ],
  },
];
async function respond(event) {
  const url = new URL(event.request.url);
  const path = url.pathname.replace("/api/admin", "");
  const method = event.request.method;
  const body = event.request.postData
    ? JSON.parse(event.request.postData)
    : undefined;
  requests.push({ method, path, body });
  let result;
  let status = 200;
  const user = { ...person, role: currentRole };
  if (path === "/auth/login")
    result = {
      access_token: "fixture-admin-access",
      refresh_token: "fixture-admin-refresh",
      user,
    };
  else if (path === "/auth/refresh")
    result = {
      user,
      tokens: {
        access_token: "fixture-admin-access",
        refresh_token: "fixture-admin-refresh",
      },
    };
  else if (path === "/auth/me") result = user;
  else if (path === "/auth/logout") result = { status: "ok" };
  else if (path === "/opportunities/counts")
    result = {
      in_review: opportunities.filter((o) => o.status === "in_review").length,
      members_only: 1,
      published_public: 1,
      archived: 0,
      hidden: opportunities.filter((o) => o.status === "hidden").length,
      draft: 0,
    };
  else if (path === "/opportunities/bulk") {
    opportunities = opportunities.map((o) =>
      body.ids.includes(o.id)
        ? {
            ...o,
            status:
              body.action === "hide"
                ? "hidden"
                : body.action === "archive"
                  ? "archived"
                  : body.action === "to_review"
                    ? "in_review"
                    : "published",
            audience:
              body.action === "publish_public"
                ? "public"
                : body.action === "publish_members"
                  ? "members"
                  : o.audience,
          }
        : o,
    );
    result = { updated: body.ids.length };
  } else if (path === "/opportunities" && method === "GET") {
    let items = opportunities.filter(
      (o) =>
        ["status", "audience", "category", "kind", "source"].every(
          (key) =>
            !url.searchParams.get(key) || o[key] === url.searchParams.get(key),
        ) &&
        (!url.searchParams.get("q") ||
          `${o.title} ${o.organization}`
            .toLowerCase()
            .includes(url.searchParams.get("q").toLowerCase())),
    );
    const total = items.length;
    items = items.slice(
      Number(url.searchParams.get("offset") || 0),
      Number(url.searchParams.get("offset") || 0) +
        Number(url.searchParams.get("limit") || 30),
    );
    result = { items, total };
  } else if (path === "/opportunities" && method === "POST") {
    const item = {
      ...opportunity,
      ...body,
      id: "opp-new",
      source: "staff",
      found_by: "staff",
    };
    opportunities.push(item);
    result = item;
  } else if (/^\/opportunities\/[^/]+\/reverify$/.test(path))
    result = { scan_id: "scan-new" };
  else if (/^\/opportunities\/[^/]+\/merge$/.test(path)) {
    opportunities = opportunities.map((o) =>
      o.id === path.split("/")[2] ? { ...o, status: "hidden" } : o,
    );
    result = opportunities.find((o) => o.id === body.into_id);
  } else if (/^\/opportunities\/[^/]+$/.test(path)) {
    const id = path.split("/")[2];
    if (method === "PATCH")
      opportunities = opportunities.map((o) =>
        o.id === id ? { ...o, ...body } : o,
      );
    result = {
      ...opportunities.find((o) => o.id === id),
      history: [audit],
      trace_excerpt:
        "Official source excerpt: applications are open to registered ventures in Ghana. The deadline is 30 November 2026.",
    };
  } else if (path === "/collections") {
    if (method === "POST") {
      const item = { ...body, id: "collection-new" };
      collections.push(item);
      result = item;
    } else result = collections;
  } else if (path.startsWith("/collections/")) {
    const id = path.split("/")[2];
    if (method === "DELETE") {
      collections = collections.filter((c) => c.id !== id);
      result = { deleted: true };
    } else {
      collections = collections.map((c) =>
        c.id === id ? { ...c, ...body } : c,
      );
      result = collections.find((c) => c.id === id);
    }
  } else if (path === "/site") {
    if (method === "PUT") site = body;
    result = site;
  } else if (path === "/settings") {
    if (method === "PUT") settings = body;
    result = settings;
  } else if (path === "/reports") result = reports;
  else if (path.startsWith("/reports/")) {
    reports = reports.map((r) =>
      r.id === path.split("/")[2] ? { ...r, resolved: true } : r,
    );
    result = reports.find((r) => r.id === path.split("/")[2]);
  } else if (path === "/scans") {
    if (method === "POST") {
      const scan = { ...scans[0], ...body, id: "scan-new", status: "running" };
      scans.unshift(scan);
      result = scan;
    } else result = scans;
  } else if (path === "/users") result = { items: [person, editor], total: 2 };
  else if (path.startsWith("/users/")) {
    status = 409;
    result = {
      detail: "Cannot demote the last admin. Assign another admin first.",
    };
  } else if (path === "/audit") result = { items: [audit], total: 1 };
  else {
    status = 404;
    result = { detail: `Unexpected fixture route: ${method} ${path}` };
    errors.push(result.detail);
  }
  await send("Fetch.fulfillRequest", {
    requestId: event.requestId,
    responseCode: status,
    responseHeaders: [{ name: "Content-Type", value: "application/json" }],
    body: Buffer.from(JSON.stringify(result)).toString("base64"),
  });
}
ws.onmessage = ({ data }) => {
  const message = JSON.parse(data);
  if (message.id) {
    const promise = pending.get(message.id);
    pending.delete(message.id);
    if (message.error) promise?.reject(new Error(message.error.message));
    else promise?.resolve(message.result);
  } else if (message.method === "Fetch.requestPaused")
    void respond(message.params).catch((error) => errors.push(error.message));
  else if (message.method === "Runtime.exceptionThrown")
    errors.push(
      message.params.exceptionDetails.exception?.description ??
        message.params.exceptionDetails.text,
    );
};
const evaluate = async (expression) => {
  const result = await send("Runtime.evaluate", {
    expression,
    returnByValue: true,
    awaitPromise: true,
  });
  if (result.exceptionDetails)
    throw new Error(
      result.exceptionDetails.exception?.description ??
        result.exceptionDetails.text,
    );
  return result.result.value;
};
const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
async function until(expression, name) {
  for (let i = 0; i < 100; i++) {
    if (await evaluate(`!!(${expression})`)) return;
    await delay(50);
  }
  throw new Error(
    `Timed out: ${name}\n${await evaluate("document.body.innerText")}`,
  );
}
async function click(text, scope = "document") {
  const clicked = await evaluate(
    `(() => { const root = ${scope}; const el = [...root.querySelectorAll('button,a')].find(el => el.textContent.trim() === ${JSON.stringify(text)} && !el.disabled); if (!el) return false; el.click(); return true; })()`,
  );
  assert(clicked, `Could not click ${text}`);
}
async function fill(label, value) {
  await evaluate(
    `(() => { const label = [...document.querySelectorAll('label')].find(el => el.textContent.trim() === ${JSON.stringify(label)}); if (!label) throw Error('Missing label'); const el = document.getElementById(label.htmlFor); const setter = Object.getOwnPropertyDescriptor(el.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype, 'value').set; setter.call(el, ${JSON.stringify(value)}); el.dispatchEvent(new Event('input', { bubbles: true })); })()`,
  );
}
async function select(label, value) {
  await evaluate(
    `(() => { const label = [...document.querySelectorAll('label')].find(el => el.textContent.trim() === ${JSON.stringify(label)}); const el = document.getElementById(label.htmlFor); el.value = ${JSON.stringify(value)}; el.dispatchEvent(new Event('change', { bubbles: true })); })()`,
  );
}
async function screenshot(name) {
  const { data } = await send("Page.captureScreenshot", {
    format: "png",
    captureBeyondViewport: false,
  });
  await writeFile(new URL(`${name}.png`, output), Buffer.from(data, "base64"));
}
async function navigate(path) {
  await send("Page.navigate", { url: app + path });
}
async function closePanel() {
  await evaluate(
    `document.querySelector('dialog [aria-label="Close panel"]').click()`,
  );
  await until("!document.querySelector('dialog')", "panel closed");
}
function pass(name) {
  passed.push(name);
  console.log(`PASS ${name}`);
}
try {
  await send("Page.enable");
  await send("Runtime.enable");
  await send("Emulation.setDeviceMetricsOverride", {
    width: 1440,
    height: 1000,
    deviceScaleFactor: 1,
    mobile: false,
  });
  await send("Fetch.enable", {
    patterns: [{ urlPattern: `${app}/api/admin/*`, requestStage: "Request" }],
  });
  await navigate("/sign-in");
  await until("document.readyState === 'complete'", "initial load");
  await evaluate("localStorage.removeItem('blesser.admin.refresh_token')");
  await navigate("/people");
  await until(
    "document.querySelector('input[type=email]')",
    "sign-in redirect",
  );
  assert.equal(await evaluate("location.pathname"), "/sign-in");
  await screenshot("sign-in");
  await fill("Email address", "admin@example.test");
  await fill("Password", "fixture-password");
  await click("Sign in");
  await until(
    "document.querySelector('h1')?.textContent === 'People'",
    "admin sign-in",
  );
  pass("Sign-in and return to protected destination");
  await click("Review queue");
  await until(
    "document.querySelector('.table-title')?.textContent.includes('Climate')",
    "review queue",
  );
  await screenshot("review-queue");
  await click("Climate venture grant");
  await until(
    "document.querySelector('dialog .source-excerpt')?.textContent.includes('Official source')",
    "agent source excerpt",
  );
  await screenshot("review-details");
  const beforeHide = requests.filter((r) => r.method === "PATCH").length;
  await send("Input.dispatchKeyEvent", {
    type: "keyDown",
    key: "h",
    code: "KeyH",
    text: "h",
  });
  await until(
    "document.querySelector('.confirmation')?.textContent.includes('Hide this opportunity')",
    "hide keyboard confirmation",
  );
  assert.equal(requests.filter((r) => r.method === "PATCH").length, beforeHide);
  await click("Cancel", "document.querySelector('dialog')");
  await click("Approve to public", "document.querySelector('dialog')");
  await until(
    "document.querySelector('dialog .detail-heading')?.textContent.includes('Published')",
    "publish action",
  );
  assert.equal(opportunities[0].audience, "public");
  pass("Review source, keyboard hide confirmation, and approve public");
  await click("Edit", "document.querySelector('dialog')");
  await until("document.querySelector('.preview')", "editor preview");
  await fill("Title", "Climate venture grant, checked");
  await until(
    "document.querySelector('.preview h3')?.textContent === 'Climate venture grant, checked'",
    "live card preview",
  );
  await screenshot("opportunity-editor");
  await click("Save opportunity");
  await until(
    "document.querySelector('dialog .detail-heading h2')?.textContent === 'Climate venture grant, checked'",
    "saved opportunity",
  );
  pass("Editor save and live shared-component preview");
  await closePanel();
  await click("Opportunities");
  await until(
    "document.querySelectorAll('tbody tr').length === 3",
    "opportunities table",
  );
  await evaluate("document.querySelector('thead input').click()");
  await select("Bulk action", "hide").catch(async () => {
    await evaluate(
      "(() => { const el = document.querySelector('select[aria-label=\"Bulk action\"]'); el.value = 'hide'; el.dispatchEvent(new Event('change',{bubbles:true})); })()",
    );
  });
  await click("Apply action");
  await until(
    "document.querySelector('.confirmation')?.textContent.includes('Hide 3 opportunities')",
    "bulk hide confirm",
  );
  assert(!requests.some((r) => r.path === "/opportunities/bulk"));
  await click("Cancel");
  await click("Clear selection");
  pass("Opportunity table and bulk hide confirmation");
  await click("Create opportunity");
  await until("document.querySelector('dialog input')", "new opportunity form");
  for (const [label, value] of [
    ["Title", "New staff opportunity"],
    ["Slug", "new-staff-opportunity"],
    ["Organization", "Ghana Research Network"],
    ["Application link", "https://example.test/new"],
    ["Source link", "https://example.test/source"],
  ])
    await fill(label, value);
  await click("Create opportunity", "document.querySelector('dialog')");
  await until(
    "document.querySelector('dialog .detail-heading h2')?.textContent === 'New staff opportunity'",
    "opportunity created",
  );
  assert.equal(
    opportunities.find((item) => item.id === "opp-new").status,
    "draft",
  );
  await closePanel();
  pass("Staff opportunity creation with draft default");
  await click("Curation");
  await until(
    "document.querySelector('h1')?.textContent === 'Curation'",
    "curation",
  );
  await until(
    "document.body.innerText.includes('For students')",
    "collections",
  );
  await click("Edit");
  await until("document.querySelector('dialog')", "collection editor");
  await fill("Title", "For students and graduates");
  await click("Save collection");
  await until("!document.querySelector('dialog')", "collection saved");
  assert.equal(collections[0].title, "For students and graduates");
  await click("Homepage content");
  await until("document.querySelector('.homepage-form')", "homepage content");
  await fill("Hero title", "Find your next step");
  await click("Save homepage");
  await until(
    "document.body.innerText.includes('Homepage saved')",
    "homepage saved",
  );
  assert.equal(site.hero_title, "Find your next step");
  await screenshot("curation-homepage");
  await click("Featured order");
  await until("document.querySelector('.ordered-row')", "featured order");
  await click("Add Climate venture grant, checked");
  await click("Save featured order");
  await until(
    "document.body.innerText.includes('Featured order saved')",
    "featured order saved",
  );
  assert.equal(
    opportunities.find((item) => item.id === "opp-1").featured_rank,
    1,
  );
  await click("Collections");
  await click("Create collection");
  await until("document.querySelector('dialog')", "new collection");
  await fill("Title", "Climate funding");
  await fill("Slug", "climate-funding");
  await select("Choose opportunities", "filter");
  await fill("Saved filter", '{"category":"startup","kind":"grant"}');
  await click("Save collection");
  await until("!document.querySelector('dialog')", "filter collection saved");
  assert.deepEqual(
    collections.find((item) => item.id === "collection-new").filter,
    { category: "startup", kind: "grant" },
  );
  await click("Climate funding");
  await until("document.querySelector('dialog')", "saved collection editor");
  await click("Delete collection");
  await until(
    "document.querySelector('.confirmation')",
    "collection delete confirmation",
  );
  assert(collections.some((item) => item.id === "collection-new"));
  await click("Delete collection", "document.querySelector('.confirmation')");
  await until("!document.querySelector('dialog')", "collection deleted");
  assert(!collections.some((item) => item.id === "collection-new"));
  pass("Collection editing, homepage content, and featured ordering");
  await click("Scans");
  await until(
    "document.querySelector('tbody')?.textContent.includes('admin@example.test')",
    "scan owners",
  );
  await click("View trace");
  await until(
    "document.querySelector('dialog')?.textContent.includes('Verified three official sources')",
    "scan trace",
  );
  await closePanel();
  await click("Start a scan");
  await until("document.querySelector('dialog')", "start scan panel");
  await click("Start scan");
  await until("!document.querySelector('dialog')", "scan started");
  assert.equal(scans[0].id, "scan-new");
  pass("Scan owners, trace, and start action");
  await click("Reports");
  await until(
    "document.querySelector('tbody')?.textContent.includes('updated eligibility')",
    "reports",
  );
  await click("Resolve report");
  await until(
    "document.body.innerText.includes('Report resolved')",
    "report resolved",
  );
  assert(reports[0].resolved);
  pass("Reports list and resolution");
  await click("People");
  await until(
    "document.querySelector('select[aria-label=\"Role for editor@example.test\"]')",
    "people roles",
  );
  await evaluate(
    "(() => { const el = document.querySelector('select[aria-label=\"Role for editor@example.test\"]'); el.value = 'admin'; el.dispatchEvent(new Event('change', {bubbles:true})); })()",
  );
  await until("document.querySelector('.confirmation')", "role confirmation");
  assert(!requests.some((r) => r.path === "/users/editor-1"));
  await click("Change role");
  await until(
    "document.querySelector('.confirmation')?.textContent.includes('Cannot demote the last admin')",
    "last-admin error",
  );
  await screenshot("people-last-admin-error");
  await click("Cancel");
  await click("Disable account");
  await until(
    "document.querySelector('.confirmation')?.textContent.includes('active sessions')",
    "disable confirmation",
  );
  await click("Cancel");
  pass("Role and disable confirmation, verbatim last-admin error");
  await click("Audit log");
  await until(
    "document.querySelector('tbody')?.textContent.includes('opportunity.update')",
    "audit log",
  );
  await click("View changes");
  await until("document.querySelector('.diff-changed pre')", "audit diff");
  await screenshot("audit-diff");
  await closePanel();
  pass("Filterable audit table and before/after JSON diff");
  await click("Settings");
  await until("document.querySelector('.settings-form')", "settings");
  await fill("Hours between sweeps", "12");
  await click("Save settings");
  await until(
    "document.body.innerText.includes('Settings saved')",
    "settings saved",
  );
  assert.equal(settings.sweep_hours, 12);
  pass("Settings round trip");
  currentRole = "editor";
  await navigate("/people");
  await until(
    "document.body.innerText.includes('An admin role is required')",
    "editor direct route guard",
  );
  assert.equal(
    await evaluate(
      "[...document.querySelectorAll('nav a')].some(el => el.getAttribute('href') === '/people')",
    ),
    false,
  );
  assert.equal(
    await evaluate(
      "[...document.querySelectorAll('nav a')].some(el => el.getAttribute('href') === '/audit')",
    ),
    false,
  );
  await screenshot("editor-role-guard");
  pass("Editor navigation and direct URL guard");
  await navigate("/review?queue=agent");
  await until(
    "document.querySelector('tbody')?.textContent.includes('West Africa')",
    "agent queue",
  );
  await send("Emulation.setEmulatedMedia", {
    features: [{ name: "prefers-color-scheme", value: "dark" }],
  });
  await screenshot("review-dark");
  assert.equal(await evaluate("document.title"), "Blesser Admin");
  assert(
    await evaluate(
      "document.querySelector('link[rel=icon]').href.startsWith('data:image/svg+xml') || document.querySelector('link[rel=icon]').href.includes('blesser-mark')",
    ),
  );
  assert.equal(
    await evaluate("document.documentElement.scrollWidth > innerWidth"),
    false,
  );
  pass("Dark theme, shared favicon, and desktop overflow check");
  await send("Input.dispatchKeyEvent", {
    type: "keyDown",
    key: "j",
    code: "KeyJ",
    text: "j",
  });
  await until(
    "document.querySelector('dialog .detail-heading h2')?.textContent.includes('West Africa')",
    "keyboard next item",
  );
  await send("Input.dispatchKeyEvent", {
    type: "keyDown",
    key: "m",
    code: "KeyM",
    text: "m",
  });
  await until(
    "document.querySelector('dialog .detail-heading')?.textContent.includes('Members only')",
    "keyboard members approval",
  );
  await until(
    "document.querySelector('dialog .actions button')?.disabled === false && document.body.innerText.includes('Opportunity updated')",
    "approval settled",
  );
  await send("Input.dispatchKeyEvent", {
    type: "keyDown",
    key: "e",
    code: "KeyE",
    text: "e",
  });
  await until("document.querySelector('.preview')", "keyboard edit");
  const checksBefore = requests.filter((request) =>
    request.path.endsWith("/reverify"),
  ).length;
  await click("Re-verify source");
  await until(
    "document.querySelector('.confirmation')",
    "verification confirmation",
  );
  assert.equal(
    requests.filter((request) => request.path.endsWith("/reverify")).length,
    checksBefore,
  );
  await click("Queue verification");
  await until(
    "!document.querySelector('.confirmation')",
    "verification queued",
  );
  assert.equal(
    requests.filter((request) => request.path.endsWith("/reverify")).length,
    checksBefore + 1,
  );
  await fill("Find a duplicate to keep", "Climate");
  await until(
    "document.querySelector('input[name=merge-target]')",
    "merge candidates",
  );
  await evaluate("document.querySelector('input[name=merge-target]').click()");
  await click("Merge duplicate");
  await until(
    "document.querySelector('.confirmation')?.textContent.includes('Keep')",
    "merge confirmation",
  );
  assert(!requests.some((request) => request.path.endsWith("/merge")));
  await click("Merge opportunities");
  await until(
    "document.querySelector('dialog .detail-heading h2')?.textContent === 'Climate venture grant, checked'",
    "merged into target",
  );
  assert.equal(
    opportunities.find((item) => item.id === "opp-2").status,
    "hidden",
  );
  await closePanel();
  pass(
    "Keyboard movement, members approval, edit, re-verification, and merge confirmations",
  );
  assert.deepEqual(errors, []);
  await writeFile(
    new URL("browser-smoke.json", output),
    JSON.stringify(
      {
        mode: "contract fixtures intercepted in Chrome, no live backend",
        passed,
        requests,
        errors,
      },
      null,
      2,
    ),
  );
  console.log(
    `${passed.length} browser smoke checks passed with contract fixtures.`,
  );
} catch (error) {
  await screenshot("failure");
  await writeFile(
    new URL("browser-smoke-failure.json", output),
    JSON.stringify({ message: error.message, errors, requests }, null, 2),
  );
  throw error;
} finally {
  ws.close();
}
