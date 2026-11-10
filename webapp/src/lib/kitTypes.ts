export type LanguageLevel = "basic" | "conversational" | "fluent" | "native"

export interface Education {
  institution: string
  qualification: string
  field: string
  start: string | null
  end: string | null
  grade: string
  country: string
}

export interface Experience {
  organization: string
  role: string
  start: string | null
  end: string | null
  current: boolean
  location: string
  summary: string
}

export interface Reference {
  name: string
  title: string
  organization: string
  email: string
  phone: string
  relationship: string
}

export interface Sensitive {
  national_id: string
  passport_number: string
  passport_expiry: string | null
}

export interface Profile {
  given_name: string
  family_name: string
  preferred_name: string
  pronouns: string
  date_of_birth: string | null
  gender: string
  nationality: string
  country_of_birth: string
  place_of_birth: string
  country_of_residence: string
  city: string
  address_line1: string
  address_line2: string
  postal_code: string
  email: string
  phone: string
  linkedin_url: string
  website_url: string
  github_url: string
  other_links: { label: string; url: string }[]
  headline: string
  short_bio: string
  long_bio: string
  education: Education[]
  experience: Experience[]
  skills: string[]
  languages: { language: string; level: LanguageLevel }[]
  awards: { title: string; issuer: string; year: number | null }[]
  publications: { title: string; venue: string; year: number | null; url: string }[]
  references: Reference[]
  sensitive: Sensitive
  completeness: number
  updated_at: string
}

export type ProfileInput = Omit<Profile, "completeness" | "updated_at">

export type ProjectStage = "idea" | "prototype" | "early_revenue" | "growth" | "other"

export interface TeamMember {
  name: string
  role: string
  bio: string
  email: string
  linkedin_url: string
  is_founder: boolean
  gender: string
}

export interface Project {
  id: string
  name: string
  tagline: string
  website_url: string
  logo_document_id: string | null
  stage: ProjectStage
  sector: string
  country: string
  city: string
  founded_on: string | null
  legal_status: string
  registration_number: string
  problem: string
  solution: string
  target_customers: string
  market_size: string
  business_model: string
  competition: string
  traction: string
  impact: string
  why_now: string
  team: TeamMember[]
  team_size: number | null
  women_led: boolean
  youth_led: boolean
  revenue_last_12_months: string
  funding_raised: string
  amount_sought: string
  currency: string
  use_of_funds: string
  document_ids: string[]
  custom_fields: { label: string; value: string }[]
  completeness: number
  created_at: string
  updated_at: string
}

export type ProjectInput = Omit<Project, "id" | "completeness" | "created_at" | "updated_at">

export type DocumentKind =
  | "cv"
  | "cover_letter"
  | "pitch_deck"
  | "transcript"
  | "certificate"
  | "budget"
  | "financials"
  | "id_document"
  | "photo"
  | "logo"
  | "other"

export interface KitDocument {
  id: string
  kind: string
  title: string
  filename: string
  content_type: string
  size_bytes: number
  project_ids: string[]
  is_default: boolean
  created_at: string
}

export interface DocumentPatch {
  title?: string
  kind?: string
  project_ids?: string[]
  is_default?: boolean
}

export interface StorageUsage {
  used_bytes: number
  limit_bytes: number
}

export interface Answer {
  id: string
  question: string
  answer: string
  tags: string[]
  project_id: string | null
  word_count: number
  updated_at: string
}

export type AnswerInput = Pick<Answer, "question" | "answer" | "tags" | "project_id">

export interface Correction {
  id: string
  host: string
  label: string
  field_type: string
  value: string | string[] | null
  wrong_field: boolean
  updated_at: string
}
