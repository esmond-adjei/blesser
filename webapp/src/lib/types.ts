import type { CitationSource } from "./citations"
/** API shapes mirroring the FastAPI backend (app/*\/schemas.py). */

export interface Run {
  id: string
  region: string
  field: string
  degree_level: string
  status: string
  interest_statement: string
  created_at: string
  /** When a done or cancelled run stopped; null while live (run detail only). */
  finished_at?: string | null
  elapsed_seconds: number | null
  updated_at?: string | null
  max_programs: number | null
  max_professors: number | null
  max_professors_per_program: number | null
  tasks: Record<string, number>
  candidates: number
  /** Custom flow; null = built-in Standard. */
  flow_id?: string | null
  /** Selectivity tiers discovery targets; empty = no preference. */
  school_tiers?: SchoolTier[]
  /** The run's model: "system" = Auto, else a configured provider. Null on older runs. */
  llm_provider?: string | null
  agent_states?: Record<string, AgentState>
}

export type AgentState = "paused" | "cancelled"

export type SchoolTier = "top" | "strong" | "solid" | "accessible"

export interface RunListItem extends Run {
  tasks: Record<string, number>
  candidates: number
}

export interface CreateRunRequest {
  region: string
  field: string
  degree_level: string
  interest_statement: string
  interest_document_id?: string | null
  max_programs?: number | null
  max_professors?: number | null
  max_professors_per_program?: number | null
  flow_id?: string | null
  school_tiers?: SchoolTier[]
  /** "default", "system" or a configured provider. */
  llm_provider?: string | null
}

export interface RunUpdate {
  interest_statement?: string
  max_programs?: number | null
  max_professors?: number | null
  max_professors_per_program?: number | null
  /** Switches the model for the run's remaining work; "default" resets. */
  llm_provider?: string | null
}

export interface ProgramSeed {
  school_name: string
  school_country?: string | null
  program_name: string
  department_url?: string | null
}

export interface DeletePreview {
  schools: number
  programs: number
  professors: number
  papers: number
  candidates: number
  drafts: number
  tasks: number
  tool_calls: number
}

export interface ToolStat {
  calls: number
  errors: number
}

export interface GateCount {
  gate: string
  label: string
  count: number
}

/** `GET /runs/{id}/refusals`: why researched professors weren't saved. */
export interface Refusals {
  researched: number
  saved: number
  not_saved: GateCount[]
  refusals: GateCount[]
  /** Scores computed by word overlap only (no embedding model). */
  lexical_scores?: number
}

export interface ModelUsage {
  provider: string | null
  model: string | null
  tasks: number
  input_tokens: number
  output_tokens: number
}

export interface Usage {
  input_tokens: number
  output_tokens: number
  turns: number
  tasks: Record<string, number>
  tools: Record<string, ToolStat>
  cache_read_tokens?: number
  model_seconds?: number
  tool_seconds?: number
  models?: ModelUsage[]
  candidates?: number
  tokens_per_candidate?: number | null
  /** From the run's creation to its first saved candidate. */
  first_candidate_seconds?: number | null
  active_seconds?: number
  /** Professor tasks by route: no_match / likely (code-first), agent, skipped. */
  narrow_paths?: Record<string, number>
  /** Why "agent" professor tasks skipped or left the code-first pass. */
  narrow_fallbacks?: Record<string, number>
}

export interface Worker {
  worker_id: string
  concurrency: number
  started_at: string | null
  last_seen_at: string | null
  lag_seconds: number | null
  alive: boolean
}

export interface CreateRunFromListRequest {
  degree_level: string
  interest_statement: string
  interest_document_id?: string | null
  programs: ProgramSeed[]
  max_programs?: number | null
  max_professors?: number | null
  max_professors_per_program?: number | null
  flow_id?: string | null
  llm_provider?: string | null
}

export interface TaskLogEvent {
  sources?: CitationSource[]
  turn: number
  /** Model text for the turn (in `note`), sent before its tools run; absent on tool-call entries. */
  kind?: "turn"
  tool?: string
  input?: object
  result_preview?: string
  ok?: boolean
  note?: string
  /** What a thinking model reasoned before `note` (Gradis turns). */
  thought?: string
  /** When the worker recorded it (UTC ISO). */
  at?: string
  tokens?: number
}

export interface Task {
  id: string
  task_type: string
  target_id: string | null
  target_name: string | null
  status: string
  error: string | null
  turns: number | null
  final_text: string | null
  log: TaskLogEvent[] | null
  input_tokens: number | null
  output_tokens: number | null
  started_at: string | null
  finished_at: string | null
  duration_seconds: number | null
  updated_at?: string | null
}

