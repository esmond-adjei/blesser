import { defineConfig } from "vitest/config";

export default defineConfig({
  esbuild: { jsx: "automatic" },
  test: {
    environment: "node",
    clearMocks: true,
    include: ["src/**/*.test.{ts,tsx}"],
  },
});
