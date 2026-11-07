/** GFM pipe-table syntax without the editor; the exports read the same syntax (api/cv/tables.py). */

export type Align = "left" | "center" | "right" | null
export type TableModel = { header: string[]; align: Align[]; rows: string[][] }

const DELIMITER_CELL = /^\s*:?-+:?\s*$/

/** A row's cells: split on unescaped pipes, outer pipes optional. */
export function splitRow(line: string): string[] {
  const cells: string[] = []
  let cell = ""
  for (let i = 0; i < line.length; i++) {
    const ch = line[i]
    if (ch === "\\" && line[i + 1] === "|") {
      cell += "\\|"
      i++
    } else if (ch === "|") {
      cells.push(cell)
      cell = ""
    } else {
      cell += ch
    }
  }
  cells.push(cell)
  if (/^\s*\|/.test(line)) cells.shift()
  if (/\|\s*$/.test(line.replace(/\\\|/g, ""))) cells.pop()
  return cells.map((c) => c.trim())
}

export function isDelimiterRow(line: string): boolean {
  const cells = splitRow(line)
  return cells.length > 0 && line.includes("-") && cells.every((c) => DELIMITER_CELL.test(c))
}

function alignOf(cell: string): Align {
  const c = cell.trim()
  const left = c.startsWith(":")
  const right = c.endsWith(":")
  return left && right ? "center" : right ? "right" : left ? "left" : null
}

export function parseTable(lines: string[]): TableModel {
  const header = splitRow(lines[0] ?? "")
  const align = splitRow(lines[1] ?? "").map(alignOf)
  const width = header.length
  const fit = (cells: string[]) => Array.from({ length: width }, (_, i) => cells[i] ?? "")
  return {
    header,
    align: Array.from({ length: width }, (_, i) => align[i] ?? null),
    rows: lines.slice(2).map((l) => fit(splitRow(l))),
  }
}

export function formatTable(t: TableModel): string[] {
  const width = t.header.length
  const widths = Array.from({ length: width }, (_, i) =>
    Math.max(3, t.header[i].length, ...t.rows.map((r) => (r[i] ?? "").length)),
  )
  const row = (cells: string[]) => `| ${cells.map((c, i) => (c ?? "").padEnd(widths[i])).join(" | ")} |`
  const rule = widths.map((w, i) => {
    const a = t.align[i]
    const dashes = "-".repeat(Math.max(1, w - (a === "center" ? 2 : a ? 1 : 0)))
    return a === "center" ? `:${dashes}:` : a === "right" ? `${dashes}:` : a === "left" ? `:${dashes}` : dashes
  })
  return [row(t.header), `| ${rule.join(" | ")} |`, ...t.rows.map(row)]
}