/** One slim board card from GET /runs/{id}/board (no trace/log payloads). */
export interface BoardTask {
  id: string
  task_type: string
  target_name: string | null
  status: string
  turns: number | null
  error: string | null
  updated_at?: string | null
}

/** `trace` frame: `from` is the index of the first event, so 0 replaces the trace and a higher value appends. */
export interface TraceDelta {
  id: string
  from: number
  total: number
  events: TaskLogEvent[]
}

export type Board = Record<string, BoardTask[]>

export interface ProgramOut {
  id: string
  name: string
  department_url: string | null
  professors: number
}

export interface School {
  id: string
  name: string
  country: string | null
  website_url: string | null
  image_url?: string | null
  /** Tier discovery placed it in; null without tiers. */
  tier?: SchoolTier | null
  /** Runs that use this school, oldest first (account listing only). */
  run_ids?: string[]
  programs: ProgramOut[]
}

export interface ProfessorOut {
  id: string
  name: string
  openalex_id: string | null
  profile_url: string | null
  lab_name: string | null
  photo_url: string | null
  papers: number
}

export interface ProgramDetail {
  id: string
  name: string
  department_url: string | null
  school_id: string
  school_name: string
  professors: ProfessorOut[]
}

export interface FacultyRow {
  id: string
  name: string
  program_id: string
  program: string
  school_id: string
  school: string
  lab_name: string | null
  photo_url: string | null
  papers: number
  candidate_id: string | null
  /** The school's faculty view adds the best candidate's details. */
  candidate_status?: string | null
  similarity_score?: number | null
  candidate_run_id?: string | null
  /** The professors catalog adds these for its cards. */
  bio?: string | null
  school_image_url?: string | null
}

/** A professor scored against a run's interests by hand. */
export interface ProfessorMatch {
  score: number
  band: "strong" | "moderate" | "weak" | "unrelated" | "no_overlap"
  /** The paper closest to the interests. */
  paper: string | null
  /** Set once saved as a match. */
  candidate_id: string | null
  /** The run a save lands in; null when no run uses the document. */
  run_id: string | null
  /** The breakdown: closest papers with their own scores, the start of
   * the interests, and how many papers were scored. */
  top_papers: { title: string; year: number | null; abstract?: string | null; url?: string | null; score: number }[]
  interest: string
  papers_scored: number
  /** Jev's judgment of the fit, when switched on: `level` 0-4 from
   * unrelated to direct, `label` the nearest level. */
  fit: { level: number; label: string; score: number; confidence: number } | null
}

export interface ProfessorCreate {
  name: string
  profile_url?: string | null
  email?: string | null
  openalex_id?: string | null
}

export interface Paper {
  /** Unset for papers an index entry holds without a saved row. */
  id?: string | null
  title: string
  abstract: string | null
  year: number | null
  url: string | null
  /** Cited-by count from OpenAlex; null when the source doesn't say. */
  citations?: number | null
  publication_type?: string | null
  /** In byline order. */
  coauthors?: { name: string; openalex_id: string | null }[]
}

export interface ProfessorDetail {
  id: string
  name: string
  profile_url: string | null
  email: string | null
  openalex_id: string | null
  lab_name: string | null
  bio: string | null
  bio_source: string | null
  photo_url: string | null
  socials: Array<{ label: string; url: string }>
  program_id: string
  program_name: string
  school_name: string
  candidate_id: string | null
  papers: Paper[]
}

export interface Candidate {
  id: string
  run_id: string
  professor_id: string
  program_id: string
  school_id: string
  professor_name: string
  school_name: string
  program_name: string
  /** Pictures for rows and cards; null when none was found. */
  professor_photo_url?: string | null
  school_image_url?: string | null
  similarity_score: number | null
  rationale: string | null
  status: string
  draft_id: string | null
  draft_subject: string | null
  draft_body: string | null
  draft_created_at: string | null
  draft_count: number
}

export interface ProfessorMatchRef {
  id: string
  run_id: string
  similarity_score: number | null
  status: string
  interest: string | null
}

export interface CandidateDetail extends Candidate {
  interest?: string | null
  /** Every match for this professor, this one included, best first. */
  matches?: ProfessorMatchRef[]
  papers: Paper[]
  draft_task_id: string | null
  draft_task_status: string | null
}

export interface ProgramCreateInput {
  name: string
  department_url?: string | null
}

export interface SchoolCreateInput {
  name: string
  country?: string | null
  website_url?: string | null
  programs?: ProgramCreateInput[]
}

export interface Draft {
  id: string
  candidate_id: string
  professor_name: string
  professor_email?: string | null
  professor_photo_url?: string | null
  school_name?: string | null
  program_name?: string | null
  candidate_status: string
  similarity_score: number | null
  rationale: string | null
  subject: string
  body: string
  created_at: string
}

