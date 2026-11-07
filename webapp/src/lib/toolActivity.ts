import {
  BookOpen, Building2, FilePenLine, FileSearch, Files, Globe, GraduationCap,
  ListFilter, Mail, Pause, Pencil, Play, Search, ShieldCheck, Square,
  Target, Trash2, UserRound, UsersRound, Wrench, type LucideIcon,
} from "lucide-react"
import type { TaskLogEvent } from "./types"

type ToolDescription = {
  name: string
  active: string
  done: string
  icon: LucideIcon
  parameters: string[]
}

const TOOLS: Record<string, ToolDescription> = {
  search_web: { name: "Search the web", active: "Searching the web", done: "Searched the web", icon: Search, parameters: ["query"] },
  fetch_page: { name: "Read a web page", active: "Reading page", done: "Read page", icon: Globe, parameters: ["url"] },
  find_openalex_author: { name: "Find an author", active: "Finding author", done: "Looked up author", icon: UserRound, parameters: ["name", "institution_hint"] },
  get_author_works: { name: "Read publications", active: "Reading publications", done: "Read publications", icon: BookOpen, parameters: ["openalex_id"] },
  score_alignment: { name: "Score research fit", active: "Scoring research fit", done: "Scored research fit", icon: Target, parameters: ["openalex_id", "interest_text"] },
  save_professor_record: { name: "Save a professor", active: "Saving professor", done: "Saved professor", icon: UserRound, parameters: ["name"] },
  jev_pick_author: { name: "Pick the right author", active: "Telling same-name authors apart", done: "Picked the author", icon: FileSearch, parameters: ["name"] },
  jev_rate_fit: { name: "Judge research fit", active: "Judging research fit", done: "Judged research fit", icon: Target, parameters: ["openalex_id"] },
  professor_index: { name: "Reuse saved research", active: "Checking saved research", done: "Reused saved research", icon: FileSearch, parameters: ["name", "openalex_id"] },
  save_program: { name: "Save a programme", active: "Saving programme", done: "Saved programme", icon: GraduationCap, parameters: ["program_name", "school_name"] },
  save_email_draft: { name: "Save an email draft", active: "Saving email draft", done: "Saved email draft", icon: Mail, parameters: ["subject"] },
  spawn_professor_research: { name: "Research professors", active: "Queueing professor research", done: "Queued professor research", icon: UsersRound, parameters: ["names"] },
  save_application: { name: "Save an application", active: "Saving application", done: "Saved application", icon: GraduationCap, parameters: ["program", "school"] },
  confirm_no_match: { name: "Record an unmatched professor", active: "Recording unmatched professor", done: "Recorded unmatched professor", icon: UserRound, parameters: ["reason"] },
  search: { name: "Search your records", active: "Searching your records", done: "Searched your records", icon: Search, parameters: ["query", "kinds"] },
  list_runs: { name: "List research runs", active: "Listing research runs", done: "Listed research runs", icon: Files, parameters: [] },
  get_run: { name: "Read a research run", active: "Reading research run", done: "Read research run", icon: FileSearch, parameters: ["run_id"] },
  list_candidates: { name: "List professor matches", active: "Listing professor matches", done: "Listed professor matches", icon: UsersRound, parameters: ["status", "run_id"] },
  get_candidate: { name: "Read a professor match", active: "Reading professor match", done: "Read professor match", icon: UserRound, parameters: ["candidate_id"] },
  list_programs: { name: "List programmes", active: "Listing programmes", done: "Listed programmes", icon: GraduationCap, parameters: ["run_id"] },
  list_tasks: { name: "List research tasks", active: "Listing research tasks", done: "Listed research tasks", icon: ListFilter, parameters: ["status", "run_id"] },
  list_applications: { name: "List applications", active: "Listing applications", done: "Listed applications", icon: GraduationCap, parameters: [] },
  get_application: { name: "Read an application", active: "Reading application", done: "Read application", icon: GraduationCap, parameters: ["application_id"] },
  list_drafts: { name: "List email drafts", active: "Listing email drafts", done: "Listed email drafts", icon: Mail, parameters: ["run_id"] },
  list_candidate_drafts: { name: "Find outreach drafts", active: "Finding outreach drafts", done: "Listed outreach drafts", icon: Mail, parameters: ["candidate_id"] },
  review_candidate: { name: "Review a professor match", active: "Reviewing professor match", done: "Reviewed professor match", icon: UserRound, parameters: ["candidate_id"] },
  update_application: { name: "Update an application", active: "Updating application", done: "Updated application", icon: Pencil, parameters: ["status", "deadline", "application_id"] },
  update_draft: { name: "Edit an email draft", active: "Updating email draft", done: "Updated email draft", icon: FilePenLine, parameters: ["subject", "draft_id"] },
  cv_list_documents: { name: "List your CVs", active: "Listing your CVs", done: "Listed your CVs", icon: Files, parameters: [] },
  cv_read: { name: "Read a CV", active: "Reading CV", done: "Read CV", icon: BookOpen, parameters: ["document_id", "version_id"] },
  cv_get_application_context: { name: "Read application context", active: "Reading application context", done: "Read application context", icon: GraduationCap, parameters: ["application_id"] },
  cv_suggest_changes: { name: "Suggest CV improvements", active: "Suggesting CV improvements", done: "Suggested CV improvements", icon: FilePenLine, parameters: ["document_id"] },
  cv_list_suggestions: { name: "Review CV suggestions", active: "Reviewing CV suggestions", done: "Reviewed CV suggestions", icon: FileSearch, parameters: ["status", "document_id"] },
  list_schools: { name: "List schools", active: "Listing schools", done: "Listed schools", icon: Building2, parameters: [] },
  get_school: { name: "Read a school", active: "Reading school", done: "Read school", icon: Building2, parameters: ["school_id"] },
  get_program: { name: "Read a programme", active: "Reading programme", done: "Read programme", icon: GraduationCap, parameters: ["program_id"] },
  get_professor: { name: "Read a professor profile", active: "Reading professor profile", done: "Read professor profile", icon: UserRound, parameters: ["professor_id"] },
  show_record: { name: "Show a record", active: "Opening record", done: "Showed record", icon: FileSearch, parameters: ["kind"] },
  create_run: { name: "Start a research run", active: "Starting research run", done: "Started research run", icon: Play, parameters: ["interest_statement", "region"] },
  update_run: { name: "Edit a research run", active: "Updating research run", done: "Updated research run", icon: Pencil, parameters: ["interest_statement", "run_id"] },
  set_run_status: { name: "Change run status", active: "Updating run status", done: "Updated run status", icon: Play, parameters: ["run_id"] },
  delete_run: { name: "Delete a research run", active: "Deleting research run", done: "Deleted research run", icon: Trash2, parameters: ["run_id"] },
  create_school: { name: "Add a school", active: "Adding school", done: "Added school", icon: Building2, parameters: ["name", "country"] },
  update_school: { name: "Edit a school", active: "Updating school", done: "Updated school", icon: Building2, parameters: ["name", "school_id"] },
  delete_school: { name: "Delete a school", active: "Deleting school", done: "Deleted school", icon: Trash2, parameters: ["school_id"] },
  create_program: { name: "Add a programme", active: "Adding programme", done: "Added programme", icon: GraduationCap, parameters: ["name"] },
  update_program: { name: "Edit a programme", active: "Updating programme", done: "Updated programme", icon: GraduationCap, parameters: ["name", "program_id"] },
  delete_program: { name: "Delete a programme", active: "Deleting programme", done: "Deleted programme", icon: Trash2, parameters: ["program_id"] },
  create_professor: { name: "Add a professor", active: "Adding professor", done: "Added professor", icon: UserRound, parameters: ["name"] },
  update_professor: { name: "Edit a professor", active: "Updating professor", done: "Updated professor", icon: UserRound, parameters: ["name", "professor_id"] },
  save_professor_papers: { name: "Save a professor's papers", active: "Saving papers", done: "Saved papers", icon: BookOpen, parameters: ["professor_id"] },
  delete_professor: { name: "Delete a professor", active: "Deleting professor", done: "Deleted professor", icon: Trash2, parameters: ["professor_id"] },
  update_candidate: { name: "Update a professor match", active: "Updating professor match", done: "Updated professor match", icon: UserRound, parameters: ["status", "candidate_id"] },
  delete_candidate: { name: "Delete a professor match", active: "Deleting professor match", done: "Deleted professor match", icon: Trash2, parameters: ["candidate_id"] },
  delete_draft: { name: "Discard an email draft", active: "Discarding email draft", done: "Discarded email draft", icon: Trash2, parameters: ["draft_id"] },
  create_application: { name: "Track an application", active: "Tracking application", done: "Tracked application", icon: GraduationCap, parameters: ["program", "school"] },
  delete_application: { name: "Delete an application", active: "Deleting application", done: "Deleted application", icon: Trash2, parameters: ["application_id"] },
  enable_changes: { name: "Request permission to make changes", active: "Requesting permission to make changes", done: "Requested permission to make changes", icon: ShieldCheck, parameters: [] },
}

