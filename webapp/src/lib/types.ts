/** API shapes, mirroring the backend schemas. */

export interface Paged<T> {
  items: T[]
  total: number
}

export interface AuthUser {
  id: string
  email: string
  created_at: string
  display_name: string | null
  email_verified: boolean
  /** False for accounts created through a sign-in provider only. */
  has_password: boolean
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

export type ApplicationStatus = "saved" | "preparing" | "submitted" | "interview" | "accepted" | "rejected"

export interface RequirementItem {
  label: string
  done: boolean
}

export interface Application {
  id: string
  title: string
  organization: string
  kind: string
  location: string
  link: string
  benefits: string
  requirements: RequirementItem[]
  deadline: string
  /** yyyy-mm-dd when the deadline is a known date. */
  deadline_date: string | null
  status: ApplicationStatus
  notes: string
  opportunity_id: string | null
  created_at: string
  updated_at: string
}

export interface ApplicationInput {
  title?: string
  organization?: string
  kind?: string
  location?: string
  link?: string
  benefits?: string
  requirements?: RequirementItem[]
  deadline?: string
  deadline_date?: string | null
  status?: ApplicationStatus
  notes?: string
}

export interface ScanTaskEvent {
  turn: number
  kind?: "turn"
  note?: string
  tool?: string
  input?: Record<string, unknown>
  result_preview?: string
  ok?: boolean
  at?: string
}

export interface ScanTask {
  id: string
  task_type: string
  target: string | null
  status: "pending" | "running" | "done" | "error" | "cancelled"
  error: string | null
  final_text: string | null
  turns: number | null
  log: ScanTaskEvent[]
  input_tokens: number | null
  output_tokens: number | null
  created_at: string
  started_at: string | null
  finished_at: string | null
}

export interface Scan {
  id: string
  region: string
  categories: OpportunityCategory[]
  focus: string
  status: "running" | "done" | "cancelled"
  created_at: string
  opportunities_added: number
  tasks?: ScanTask[]
}

export interface ScanRequest {
  categories?: OpportunityCategory[]
  region?: string
  focus?: string
}

// --- Opportunities, to-dos and calendar ------------------------------------

export type OpportunityCategory = "startup" | "research" | "student"
export type OpportunityKind =
  | "grant"
  | "fellowship"
  | "scholarship"
  | "accelerator"
  | "incubator"
  | "competition"
  | "internship"
  | "call_for_proposals"
  | "training"
  | "conference"
  | "job"
  | "other"

export interface Opportunity {
  id: string
  title: string
  organization: string
  category: OpportunityCategory
  kind: OpportunityKind
  summary: string
  eligibility: string
  benefits: string
  location: string
  countries: string[]
  requirements: string[]
  tags: string[]
  deadline: string
  /** yyyy-mm-dd when the deadline is a known date. */
  deadline_date: string | null
  rolling: boolean
  link: string
  source_url: string
  status: "published" | "pending" | "hidden"
  source: "agent" | "community"
  verified_at: string | null
  created_at: string
  updated_at: string
  is_open: boolean
  days_left: number | null
}

export interface OpportunityQuery {
  q?: string
  category?: OpportunityCategory
  kind?: OpportunityKind
  country?: string
  include_closed?: boolean
  closing_within?: number
  sort?: "deadline" | "new"
  limit?: number
  offset?: number
}

export interface OpportunityFacets {
  categories: { key: OpportunityCategory; count: number }[]
  kinds: { key: OpportunityKind; count: number }[]
  total: number
  closing_soon: number
}

export interface OpportunitySubmit {
  title: string
  organization?: string
  category: OpportunityCategory
  kind?: OpportunityKind
  summary?: string
  eligibility?: string
  benefits?: string
  location?: string
  deadline?: string
  rolling?: boolean
  link: string
}

export type TodoPriority = "low" | "normal" | "high"

export interface Todo {
  id: string
  title: string
  notes: string
  due_date: string | null
  priority: TodoPriority
  done: boolean
  done_at: string | null
  position: number
  opportunity_id: string | null
  application_id: string | null
  opportunity_title: string | null
  application_label: string | null
  created_at: string
  updated_at: string
}

export interface TodoCreate {
  title: string
  notes?: string
  due_date?: string | null
  priority?: TodoPriority
  opportunity_id?: string | null
  application_id?: string | null
}

export interface TodoUpdate {
  title?: string
  notes?: string
  due_date?: string | null
  priority?: TodoPriority
  done?: boolean
  position?: number
}

export interface CalendarFeed {
  url: string
  webcal_url: string
  created_at: string
}