export interface SkippedItem {
  id: string
  reason: string
  task_id?: string
}

export interface BulkDraftResult {
  queued: string[]
  skipped: SkippedItem[]
}

export interface BulkReviewResult {
  updated: string[]
  skipped: SkippedItem[]
}

export interface ReviewInput {
  candidate_id: string
  approved: boolean
}

export interface ListParams {
  status?: string
  task_type?: string
  limit?: number
  offset?: number
  sort?: string
  q?: string
  run_ids?: string[]
}

export interface Paged<T> {
  items: T[]
  total: number
}

export interface AuthUser {
  id: string
  email: string
  created_at: string
  display_name: string | null
  /** Public, immutable URL for the profile picture; null when unset. */
  avatar_url: string | null
  email_verified: boolean
  /** False for accounts created through a sign-in provider only. */
  has_password: boolean
  /** The plan in effect ("beta" while plans don't apply). */
  plan: string
  /** True until the account picks a plan (onboarding's plan step). */
  needs_plan: boolean
  /** Unset model choices use the default own model, not Auto. */
  prefer_own_model?: boolean
  agent_full_access?: boolean
}

export interface AuthTokens {
  access_token: string
  refresh_token: string
  token_type: string
}

export interface AuthSession {
  user: AuthUser
  tokens: AuthTokens
}

export interface AgentTool {
  name: string
  scope: string
  enabled: boolean
  read_only: boolean
  confirm_required: boolean
  description: string
  /** Toggle-together group id, null when the tool stands alone. */
  group: string | null
  updated_at: string | null
}

export interface AgentToolGroup {
  id: string
  label: string
  description: string
  tools: string[]
}

export interface AgentTask {
  task_type: string
  enabled: boolean
  tools: string[]
  updated_at: string | null
}

export interface ProviderConfig {
  provider: string
  model: string
  base_url: string
  /** The model's context window in tokens; null when not set. */
  context_window: number | null
  has_key: boolean
  /** The account's default own model (used when it prefers its own). */
  is_active: boolean
  /** Switched off rows keep their details but are never used. */
  enabled: boolean
  updated_at: string | null
}

export interface ProviderCatalogEntry {
  provider: string
  default_model: string
  default_base_url: string
  key_required: boolean
  base_url_required: boolean
}

export interface SystemModel {
  provider: string
  model: string
  base_url: string
  key_configured: boolean
  context_window: number | null
}

export interface ProviderCatalog {
  providers: ProviderCatalogEntry[]
  system: SystemModel
}

export interface ProviderTest {
  ok: boolean
  models: string[]
  count: number
  error: string | null
}

export interface Health {
  status: "ok" | "degraded" | string
  /** Tasks are waiting and no worker process is alive to run them. */
  no_workers?: boolean
  database: {
    reachable: boolean
    dialect?: string
    latency_ms?: number
    runs?: number
    tasks?: number
    candidates?: number
    drafts?: number
    error?: string
  }
  queue: {
    pending?: number
    running?: number
    done?: number
    error?: number
    stale_running?: number
    /** Pending professor tasks waiting for OpenAlex's daily budget to reset. */
    waiting_for_openalex?: number
    /** Failures in error_window_minutes; `error` is a lifetime count, so use this for "broken now" banners. */
    recent_error?: number
    error_window_minutes?: number
    last_activity_at?: string | null
    eta_seconds?: number | null
  }
  search_configured?: boolean
  typesafe_enabled?: boolean
  [key: string]: unknown
}

export interface RequirementItem {
  label: string
  done: boolean
}

export interface ApplicationProfessorLink {
  name: string
  professor_id: string | null
  candidate_id: string | null
  school: string | null
}

export interface ApplicationOut {
  id: string
  school: string
  program: string
  degree_type: string
  location: string
  link: string
  requirements: RequirementItem[]
  offer: string
  deadline: string
  /** Parsed or picked deadline date (yyyy-mm-dd); null when unknown. */
  deadline_date?: string | null
  status: string
  professors: ApplicationProfessorLink[]
  notes: string
  fee_waiver: boolean
  fee_waiver_notes: string
  source: string
  run_id: string | null
  created_at: string
  updated_at: string
  school_image_url?: string | null
}

export interface ApplicationCreate {
  school: string
  program?: string
  degree_type?: string
  location?: string
  link?: string
  requirements?: RequirementItem[]
  offer?: string
  deadline?: string
  deadline_date?: string | null
  status?: string
  professors?: ApplicationProfessorLink[]
  notes?: string
  fee_waiver?: boolean
  fee_waiver_notes?: string
}