const RUN_ACTIONS: Record<string, Pick<ToolDescription, "active" | "done" | "icon">> = {
  pause: { active: "Pausing research run", done: "Paused research run", icon: Pause },
  resume: { active: "Resuming research run", done: "Resumed research run", icon: Play },
  cancel: { active: "Cancelling research run", done: "Cancelled research run", icon: Square },
}

/** The operation name shown in settings, permissions and activity details. */
export function friendlyToolName(tool: string | null | undefined): string {
  return tool && Object.hasOwn(TOOLS, tool) ? TOOLS[tool].name : "Workspace action"
}

/** API messages and result previews may mention internal tool identifiers. */
export function friendlyToolText(text: string): string {
  return text.replace(/\b[a-z][a-z0-9]*(?:_[a-z0-9]+)+\b/g, (name) =>
    Object.hasOwn(TOOLS, name) ? TOOLS[name].name : name.replace(/_/g, " ").replace(/^./, (letter) => letter.toUpperCase()),
  )
}

export function friendlyToolData(value: unknown): string {
  return friendlyToolText(typeof value === "string" ? value : JSON.stringify(value, null, 2) ?? "")
}

function parameterText(value: unknown): string {
  if (typeof value === "string") return value.trim().replace(/\s+/g, " ")
  if (typeof value === "number") return String(value)
  if (Array.isArray(value)) {
    const names = value.filter((item): item is string => typeof item === "string" && !!item.trim())
    return names.slice(0, 3).map((name) => name.trim().replace(/\s+/g, " ")).join(", ") + (names.length > 3 ? ` +${names.length - 3} more` : "")
  }
  return ""
}

