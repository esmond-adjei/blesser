export interface BuildEnv {
  apiUrl: string
  appUrl: string
  appOrigins: string[]
  testHosts: string[]
}

const list = (raw: string | undefined) => (raw ?? "").split(",").map((s) => s.trim()).filter(Boolean)

export function readBuildEnv(env: Record<string, string | undefined>): BuildEnv {
  const appUrl = (env.BLESSER_APP_URL || "http://localhost:5173").replace(/\/+$/, "")
  const apiUrl = (env.BLESSER_API_URL || "http://localhost:8000").replace(/\/+$/, "")
  const origins = new Set([new URL(appUrl).origin, ...list(env.BLESSER_APP_ORIGINS).map((o) => new URL(o).origin)])
  return { apiUrl, appUrl, appOrigins: [...origins], testHosts: list(env.BLESSER_E2E_HOSTS) }
}

export function buildManifest(env: BuildEnv, version: string) {
  return {
    manifest_version: 3,
    name: "Blesser: Apply with your kit",
    short_name: "Blesser",
    description: "Fill application forms from your Blesser profile, projects and documents. You review and submit.",
    version,
    minimum_chrome_version: "116",
    icons: { 16: "icons/16.png", 32: "icons/32.png", 48: "icons/48.png", 128: "icons/128.png" },
    action: {
      default_title: "Open Blesser",
      default_icon: { 16: "icons/16.png", 32: "icons/32.png" },
    },
    side_panel: { default_path: "sidepanel.html" },
    options_page: "options.html",
    background: { service_worker: "background.js", type: "module" },
    permissions: ["activeTab", "scripting", "storage", "sidePanel"],
    // Test builds only: stands in for the toolbar click that grants activeTab, which automation can't press.
    ...(env.testHosts.length ? { host_permissions: env.testHosts } : {}),
    externally_connectable: { matches: env.appOrigins.map((o) => `${o}/*`) },
  }
}
