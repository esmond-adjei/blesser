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

export type ScanFind = {
  opportunity_id: string
  title: string
  slug?: string | null
  category?: OpportunityCategory | null
  kind?: OpportunityKind | null
  deadline_date: string | null
  official_url: string | null
  is_new: boolean
  in_review: boolean
} & ({ source: "catalog"; source_domain: null } | { source: "web"; source_domain: string | null })

export interface Scan {
  id: string
  region: string
  categories: OpportunityCategory[]
  focus: string
  /** Sites the member asked the agent to read first. */
  sites?: string[]
  kind?: "member" | "sweep"
  status: "running" | "done" | "cancelled"
  created_at: string
  /** Listings that fit the request: matched from the catalog or found on the web. */
  opportunities_found?: number
  /** Of those, listings new to Blesser. */
  opportunities_added: number
  started_at?: string | null
  finished_at?: string | null
  tasks?: ScanTask[] | null
  finds?: ScanFind[] | null
}

export interface ScanAllowance {
  enabled: boolean
  per_hour: number
  left_this_hour: number
  per_day: number
  left_today: number
}

export interface ScanRequest {
  categories?: OpportunityCategory[]
  region?: string
  focus?: string
  sites?: string[]
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

export interface MemberOpportunity {
  id: string
  slug: string
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
  verified_at: string | null
  published_at: string | null
  is_open: boolean
  days_left: number | null
  closed: boolean
  audience: "public" | "members"
  found_by: "agent" | "community" | "staff"
  created_at: string
  is_new: boolean
  /** Only with sort=for_you. */
  match_score?: number | null
  match_terms?: string[]
}

export type Opportunity = MemberOpportunity

export type AlertFrequency = "off" | "daily" | "weekly"
export type MatchLevel = "undergraduate" | "masters" | "phd" | "postdoc" | "founder"

export interface MatchProfileInput {
  categories: OpportunityCategory[]
  kinds: OpportunityKind[]
  fields: string[]
  levels: MatchLevel[]
  countries: string[]
  alerts: AlertFrequency
  closing_soon: boolean
}

export interface MatchProfile extends MatchProfileInput {
  /** False while the values are only a suggestion from the Applicant Kit. */
  saved: boolean
  updated_at: string | null
}

export interface SearchFilters {
  q?: string
  category?: OpportunityCategory | null
  kind?: OpportunityKind | null
  country?: string | null
  closing_within?: number | null
}

export interface SavedSearch {
  id: string
  name: string
  filters: SearchFilters
  alerts: AlertFrequency
  created_at: string
}

export type OpportunitySort = "deadline" | "new" | "relevance" | "for_you"

export interface OpportunityQuery {
  q?: string
  category?: OpportunityCategory
  kind?: OpportunityKind
  country?: string
  include_closed?: boolean
  new?: boolean
  audience?: "public" | "members"
  closing_within?: number
  sort?: OpportunitySort
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

export type ShareFormat = "square" | "wide" | "story"
export interface ShareKit {
  share_url: string
  images: Record<ShareFormat, string>
  captions: { short: string; standard: string; hashtags: string }
  disclaimer: string
}
