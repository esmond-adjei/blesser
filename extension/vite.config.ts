import { readFileSync } from "node:fs"
import tailwindcss from "@tailwindcss/vite"
import react from "@vitejs/plugin-react"
import { defineConfig, type Plugin } from "vite"
import { buildManifest, readBuildEnv } from "./manifest.config.ts"

const env = readBuildEnv(process.env)
const outDir = process.env.BLESSER_OUT_DIR || "dist"
const { version } = JSON.parse(readFileSync(new URL("./package.json", import.meta.url), "utf8")) as { version: string }

function manifest(): Plugin {
  return {
    name: "blesser-manifest",
    generateBundle() {
      this.emitFile({ type: "asset", fileName: "manifest.json", source: JSON.stringify(buildManifest(env, version), null, 2) })
    },
  }
}

export default defineConfig({
  plugins: [react(), tailwindcss(), manifest()],
  define: {
    __DEFAULT_API_URL__: JSON.stringify(env.apiUrl),
    __DEFAULT_APP_URL__: JSON.stringify(env.appUrl),
    __APP_ORIGINS__: JSON.stringify(env.appOrigins),
    __TEST_BUILD__: JSON.stringify(env.testHosts.length > 0),
  },
  build: {
    outDir,
    emptyOutDir: true,
    target: "chrome116",
    rollupOptions: {
      input: {
        sidepanel: "sidepanel.html",
        options: "options.html",
        background: "src/background/index.ts",
      },
      output: {
        entryFileNames: (chunk) => (chunk.name === "background" ? "background.js" : "assets/[name]-[hash].js"),
      },
    },
  },
})