/** Descriptions use named parameters, never an arbitrary first value or an email body. */
export function toolActivity(event: Pick<TaskLogEvent, "tool" | "input" | "ok">) {
  const tool = event.tool ?? ""
  const input = new Map<string, unknown>(Object.entries(event.input ?? {}))
  const fallback = friendlyToolName(tool)
  const definition = (Object.hasOwn(TOOLS, tool) ? TOOLS[tool] : undefined) ?? { name: fallback, active: fallback, done: fallback, icon: Wrench, parameters: ["query", "name", "url", "subject"] }
  const action = tool === "set_run_status" ? RUN_ACTIONS[parameterText(input.get("action"))] : undefined
  let label = event.ok === true ? (action ?? definition).done : (action ?? definition).active
  if (tool === "review_candidate" && typeof input.get("approved") === "boolean") {
    label = input.get("approved")
      ? event.ok === true ? "Approved professor match" : "Approving professor match"
      : event.ok === true ? "Rejected professor match" : "Rejecting professor match"
  }
  const details = definition.parameters.map((key) => {
    const value = parameterText(input.get(key))
    if (!value) return ""
    if (key.endsWith("_id")) {
      const entity = key === "openalex_id" ? "Author" : key === "document_id" ? "CV" : key.replace(/_id$/, "").replace(/_/g, " ")
      return `${entity.charAt(0).toUpperCase() + entity.slice(1)} ${value}`
    }
    return value
  }).filter(Boolean)
  if (tool === "cv_suggest_changes") {
    const suggestions = input.get("suggestions")
    if (Array.isArray(suggestions)) details.unshift(`${suggestions.length} suggested change${suggestions.length === 1 ? "" : "s"}`)
  }
  return { label, detail: friendlyToolText(details.join(", ")), icon: action?.icon ?? definition.icon }
}
