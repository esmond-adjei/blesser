/** First letters of the first and last words, skipping bracketed
 * nicknames and punctuation: "Xiaojin (Jerry) Zhu" is XZ, not X(. */
export function initials(name: string): string {
  const words = name
    .replace(/\([^)]*\)/g, " ")
    .split(/\s+/)
    .map((w) => w.replace(/^[^\p{L}\p{N}]+/u, ""))
    .filter(Boolean)
  const picked = words.length > 1 ? [words[0], words[words.length - 1]] : words
  return picked.map((w) => w[0].toUpperCase()).join("")
}
