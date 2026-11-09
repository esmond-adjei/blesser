import assert from "node:assert/strict";
import { mkdir, writeFile } from "node:fs/promises";

const origin = process.env.ADMIN_SMOKE_URL ?? "http://127.0.0.1:5174";
const debug = process.env.CHROME_DEBUG_URL ?? "http://127.0.0.1:9235";
const output = new URL("../../.agent-logs/", import.meta.url);
await mkdir(output, { recursive: true });
const targets = await (await fetch(`${debug}/json/list`)).json();
const target = targets.find((item) => item.type === "page");
assert(target, "Start Chrome with remote debugging on port 9235");
const ws = new WebSocket(target.webSocketDebuggerUrl);
await new Promise((resolve, reject) => {
  ws.onopen = resolve;
  ws.onerror = reject;
});
let sequence = 0;
const pending = new Map();
const errors = [];
const writes = [];
const now = "2026-11-09T12:00:00Z";
const staff = {
  id: "editor-1",
  email: "editor@example.test",
  display_name: "Editor",
  role: "editor",
  email_verified: true,
  disabled: false,
  created_at: now,
  scans_last_30_days: 0,
};
let sources = [
  {
    id: "source-1",
    url: "https://fund.example.org/feed",
    kind: "rss",
    category_hints: ["student"],
    enabled: true,
    proposed: false,
    last_crawled_at: now,
    next_crawl_at: now,
    crawl_requested: false,
    etag: "",
    last_modified: "",
    consecutive_failures: 0,
    last_error: "",
    candidates_found: 15,
    opportunities_saved: 4,
    last_candidates: 3,
    created_at: now,
  },
];
function send(method, params = {}) {
  return new Promise((resolve, reject) => {
    const id = ++sequence;
    pending.set(id, { resolve, reject });
    ws.send(JSON.stringify({ id, method, params }));
  });
}
async function respond({ requestId, request }) {
  const path = new URL(request.url).pathname.replace("/api/admin", "");
  const method = request.method;
  let result;
  let status = 200;
  if (path === "/auth/refresh")
    result = {
      user: staff,
      tokens: {
        access_token: "editor-access",
        refresh_token: "editor-refresh",
      },
    };
  else if (path === "/auth/me") result = staff;
  else if (path === "/sources" && method === "GET") result = sources;
  else if (path.startsWith("/sources")) {
    const body = JSON.parse(request.postData ?? "{}");
    const forbidden = Object.keys(body).filter(
      (key) => !["url", "kind", "category_hints", "enabled"].includes(key),
    );
    assert.equal(forbidden.length, 0, `Forbidden source fields: ${forbidden}`);
    writes.push({ path, method, body });
    const id = path.split("/")[2];
    if (method === "POST" && path.endsWith("/crawl")) {
      sources = sources.map((source) =>
        source.id === id ? { ...source, crawl_requested: true } : source,
      );
      result = sources.find((source) => source.id === id);
      status = 202;
    } else if (method === "POST") {
      result = { ...sources[0], ...body, id: "source-2" };
      sources = [...sources, result];
      status = 201;
    } else if (method === "PATCH") {
      sources = sources.map((source) =>
        source.id === id ? { ...source, ...body } : source,
      );
      result = sources.find((source) => source.id === id);
    } else if (method === "DELETE") {
      sources = sources.filter((source) => source.id !== id);
      status = 204;
    }
  } else throw new Error(`Unexpected endpoint ${method} ${path}`);
  await send("Fetch.fulfillRequest", {
    requestId,
    responseCode: status,
    responseHeaders: [{ name: "content-type", value: "application/json" }],
    body: Buffer.from(status === 204 ? "" : JSON.stringify(result)).toString(
      "base64",
    ),
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
    void respond(message.params).catch((error) => errors.push(String(error)));
  else if (message.method === "Runtime.exceptionThrown")
    errors.push(message.params.exceptionDetails.text);
};
async function evaluate(expression) {
  const result = await send("Runtime.evaluate", {
    expression,
    returnByValue: true,
    awaitPromise: true,
  });
  if (result.exceptionDetails) throw new Error(result.exceptionDetails.text);
  return result.result.value;
}
async function until(expression) {
  for (let i = 0; i < 100; i++) {
    if (await evaluate(expression)) return;
    if (errors.length) throw new Error(errors.join("\n"));
    await new Promise((resolve) => setTimeout(resolve, 50));
  }
  throw new Error(
    `Timed out: ${expression}\n${await evaluate("document.body.innerText")}`,
  );
}
async function click(label, scope = "document") {
  assert(
    await evaluate(
      `(() => { const element = [...${scope}.querySelectorAll('button')].find(element => element.textContent.trim() === ${JSON.stringify(label)} && !element.disabled); if (!element) return false; element.click(); return true; })()`,
    ),
    `Button ${label}`,
  );
}
async function fill(value) {
  await evaluate(
    `(() => { const element = document.querySelector('form input[type=url]'); Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(element, ${JSON.stringify(value)}); element.dispatchEvent(new Event('input', { bubbles: true })); })()`,
  );
}
try {
  await send("Page.enable");
  await send("Runtime.enable");
  await send("Page.addScriptToEvaluateOnNewDocument", {
    source:
      "localStorage.setItem('blesser.admin.refresh_token','editor-refresh'); window.confirm=()=>true;",
  });
  await send("Emulation.setDeviceMetricsOverride", {
    width: 1440,
    height: 1000,
    deviceScaleFactor: 1,
    mobile: false,
  });
  await send("Fetch.enable", {
    patterns: [
      { urlPattern: `${origin}/api/admin/*`, requestStage: "Request" },
    ],
  });
  await send("Page.navigate", { url: `${origin}/sources` });
  await until(
    "document.querySelector('tbody')?.innerText.includes('15 candidates')",
  );
  await click("Edit");
  await until("!!document.querySelector('form')");
  await fill("https://fund.example.org/updated");
  await click("Save source");
  await until(
    "!document.querySelector('form') && document.querySelector('tbody').innerText.includes('/updated')",
  );
  assert.equal(writes.at(-1).body.url, "https://fund.example.org/updated");
  await click("Disable");
  await until("document.querySelector('tbody').innerText.includes('Disabled')");
  await click("Enable");
  await until("document.querySelector('tbody').innerText.includes('Enabled')");
  await click("Crawl now");
  await until(
    "document.querySelector('tbody').innerText.includes('Crawl queued')",
  );
  await click("Add source");
  await fill("https://new.example.org/calls");
  await click("Save source");
  await until("document.querySelectorAll('tbody tr').length === 2");
  await click("Delete", "document.querySelector('tbody tr:last-child')");
  await until("document.querySelectorAll('tbody tr').length === 1");
  const shot = await send("Page.captureScreenshot", { format: "png" });
  await writeFile(
    new URL("sources-browser.png", output),
    Buffer.from(shot.data, "base64"),
  );
  assert.deepEqual(errors, []);
  await writeFile(
    new URL("sources-browser.json", output),
    JSON.stringify(
      {
        passed: [
          "editor access",
          "yield display",
          "edit with allowed fields",
          "disable",
          "enable",
          "crawl now",
          "create",
          "delete",
        ],
        writes,
      },
      null,
      2,
    ),
  );
  console.log("Sources browser checks passed");
} finally {
  ws.close();
}
