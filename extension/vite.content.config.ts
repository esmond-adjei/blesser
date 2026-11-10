import { defineConfig } from "vite"

// The content script is injected with chrome.scripting as a classic script, so it ships as one IIFE.
export default defineConfig({
  publicDir: false,
  build: {
    outDir: process.env.BLESSER_OUT_DIR || "dist",
    emptyOutDir: false,
    target: "chrome116",
    lib: { entry: "src/content/index.ts", formats: ["iife"], name: "BlesserContent", fileName: () => "content.js" },
  },
})
