import type { FormProgress } from "./types"

export interface ProgressCount {
  total: number
  filled: number
  required: number
  requiredFilled: number
  sections: { name: string; total: number; filled: number }[]
}

/** Totals across frames, with sections in page order (frame 0 first). */
export function countProgress(progress: Pick<FormProgress, "frames">): ProgressCount {
  const frames = Object.keys(progress.frames).sort((a, b) => Number(a) - Number(b))
  const out: ProgressCount = { total: 0, filled: 0, required: 0, requiredFilled: 0, sections: [] }
  const sections = new Map<string, { name: string; total: number; filled: number }>()
  for (const frame of frames) {
    for (const field of progress.frames[frame]) {
      out.total++
      if (field.filled) out.filled++
      if (field.required) {
        out.required++
        if (field.filled) out.requiredFilled++
      }
      const name = field.section.trim()
      const section = sections.get(name) ?? { name, total: 0, filled: 0 }
      section.total++
      if (field.filled) section.filled++
      if (!sections.has(name)) {
        sections.set(name, section)
        out.sections.push(section)
      }
    }
  }
  return out
}
