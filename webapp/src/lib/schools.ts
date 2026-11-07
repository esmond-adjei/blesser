import type { School, SchoolTier } from "./types"

export const tierColors: Record<SchoolTier, string> = {
  top: "text-violet-700 dark:text-violet-300",
  strong: "text-blue-700 dark:text-blue-300",
  solid: "text-teal-700 dark:text-teal-300",
  accessible: "text-amber-800 dark:text-amber-300",
}

export function schoolFacultyCount(school: School): number {
  return school.programs.reduce((n, p) => n + p.professors, 0)
}
