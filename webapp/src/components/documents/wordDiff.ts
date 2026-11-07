/** A word-level diff of a suggestion's before and after, so the panel can
 * show one passage with the change marked in place rather than two copies
 * to compare by eye. */
export type DiffPart = { kind: "same" | "del" | "ins"; text: string }

/** Words, the spaces between them and punctuation, each its own token,
 * so spacing survives and "MuJoCo," still matches "MuJoCo". */
const tokens = (s: string) => s.split(/(\s+|[,.;:!?()])/).filter(Boolean)

/** Past this many tokens on a side the table gets big; such a rewrite
 * reads better as before and after anyway. */
const MAX_TOKENS = 600

export function wordDiff(before: string, after: string): DiffPart[] | null {
  const a = tokens(before)
  const b = tokens(after)
  if (a.length > MAX_TOKENS || b.length > MAX_TOKENS) return null
  // Longest common subsequence, filled from the end so the walk below runs forwards.
  const w = b.length + 1
  const lcs = new Uint16Array((a.length + 1) * w)
  for (let i = a.length - 1; i >= 0; i--)
    for (let j = b.length - 1; j >= 0; j--)
      lcs[i * w + j] = a[i] === b[j] ? lcs[(i + 1) * w + j + 1] + 1 : Math.max(lcs[(i + 1) * w + j], lcs[i * w + j + 1])
  const parts: DiffPart[] = []
  const push = (kind: DiffPart["kind"], text: string) => {
    const last = parts[parts.length - 1]
    if (last?.kind === kind) last.text += text
    else parts.push({ kind, text })
  }
  let i = 0
  let j = 0
  while (i < a.length || j < b.length) {
    if (i < a.length && j < b.length && a[i] === b[j]) {
      push("same", a[i++])
      j++
    } else if (j < b.length && (i === a.length || lcs[i * w + j + 1] >= lcs[(i + 1) * w + j])) push("ins", b[j++])
    else push("del", a[i++])
  }
  // A space alone between two changes reads as part of them.
  for (let k = 1; k < parts.length - 1; k++)
    if (parts[k].kind === "same" && !parts[k].text.trim() && parts[k - 1].kind !== "same" && parts[k + 1].kind !== "same") {
      const space = parts[k].text
      parts.splice(k, 1, { kind: "del", text: space }, { kind: "ins", text: space })
    }
  return merge(parts)
}

/** Neighbouring deletions together, then insertions: "~~a b~~ __c d__"
 * rather than alternating word by word. */
function merge(parts: DiffPart[]): DiffPart[] {
  const out: DiffPart[] = []
  let del = ""
  let ins = ""
  const flush = () => {
    if (del) out.push({ kind: "del", text: del })
    if (ins) out.push({ kind: "ins", text: ins })
    del = ins = ""
  }
  for (const p of parts) {
    if (p.kind === "del") del += p.text
    else if (p.kind === "ins") ins += p.text
    else {
      flush()
      out.push(p)
    }
  }
  flush()
  return out
}

/** How much of the passage stays: below about a third, marking changes
 * in place is mostly noise and before-and-after reads better. */
export function kept(parts: DiffPart[]): number {
  let same = 0
  let all = 0
  for (const p of parts) {
    const n = p.text.trim().length
    all += n
    if (p.kind === "same") same += n
  }
  return all ? same / all : 1
}