export interface ApplicationUpdate {
  school?: string
  program?: string
  degree_type?: string
  location?: string
  link?: string
  requirements?: RequirementItem[]
  offer?: string
  deadline?: string
  deadline_date?: string | null
  status?: string
  professors?: ApplicationProfessorLink[]
  notes?: string
  fee_waiver?: boolean
  fee_waiver_notes?: string
}

export type DocumentKind = "cv" | "sop" | "diversity_statement" | "research_proposal" | "interest" | "note"

/** One level of folders, for sorting documents only. */
export interface DocumentFolder {
  id: string
  name: string
  sort_order: number
  document_count: number
  created_at: string | null
  updated_at: string | null
}

export interface CvVersionSummary {
  id: string
  document_id: string
  name: string
  candidate_id: string | null
  professor_id: string | null
  application_id: string | null
  /** Who it was tailored for, e.g. "Ada Lovelace, ETH Zurich". */
  target_label: string | null
  revision: number
  forked_from_revision: number | null
  /** The base changed since the fork: its changes come across only as
   * suggestions the student asks for. */
  base_updated: boolean
  /** Its own limits; null uses the base's. */
  word_limit: number | null
  page_limit: number | null
  created_at: string | null
  updated_at: string | null
}

export interface CvVersion extends CvVersionSummary {
  markdown: string
  professor_name: string | null
  school_name: string | null
  base_word_limit: number | null
  base_page_limit: number | null
}

export interface CvDocument {
  id: string
  title: string
  kind: DocumentKind
  folder_id: string | null
  /** Optional limits; null is none. */
  word_limit: number | null
  page_limit: number | null
  /** What was uploaded: docx, pdf, md or txt. */
  format: string
  size_bytes: number
  has_original: boolean
  revision: number
  version_count: number
  created_at: string | null
  updated_at: string | null
  /** Its tailored variants, most recently edited first. */
  versions: CvVersionSummary[]
}

export interface CvDocumentDetail extends CvDocument {
  markdown: string
}

export interface CvClaimCheck {
  passed?: boolean
  /** Words the change adds that the base CV never mentions. */
  new_terms?: string[]
}

export interface CvLimitCheck {
  word_limit: number | null
  page_limit: number | null
  /** Words it adds (negative: removes). */
  delta: number
  words_before: number
  /** Words and pages after its whole batch. */
  words_after: number
  pages_after: number | null
  /** It adds words and the batch ends over the limit. */
  over_limit: boolean
  /** It would go over on its own; a cut in the same batch makes room. */
  offset: boolean
}

export type DocumentLimits = { word_limit: number | null; page_limit: number | null }

export interface CheckFinding {
  kind: "placeholder" | "date_mismatch" | "name_mismatch" | "unknown_faculty"
  message: string
  /** Exact text on `line` (0-based), to mark in the editor. */
  quote: string
  line: number
}

export interface CvSuggestion {
  id: string
  document_id: string
  version_id: string | null
  find: string
  replace: string
  rationale: string | null
  claim_check: CvClaimCheck
  /** On a document with a limit: whether this keeps it within. */
  limit_check: CvLimitCheck | null
  status: "pending" | "accepted" | "rejected" | "stale"
  /** Whether the quoted text still occurs exactly once. */
  applicable: boolean
  /** The fresh suggestion asked for in place of this stale one. */
  superseded_by: string | null
  created_by: string
  created_at: string | null
  resolved_at: string | null
}

/** Quick changes on a selection; "custom" carries the student's words. */
export type CvSuggestAction = "improve" | "shorten" | "quantify" | "tailor" | "custom"

/** POST /cv/documents/{id}/suggest. `range` is in the saved text at
 * `base_revision`, counted as the editor counts (UTF-16), and `text` is
 * what it covers there. */
export interface SelectionSuggestRequest {
  version_id: string | null
  base_revision: number
  range: { from: number; to: number }
  text: string
  action: CvSuggestAction
  instruction?: string
  model?: { provider: string } | null
}

/** One change to the base since a variant was forked. */
export interface BaseChange {
  before: string
  after: string
  /** The variant still has `before` exactly once, so it can be suggested there. */
  applicable: boolean
}

export interface BaseChanges {
  base_updated: boolean
  forked_from_revision: number | null
  base_revision: number
  changes: BaseChange[]
}

export interface CvAcceptResult {
  suggestion: CvSuggestion
  markdown: string
  revision: number
}

export interface InterestSuggestion {
  text: string
  document_id: string
  document_title: string
  section: string
  evidence: string
}

export interface InterestSuggestions {
  sources: { document_id: string; title: string }[]
  suggestions: InterestSuggestion[]
  method: "model" | "heuristic" | "none"
}

export interface RunBudget {
  programs: { used: number; limit: number }
  professors: { used: number; limit: number }
  user_programs: { used: number; limit: number }
}
