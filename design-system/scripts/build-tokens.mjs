import { readFileSync, writeFileSync } from "node:fs"

const root = new URL("../", import.meta.url)
const tokens = JSON.parse(readFileSync(new URL("tokens.json", root), "utf8"))
const header = "/* Generated from tokens.json by scripts/build-tokens.mjs (npm run tokens). Do not edit. */\n"

// Self-hosted fontsource families register under their own names; list them first.
const SELF_HOSTED = {
  display: '"Bricolage Grotesque Variable", ',
  sans: '"Figtree Variable", ',
  mono: "",
}
const families = Object.fromEntries(
  Object.entries(tokens.type.families).map(([key, value]) => [key, SELF_HOSTED[key] + value]),
)

const block = (selector, lines) => `${selector} {\n${lines.map((l) => `  ${l}`).join("\n")}\n}\n`
const themed = (theme) => [
  `color-scheme: ${theme};`,
  ...tokens.color.tokens.map((t) => `--${t.name}: ${t.value[theme]};`),
  ...tokens.shadow.tokens.map((t) => `--${t.name}: ${t.value[theme]};`),
]
const fixed = [
  ...tokens.spacing.tokens.map((t) => `--${t.name}: ${t.value};`),
  ...tokens.radius.tokens.map((t) => `--${t.name}: ${t.value};`),
  ...tokens.size.tokens.map((t) => `--${t.name}: ${t.value};`),
  ...Object.entries(families).map(([key, value]) => `--font-${key}: ${value};`),
]

const tokensCss =
  header +
  "\n" +
  block(":root", themed("light")) +
  "\n" +
  block('.dark,\n[data-theme="dark"]', themed("dark")) +
  "\n" +
  block(":root", fixed)

const styles = tokens.type.groups.flatMap((g) => g.styles.map((s) => ({ ...s, family: g.family })))
const radius = (name) => tokens.radius.tokens.find((t) => t.name === name).value

const theme = [
  header,
  '@source "./components";',
  "",
  '@custom-variant dark (&:where(.dark, .dark *, [data-theme="dark"], [data-theme="dark"] *));',
  "",
  block("@theme inline", [
    ...tokens.color.tokens.map((t) => `--color-${t.name}: var(--${t.name});`),
    ...tokens.shadow.tokens.map((t) => `--shadow-${t.name}: var(--${t.name});`),
    "--shadow-xs: var(--elevation-1);",
    "--shadow-sm: var(--elevation-1);",
    "--shadow-md: var(--elevation-2);",
    "--shadow-lg: var(--elevation-2);",
    "--shadow-xl: var(--elevation-3);",
    "--shadow-2xl: var(--elevation-3);",
    ...tokens.size.tokens
      .filter((t) => t.name.startsWith("control-"))
      .map((t) => `--spacing-${t.name}: var(--${t.name});`),
    "--container-content: var(--content-max);",
    "--container-reading: var(--reading-max);",
  ]),
  // Same names as tokens.css with the same literal values, so neither side refers to itself.
  block("@theme", [
    ...Object.entries(families).map(([key, value]) => `--font-${key}: ${value};`),
    `--radius-sm: ${radius("radius-sm")};`,
    `--radius-md: ${radius("radius-md")};`,
    `--radius-lg: ${radius("radius-lg")};`,
    `--radius-xl: ${radius("radius-xl")};`,
    ...styles.flatMap((s) => [
      `--text-${s.name}: ${s.fontSize};`,
      `--text-${s.name}--line-height: ${s.lineHeight};`,
      `--text-${s.name}--font-weight: ${s.fontWeight};`,
      ...(s.letterSpacing ? [`--text-${s.name}--letter-spacing: ${s.letterSpacing};`] : []),
    ]),
  ]),
  block("@keyframes blesser-bloom-fill", ["from { transform: scaleX(0); }", "to { transform: scaleX(1); }"]),
  ...styles.map((s) =>
    block(`@utility type-${s.name}`, [
      `font-family: var(--font-${s.family});`,
      `font-size: ${s.fontSize};`,
      `line-height: ${s.lineHeight};`,
      `font-weight: ${s.fontWeight};`,
      `letter-spacing: ${s.letterSpacing ?? "normal"};`,
      ...(s.family === "display" ? ["text-wrap: balance;"] : []),
      ...(s.name === "numeral" ? ["font-variant-numeric: tabular-nums;"] : []),
    ]),
  ),
  `@layer base {
  html {
    -webkit-font-smoothing: antialiased;
    -moz-osx-font-smoothing: grayscale;
  }

  body {
    background: var(--canvas);
    color: var(--ink);
    font: 400 16px/24px var(--font-sans);
  }

  :where(h1, h2, h3, h4) {
    text-wrap: balance;
  }

  ::selection {
    background: var(--sun-soft);
    color: var(--ink);
  }

  :focus-visible {
    outline: 2px solid var(--focus);
    outline-offset: 2px;
  }

  @media (prefers-reduced-motion: reduce) {
    *, ::before, ::after {
      transition-duration: 0ms !important;
      animation-duration: 0ms !important;
    }
  }
}
`,
].join("\n")

writeFileSync(new URL("src/tokens.css", root), tokensCss)
writeFileSync(new URL("src/theme.css", root), theme)
console.log("Wrote src/tokens.css and src/theme.css")
