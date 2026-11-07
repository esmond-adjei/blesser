/** Canonical agent task types (mirrors TASK_HANDLERS on the backend). */
const TASK_TYPES = [
  "discover_programs",
  "research_professor",
  "research_one_professor",
  "draft_email",
  "discover_opportunities",
] as const

export type TaskTypeFilter = (typeof TASK_TYPES)[number]

export const TASK_TYPE_TAB_LABELS: Record<TaskTypeFilter, string> = {
  discover_programs: "School agents",
  research_professor: "Faculty agents",
  research_one_professor: "Professor agents",
  draft_email: "Email agents",
  discover_opportunities: "Opportunity agents",
}
