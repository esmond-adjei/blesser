/** Typed fetch client for the backend; same-origin unless VITE_API_URL is set. */
import type {
  AgentTask,
  InterestSuggestions,
  RunBudget,
  AgentTool,
  AgentToolGroup,
  ProviderCatalog,
  ProviderConfig,
  ProviderTest,
  ApplicationCreate,
  ApplicationOut,
  AuthSession,
  AuthUser,
  ApplicationUpdate,
  Board,
  BulkDraftResult,
  BulkReviewResult,
  Candidate,
  CandidateDetail,
  CreateRunFromListRequest,
  CreateRunRequest,
  BaseChanges,
  CheckFinding,
  DocumentLimits,
  CvAcceptResult,
  CvDocument,
  CvDocumentDetail,
  DocumentFolder,
  DocumentKind,
  CvSuggestion,
  CvVersion,
  DeletePreview,
  SelectionSuggestRequest,
  Draft,
  FacultyRow,
  ProfessorMatch,
  Health,
  ListParams,
  Paged,
  ProfessorCreate,
  ProfessorDetail,
  ProgramDetail,
  ReviewInput,
  Run,
  RunListItem,
  RunUpdate,
  School,
  SchoolCreateInput,
  Task,
  Refusals,
  Usage,
  Worker,
  CalendarFeed,
  Opportunity,
  OpportunityFacets,
  OpportunityQuery,
  OpportunitySubmit,
  ScanRequest,
  ScanStarted,
  Todo,
  TodoCreate,
  TodoUpdate,
} from "./types"

export const API_BASE: string =
  (import.meta.env.VITE_API_URL as string | undefined) ?? ""

export class ApiError extends Error {
  status: number
  body: string
  detail: unknown
  constructor(status: number, body: string, message?: string, detail?: unknown) {
    super(message ?? `Request failed (${status}): ${body.slice(0, 300)}`)
    this.name = "ApiError"
    this.status = status
    this.body = body
    this.detail = detail
  }
}

export function apiMessage(err: unknown): string {
  if (err instanceof ApiError) return err.message
  if (err instanceof Error) return err.message
  return "Something went wrong."
}

async function reqRaw(path: string, init?: RequestInit): Promise<Response> {
  return fetch(`${API_BASE}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
  })
}

function parseDetail(text: string): { message: string; detail: unknown } {
  try {
    const parsed = JSON.parse(text) as { detail?: unknown }
    if (typeof parsed.detail === "string") return { message: parsed.detail, detail: parsed.detail }
    if (parsed.detail && typeof parsed.detail === "object") {
      const d = parsed.detail as { message?: unknown }
      if (typeof d.message === "string") return { message: d.message, detail: parsed.detail }
    }
  } catch {
    /* keep raw text */
  }
  return { message: text, detail: undefined }
}

// Token store lives here so every endpoint shares one token without import cycles.
let accessToken: string | null = null
let refreshHandler: (() => Promise<string | null>) | null = null

export function setAccessToken(token: string | null) {
  accessToken = token
}

/** Current Bearer token for transports that can't use api.ts (EventSource, Gradis fetch). */
export function getAccessToken(): string | null {
  return accessToken
}

export function setRefreshHandler(fn: (() => Promise<string | null>) | null) {
  refreshHandler = fn
}

// Auth endpoints manage their own credentials and never carry a token.
const TOKENLESS = new Set([
  "/api/auth/login",
  "/api/auth/register",
  "/api/auth/refresh",
  "/api/auth/password/forgot",
  "/api/auth/password/reset",
  "/api/auth/oauth/link",
  "/api/notifications/unsubscribe",
])

function authedInit(path: string, init?: RequestInit): RequestInit {
  if (accessToken && !TOKENLESS.has(path)) {
    return { ...init, headers: { ...(init?.headers ?? {}), Authorization: `Bearer ${accessToken}` } }
  }
  return init ?? {}
}

async function fetchWithAuth(
  path: string,
  init?: RequestInit,
): Promise<{ res: Response; text: string }> {
  let res = await reqRaw(path, authedInit(path, init))
  let text = await res.text()
  if (res.status === 401 && refreshHandler && !TOKENLESS.has(path)) {
    // One refresh then one replay on 401; the provider single-flights the refresh.
    const next = await refreshHandler()
    if (next) {
      res = await reqRaw(path, authedInit(path, init))
      text = await res.text()
    }
  }
  return { res, text }
}

/** 402 payload from the server's plan gates. */
export interface UpgradeRequired {
  code: "upgrade_required"
  message: string
  kind: "feature" | "quota"
  key: string
  label: string
  plan: string
  upgrade_to: string
  used?: number
  limit?: number
  /** Quota noun for sentences, e.g. "research runs". */
  noun?: string
}

export const UPGRADE_EVENT = "graduator:upgrade-required"

/** Any 402 from a plan gate opens the one shared upgrade prompt. */
export function notifyUpgrade(status: number, detail: unknown) {
  if (status !== 402 || !detail || typeof detail !== "object") return
  if ((detail as { code?: unknown }).code !== "upgrade_required") return
  window.dispatchEvent(new CustomEvent<UpgradeRequired>(UPGRADE_EVENT, { detail: detail as UpgradeRequired }))
}

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const { res, text } = await fetchWithAuth(path, init)
  if (!res.ok) {
    const { message, detail } = parseDetail(text)
    notifyUpgrade(res.status, detail)
    throw new ApiError(res.status, text, message.slice(0, 500), detail)
  }
  if (!text) return undefined as T
  return JSON.parse(text) as T
}

/** File response as a blob plus download name; same auth and retry as `req`. */
async function reqFile(path: string, init?: RequestInit): Promise<{ blob: Blob; filename: string }> {
  let res = await reqRaw(path, authedInit(path, init))
  if (res.status === 401 && refreshHandler && !TOKENLESS.has(path)) {
    if (await refreshHandler()) res = await reqRaw(path, authedInit(path, init))
  }
  if (!res.ok) {
    const text = await res.text()
    const { message, detail } = parseDetail(text)
    notifyUpgrade(res.status, detail)
    throw new ApiError(res.status, text, message.slice(0, 500), detail)
  }
  const disposition = res.headers.get("Content-Disposition") ?? ""
  const filename = /filename="([^"]+)"/.exec(disposition)?.[1] ?? "download"
  return { blob: await res.blob(), filename }
}

/** GET that also reads the X-Total-Count header (paged list endpoints). */
async function reqPaged<T>(path: string): Promise<Paged<T>> {
  const { res, text } = await fetchWithAuth(path)
  if (!res.ok) {
    const { message, detail } = parseDetail(text)
    throw new ApiError(res.status, text, message.slice(0, 500), detail)
  }
  const total = Number(res.headers.get("X-Total-Count") ?? "0")
  return { items: JSON.parse(text) as T[], total: Number.isFinite(total) ? total : 0 }
}

function toQuery(params: ListParams): string {
  const q = new URLSearchParams()
  if (params.status && params.status !== "all") q.set("status", params.status)
  if (params.task_type && params.task_type !== "all") q.set("task_type", params.task_type)
  if (params.limit != null) q.set("limit", String(params.limit))
  if (params.offset) q.set("offset", String(params.offset))
  if (params.sort) q.set("sort", params.sort)
  if (params.q) q.set("q", params.q)
  if (params.run_ids && params.run_ids.length > 0) q.set("run_ids", params.run_ids.join(","))
  const s = q.toString()
  return s ? `?${s}` : ""
}

const get = <T>(path: string): Promise<T> => req<T>(path)
const post = <T>(path: string, body?: unknown): Promise<T> =>
  req<T>(path, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) })
const patch = <T>(path: string, body: unknown): Promise<T> =>
  req<T>(path, { method: "PATCH", body: JSON.stringify(body) })
const put = <T>(path: string, body: unknown): Promise<T> =>
  req<T>(path, { method: "PUT", body: JSON.stringify(body) })
const del = <T>(path: string, body?: unknown): Promise<T> =>
  req<T>(path, { method: "DELETE", body: body === undefined ? undefined : JSON.stringify(body) })

export const registerAccount = (email: string, password: string, acceptTerms: boolean) =>
  post<AuthSession>("/api/auth/register", { email, password, accept_terms: acceptTerms })
export const loginAccount = (email: string, password: string) =>
  post<AuthSession>("/api/auth/login", { email, password })
export const refreshSession = (refreshToken: string) =>
  post<AuthSession>("/api/auth/refresh", { refresh_token: refreshToken })
export const logoutSession = (refreshToken: string, pushEndpoint?: string | null) =>
  post<{ status: string }>("/api/auth/logout", { refresh_token: refreshToken, push_endpoint: pushEndpoint ?? null })
export const getMe = () => get<AuthUser>("/api/auth/me")
export interface OAuthProvider { id: string; label: string }
export interface OAuthLinkRequired { provider: string; email: string; link_token: string }
export type OAuthCallbackResult =
  | { user: AuthUser; tokens: { access_token: string; refresh_token: string }; next: string }
  | { link_required: OAuthLinkRequired; next: string }
export const oauthProviders = () => get<OAuthProvider[]>("/api/auth/oauth/providers")
export const oauthStart = (provider: string, next: string) =>
  post<{ authorize_url: string; state: string }>(`/api/auth/oauth/${provider}/start`, { next })
export const oauthCallback = (provider: string, code: string, state: string) =>
  post<OAuthCallbackResult>(`/api/auth/oauth/${provider}/callback`, { code, state })
export const oauthLink = (link_token: string, password: string) =>
  post<{ user: AuthUser; tokens: { access_token: string; refresh_token: string } }>("/api/auth/oauth/link", { link_token, password })
export interface AccountExport {
  id: string
  status: "pending" | "ready" | "failed"
  size_bytes: number | null
  error: string | null
  created_at: string
  expires_at: string
}
export interface UsageDay { day: string; calls: number; input_tokens: number; output_tokens: number }
export interface UsageRow { feature: string; provider: string; model: string; calls: number; input_tokens: number; output_tokens: number }
export interface AccountUsage {
  since: string
  days: UsageDay[]
  by_feature: UsageRow[]
  by_day_feature: { day: string; feature: string; calls: number; tokens: number }[]
  totals: { calls: number; input_tokens: number; output_tokens: number }
  /** The same length of time just before `since`. */
  previous: { calls: number; input_tokens: number; output_tokens: number }
}
export interface PlanSummary {
  plan: { id: string; label: string }
  enforced: boolean
  features: { key: string; label: string; included: boolean }[]
  quotas: { key: string; label: string; limit: number | null; used: number | null }[]
  /** The system model's (Auto's) daily allowance; null limit = unlimited. */
  system_model?: { daily_limit: number | null; used_today: number }
  /** Development plan switch (BILLING_PLAN_SWITCH): the plans to pick from. */
  switchable: boolean
  plans: { id: string; label: string }[]
  /** The plans on offer in the plan picker. */
  catalog: PlanOffer[]
}
export interface PlanOffer {
  id: string
  label: string
  monthly_price_usd: number
  features: string[]
  quotas: { key: string; label: string; limit: number | null }[]
}
export type CheckoutStart =
  | { status: "applied"; plan: string }
  | { status: "checkout"; plan: string; session: string }
export interface CheckoutPage {
  provider: string
  plan: { id: string; label: string }
  monthly_price_usd: number
  test_cards: { succeeds: string; declined: string }
}
export const getPlan = () => get<PlanSummary>("/api/billing/plan")
export const startCheckout = (plan: string) => post<CheckoutStart>("/api/billing/checkout", { plan })
export const getCheckout = (session: string) =>
  get<CheckoutPage>(`/api/billing/checkout?session=${encodeURIComponent(session)}`)
export const completeCheckout = (session: string, cardNumber: string) =>
  post<{ status: "paid"; plan: string }>("/api/billing/checkout/complete", { session, card_number: cardNumber })
export const switchPlan = (plan: string) =>
  req<PlanSummary>("/api/billing/plan", { method: "PUT", body: JSON.stringify({ plan }) })
export const getAccountUsage = (days: number) => get<AccountUsage>(`/api/usage?days=${days}`)
export interface FlowStep {
  type: string
  enabled: boolean
  tool_groups: string[]
  tools: string[]
  instructions: string
}
export interface AgentFlow { id: string; name: string; builtin: boolean; base?: string; steps: FlowStep[] }
export interface FlowList { steps: { type: string; label: string; summary: string }[]; flows: AgentFlow[] }
export const listFlows = () => get<FlowList>("/api/flows")
export const duplicateFlow = (source: string, name: string) => post<AgentFlow>("/api/flows", { source, name })
export const updateFlow = (id: string, body: { name?: string; steps?: FlowStep[] }) => patch<AgentFlow>(`/api/flows/${id}`, body)
export const deleteFlow = (id: string) => del<{ status: string }>(`/api/flows/${id}`)
export const listExports = () => get<AccountExport[]>("/api/account/exports")
export const createExport = () => post<AccountExport>("/api/account/exports", {})
export const exportLink = (id: string) => post<{ url: string }>(`/api/account/exports/${id}/link`, {})
export const forgotPassword = (email: string) => post<{ status: string }>("/api/auth/password/forgot", { email })
export const resetPassword = (token: string, new_password: string) =>
  post<{ status: string }>("/api/auth/password/reset", { token, new_password })
export const verifyEmail = (token: string) => post<AuthUser>("/api/auth/verify", { token })
export const resendVerification = () => post<{ status: string }>("/api/auth/verify/send", {})
export const updateProfile = (display_name: string | null) =>
  patch<AuthUser>("/api/auth/me", { display_name })
/** Whether unset model choices use your default own model instead of Auto. */
export const setPreferOwnModel = (prefer_own_model: boolean) =>
  patch<AuthUser>("/api/auth/me", { prefer_own_model })
/** Gradis makes changes without approval cards. */
export const setAgentFullAccess = (agent_full_access: boolean) =>
  patch<AuthUser>("/api/auth/me", { agent_full_access })
export const uploadAvatar = (file: Blob) => {
  const form = new FormData()
  form.append("file", file, "avatar.webp")
  return upload<AuthUser>("/api/auth/me/avatar", form, "PUT")
}
export const removeAvatar = () => del<AuthUser>("/api/auth/me/avatar")
export const changePassword = (current_password: string, new_password: string) =>
  post<{ status: string }>("/api/auth/change-password", { current_password, new_password })
export const deleteAccount = (password: string) =>
  del<{ status: string }>("/api/auth/account", { password })

export const listAgentTools = () => get<AgentTool[]>("/api/agent/tools")
export const updateAgentTool = (scope: string, name: string, body: { enabled?: boolean; confirm_required?: boolean }) =>
  patch<AgentTool>(`/api/agent/tools/${scope}/${name}`, body)
export const listAgentToolGroups = () => get<AgentToolGroup[]>("/api/agent/tool-groups")
export const updateAgentToolGroup = (scope: string, group: string, body: { enabled?: boolean; confirm_required?: boolean }) =>
  patch<AgentTool[]>(`/api/agent/tool-groups/${scope}/${group}`, body)
export const listAgentTasks = () => get<AgentTask[]>("/api/agent/tasks")
export const updateAgentTask = (taskType: string, body: { enabled?: boolean; tools?: string[] }) =>
  patch<AgentTask>(`/api/agent/tasks/${taskType}`, body)

export const listProviders = () => get<ProviderConfig[]>("/api/providers")
export const updateProvider = (provider: string, body: { model?: string; api_key?: string; base_url?: string; context_window?: number | null; is_active?: boolean; enabled?: boolean }) =>
  patch<ProviderConfig>(`/api/providers/${provider}`, body)
export const testProvider = (provider: string, body?: { base_url?: string; api_key?: string }) =>
  post<ProviderTest>(`/api/providers/${provider}/test`, body ?? {})
export const getProviderCatalog = () => get<ProviderCatalog>("/api/providers/catalog")

export const getHealth = () => get<Health>("/health")
export const getReady = () => get<{ ready: boolean }>("/ready")
export const listWorkers = () => get<Worker[]>("/api/workers")

export const listRuns = () => get<RunListItem[]>("/api/runs")
/** One page of runs, newest first; a short page is the last. */
export const listRunsPage = (limit: number, offset: number) =>
  get<RunListItem[]>(`/api/runs?limit=${limit}&offset=${offset}`)
export const createRun = (body: CreateRunRequest) => post<Run>("/api/runs", body)
/** Interest phrases from one CV (or the newest few when none is named);
 * `signal` cancels the request. */
export const suggestRunInterests = (documentId?: string | null, signal?: AbortSignal) =>
  req<InterestSuggestions>("/api/runs/interest-suggestions", {
    method: "POST",
    body: JSON.stringify(documentId ? { document_id: documentId } : {}),
    signal,
  })
export const getRunBudget = (runId: string) => get<RunBudget>(`/api/runs/${runId}/budget`)
export const createRunFromList = (body: CreateRunFromListRequest) =>
  post<Run>("/api/runs/from-list", body)
export const getRun = (id: string) => get<Run>(`/api/runs/${id}`)
export const updateRun = (id: string, body: RunUpdate) => patch<Run>(`/api/runs/${id}`, body)
export const cancelRun = (id: string) => post<{ status: string }>(`/api/runs/${id}/cancel`)
export const pauseRun = (id: string) => post<{ status: string }>(`/api/runs/${id}/pause`)
/** Pause, resume or cancel one agent (task type) in a run. */
export const controlAgent = (id: string, taskType: string, action: "pause" | "resume" | "cancel") =>
  post<{ agent: string; state: string | null; affected: number; agent_states: Record<string, string> }>(
    `/api/runs/${id}/agents/${taskType}/${action}`,
  )
export const resumeRun = (id: string) => post<{ status: string }>(`/api/runs/${id}/resume`)
export const retryFailed = (id: string) => post<{ retried: number }>(`/api/runs/${id}/retry-failed`)
export const getUsage = (id: string) => get<Usage>(`/api/runs/${id}/usage`)
export const getRefusals = (id: string) => get<Refusals>(`/api/runs/${id}/refusals`)
export interface RunEstimate {
  estimated_tokens: number
  narrow_tasks: number
  basis: "history" | "defaults"
  daily_allowance_left: number | null
  fits: boolean | null
}
export const getRunEstimate = (dials: {
  max_programs: number
  max_professors: number
  max_professors_per_program: number
  llm_provider?: string
}) => {
  const q = new URLSearchParams({
    max_programs: String(dials.max_programs),
    max_professors: String(dials.max_professors),
    max_professors_per_program: String(dials.max_professors_per_program),
  })
  if (dials.llm_provider) q.set("llm_provider", dials.llm_provider)
  return get<RunEstimate>(`/api/runs/estimate?${q.toString()}`)
}
export const getDeletePreview = (id: string) => get<DeletePreview>(`/api/runs/${id}/delete-preview`)
export const deleteRun = (id: string) => del<{ status: string }>(`/api/runs/${id}`)
export const listTasks = (runId: string, params: ListParams = {}) =>
  reqPaged<Task>(`/api/runs/${runId}/tasks${toQuery({ limit: 100, ...params })}`)
export const getBoard = (runId: string) => get<Board>(`/api/runs/${runId}/board`)
export const listRunSchools = (runId: string) => get<School[]>(`/api/runs/${runId}/programs`)
/** Every school the account has, once each, with the runs that use it. */
export const listSchools = () => get<School[]>("/api/schools")
export const listSchoolFaculty = (schoolId: string) => get<FacultyRow[]>(`/api/schools/${schoolId}/faculty`)
export const listRunCandidates = (runId: string, params: ListParams = {}) =>
  reqPaged<Candidate>(`/api/runs/${runId}/candidates${toQuery({ limit: 50, ...params })}`)
export const searchCandidates = (params: ListParams = {}) =>
  reqPaged<Candidate>(`/api/candidates/search${toQuery({ limit: 50, sort: "score", ...params })}`)
export const listRunDrafts = (runId: string) => get<Draft[]>(`/api/runs/${runId}/drafts`)

export const getTask = (id: string) => get<Task>(`/api/tasks/${id}`)
export const retryTask = (id: string) => post<{ status: string }>(`/api/tasks/${id}/retry`)
export const rerunTask = (id: string) => post<{ status: string }>(`/api/tasks/${id}/rerun`)
export const pauseTask = (id: string) => post<{ status: string }>(`/api/tasks/${id}/pause`)
export const resumeTask = (id: string) => post<{ status: string }>(`/api/tasks/${id}/resume`)
export const cancelTask = (id: string) => post<{ status: string }>(`/api/tasks/${id}/cancel`)
export const deleteTask = (id: string) => del<{ status: string }>(`/api/tasks/${id}`)

export const createSchool = (runId: string, body: SchoolCreateInput) =>
  post<School>(`/api/runs/${runId}/schools`, body)
export const getSchool = (id: string) => get<School>(`/api/schools/${id}`)
export const updateSchool = (id: string, body: { name?: string; country?: string | null; website_url?: string | null }) =>
  patch<School>(`/api/schools/${id}`, body)
export const getProgram = (id: string) => get<ProgramDetail>(`/api/programs/${id}`)
export const listProfessors = () => get<FacultyRow[]>("/api/professors")
/** Interests to match against: a run's, or an interest document's. */
export type InterestSource = { run_id: string } | { document_id: string }
export const matchProfessor = (id: string, source: InterestSource, save = false) =>
  post<ProfessorMatch>(`/api/professors/${id}/match`, { ...source, save })
export const getProfessor = (id: string) => get<ProfessorDetail>(`/api/professors/${id}`)
export const updateProfessor = (id: string, body: { name?: string; profile_url?: string | null; email?: string | null; lab_name?: string | null; bio?: string | null; bio_source?: string | null; photo_url?: string | null; socials?: Array<{ label: string; url: string }> }) =>
  patch<ProfessorDetail>(`/api/professors/${id}`, body)
export const createProfessor = (programId: string, body: ProfessorCreate) =>
  post<ProfessorDetail>(`/api/programs/${programId}/professors`, body)

export const getCandidate = (id: string) => get<CandidateDetail>(`/api/candidates/${id}`)
/** One branded PDF per request: dossiers, or a cover and a section per candidate. */
export const exportCandidatesPdf = (candidateIds: string[]) =>
  reqFile("/api/candidates/export.pdf", { method: "POST", body: JSON.stringify({ candidate_ids: candidateIds }) })
export const listCandidateDrafts = (id: string) =>
  get<Draft[]>(`/api/candidates/${id}/drafts`)
export const deleteCandidate = (id: string) => del<{ status: string }>(`/api/candidates/${id}`)
export const requestDraft = (candidateId: string) =>
  post<{ status: string }>(`/api/candidates/${candidateId}/request-draft`)
export const reviewCandidate = (candidateId: string, approved: boolean) =>
  post<{ status: string }>(`/api/candidates/${candidateId}/review`, { approved })
export const requestDrafts = (runId: string, candidateIds: string[]) =>
  post<BulkDraftResult>(`/api/runs/${runId}/request-drafts`, { candidate_ids: candidateIds })
export const reviewBulk = (runId: string, reviews: ReviewInput[]) =>
  post<BulkReviewResult>(`/api/runs/${runId}/review-bulk`, { reviews })
export const updateDraft = (draftId: string, body: { subject?: string; body?: string }) =>
  patch<Draft>(`/api/drafts/${draftId}`, body)
export const deleteDraft = (draftId: string) => del<{ status: string }>(`/api/drafts/${draftId}`)

export const listApplications = () => get<ApplicationOut[]>("/api/applications")
export const createApplication = (body: ApplicationCreate) =>
  post<ApplicationOut>("/api/applications", body)
export const updateApplication = (id: string, body: ApplicationUpdate) =>
  patch<ApplicationOut>(`/api/applications/${id}`, body)
export const deleteApplication = (id: string) => del<{ status: string }>(`/api/applications/${id}`)

export const resolveApplicationProfessors = (id: string) =>
  post<ApplicationOut>(`/api/applications/${id}/resolve-professors`)

/** Multipart request with Bearer auth and the same 401 retry. No Content-Type
 * header: the browser sets the multipart boundary. */
async function upload<T>(path: string, form: FormData, method: "POST" | "PUT" = "POST"): Promise<T> {
  const send = () => fetch(`${API_BASE}${path}`, authedInit(path, { method, body: form }))
  let res = await send()
  if (res.status === 401 && refreshHandler && (await refreshHandler())) res = await send()
  const text = await res.text()
  if (!res.ok) {
    const { message, detail } = parseDetail(text)
    throw new ApiError(res.status, text, message.slice(0, 500), detail)
  }
  return JSON.parse(text) as T
}

export type CvExportFormat = "pdf" | "docx" | "md" | "txt"

export const uploadCv = (file: File, opts: { title?: string; kind?: DocumentKind; folderId?: string | null } = {}) => {
  const form = new FormData()
  form.append("file", file)
  if (opts.title) form.append("title", opts.title)
  if (opts.kind) form.append("kind", opts.kind)
  if (opts.folderId) form.append("folder_id", opts.folderId)
  return upload<CvDocumentDetail>("/api/cv/documents", form)
}
export const createCvFromText = (body: { title: string; markdown: string; kind?: DocumentKind; folder_id?: string | null }) =>
  post<CvDocumentDetail>("/api/cv/documents/text", body)
/** Every document, of every kind (filter by `kind` for one). */
export const listCvDocuments = () => get<CvDocument[]>("/api/cv/documents")
export const listCvs = () => get<CvDocument[]>("/api/cv/documents?kind=cv")
/** Move a document into a folder, or out of one (null). Its text stays. */
export const moveDocument = (id: string, folderId: string | null) =>
  patch<CvDocumentDetail>(`/api/cv/documents/${id}`, { folder_id: folderId })
/** Set a document's word and page limits (null removes one). Its text stays. */
export const setDocumentLimits = (id: string, limits: Partial<DocumentLimits>) =>
  patch<CvDocumentDetail>(`/api/cv/documents/${id}`, limits)
/** A variant's own limits (null uses the base's). */
export const setVersionLimits = (id: string, limits: Partial<DocumentLimits>) =>
  patch<CvVersion>(`/api/cv/versions/${id}`, limits)
/** Read-only consistency checks on the saved text of the base or a variant. */
export const getDocumentChecks = (documentId: string, versionId: string | null) =>
  get<{ findings: CheckFinding[] }>(
    `/api/cv/documents/${documentId}/checks${versionId ? `?version_id=${versionId}` : ""}`,
  )
export const listDocumentFolders = () => get<DocumentFolder[]>("/api/cv/folders")
export const createDocumentFolder = (name: string) => post<DocumentFolder>("/api/cv/folders", { name })
export const renameDocumentFolder = (id: string, name: string) =>
  patch<DocumentFolder>(`/api/cv/folders/${id}`, { name })
export const reorderDocumentFolders = (ids: string[]) => put<DocumentFolder[]>("/api/cv/folders/order", { ids })
export const deleteDocumentFolder = (id: string) => del<{ status: string }>(`/api/cv/folders/${id}`)
export const getCvDocument = (id: string) => get<CvDocumentDetail>(`/api/cv/documents/${id}`)
export const saveCvDocument = (id: string, body: { base_revision: number; markdown?: string; title?: string }) =>
  put<CvDocumentDetail>(`/api/cv/documents/${id}`, body)
export const deleteCvDocument = (id: string) => del<{ status: string }>(`/api/cv/documents/${id}`)
export const downloadCvOriginal = (id: string) => reqFile(`/api/cv/documents/${id}/original`)
export const exportCvDocument = (id: string, format: CvExportFormat) =>
  reqFile(`/api/cv/documents/${id}/export?format=${format}`)
export const createCvVersion = (
  documentId: string,
  body: { name?: string; candidate_id?: string; application_id?: string; new?: boolean; markdown?: string },
) => post<CvVersion>(`/api/cv/documents/${documentId}/versions`, body)
export const getCvVersion = (id: string) => get<CvVersion>(`/api/cv/versions/${id}`)
export const saveCvVersion = (id: string, body: { base_revision: number; markdown?: string; title?: string }) =>
  put<CvVersion>(`/api/cv/versions/${id}`, body)
export const deleteCvVersion = (id: string) => del<{ status: string }>(`/api/cv/versions/${id}`)
export const exportCvVersion = (id: string, format: CvExportFormat) =>
  reqFile(`/api/cv/versions/${id}/export?format=${format}`)
export const listCvSuggestions = (params: { document_id: string; version_id?: string | null }) => {
  const q = new URLSearchParams({ document_id: params.document_id })
  if (params.version_id) q.set("version_id", params.version_id)
  else q.set("base_only", "true")
  return get<CvSuggestion[]>(`/api/cv/suggestions?${q.toString()}`)
}
export const acceptCvSuggestion = (id: string, body: { replace?: string; confirm_new_terms?: boolean } = {}) =>
  post<CvAcceptResult>(`/api/cv/suggestions/${id}/accept`, body)
export const rejectCvSuggestion = (id: string) => post<CvSuggestion>(`/api/cv/suggestions/${id}/reject`)
/** A fresh suggestion in place of a stale one, against the text as it is now. */
export const refreshCvSuggestion = (id: string, body: { model?: { provider: string } | null } = {}) =>
  post<CvSuggestion[]>(`/api/cv/suggestions/${id}/refresh`, body)
/** What changed in the base since a variant was forked (read-only). */
export const getBaseChanges = (versionId: string) => get<BaseChanges>(`/api/cv/versions/${versionId}/base-changes`)
/** The base's changes as suggestions on the variant; its text doesn't change. */
export const syncFromBase = (versionId: string) =>
  post<{ suggestions: CvSuggestion[]; skipped: number }>(`/api/cv/versions/${versionId}/sync`)
/** Keep the variant as it is: the base's changes so far aren't offered again. */
export const keepVersionAsIs = (versionId: string) => post<CvVersion>(`/api/cv/versions/${versionId}/keep`)
/** A suggested rewrite of the selected passage of the saved text, stored
 * for review like any other suggestion. */
export const suggestForSelection = (documentId: string, body: SelectionSuggestRequest) =>
  post<CvSuggestion[]>(`/api/cv/documents/${documentId}/suggest`, body)
/** Where each page of the CV's PDF starts (1-based source lines), for the editor's page breaks. */
export const cvLayout = (markdown: string) =>
  post<{ pages: number; breaks: { page: number; line: number }[] }>("/api/cv/layout", { markdown })

export type NotificationChannel = "inbox" | "push" | "email"
export interface AppNotification {
  id: string
  kind: string
  title: string
  body: string
  /** In-app path the notification opens. */
  link: string
  entity_id: string | null
  created_at: string
  read_at: string | null
}
export interface NotificationInbox {
  items: AppNotification[]
  unread: number
  /** Stored timezone; null until the browser reports one. */
  timezone: string | null
}
export interface NotificationKindPrefs {
  kind: string
  label: string
  description: string
  channels: Record<NotificationChannel, boolean>
  defaults: Record<NotificationChannel, boolean>
}
export interface NotificationPreferences {
  kinds: NotificationKindPrefs[]
  quiet_start: string | null
  quiet_end: string | null
  timezone: string | null
  email_digest: boolean
}
export interface NotificationPreferencesPatch {
  channels?: Record<string, Partial<Record<NotificationChannel, boolean>>>
  quiet_start?: string | null
  quiet_end?: string | null
  timezone?: string | null
  email_digest?: boolean
}
export interface PushDevice {
  id: string
  endpoint: string
  user_agent: string | null
  created_at: string
  last_ok_at: string | null
}
export const listNotifications = () => get<NotificationInbox>("/api/notifications")
export const deleteNotification = (id: string) => del<{ removed: number }>(`/api/notifications/${encodeURIComponent(id)}`)
export const clearNotifications = () => del<{ removed: number }>("/api/notifications")
export const markNotificationRead = (id: string) => post<{ marked: number }>(`/api/notifications/${id}/read`)
export const markAllNotificationsRead = () => post<{ marked: number }>("/api/notifications/read-all")
export const getNotificationPreferences = () => get<NotificationPreferences>("/api/notifications/preferences")
export const updateNotificationPreferences = (body: NotificationPreferencesPatch) =>
  patch<NotificationPreferences>("/api/notifications/preferences", body)
export const getPushConfig = () => get<{ enabled: boolean; public_key: string | null }>("/api/notifications/push/config")
export const listPushDevices = () => get<PushDevice[]>("/api/notifications/push/subscriptions")
export const savePushSubscription = (body: {
  endpoint: string
  keys: { p256dh: string; auth: string }
  timezone?: string
}) => post<PushDevice>("/api/notifications/push/subscriptions", body)
export const removePushSubscription = (endpoint: string) =>
  del<{ removed: number }>("/api/notifications/push/subscriptions", { endpoint })
export const sendTestNotification = () =>
  post<{ push_enabled: boolean; devices: number; pushed: number }>("/api/notifications/test")
export const sendTestEmail = () =>
  post<{ to: string; sent: boolean; backend: string }>("/api/notifications/test-email")
export const unsubscribeNotificationEmail = (token: string) =>
  post<{ status: string; kind: string; label: string }>("/api/notifications/unsubscribe", { token })

export interface SearchHit { kind: string; id: string; title: string; subtitle?: string | null; href: string | null; snippet?: string | null; image_url?: string | null }
export const globalSearch = (q: string) => get<{ items: SearchHit[] }>(`/api/search${toQuery({ q })}`)

// --- Opportunities (public reads), to-dos and the calendar feed -------------

function opportunityParams(query: OpportunityQuery): string {
  const params = new URLSearchParams()
  for (const [key, value] of Object.entries(query)) {
    if (value === undefined || value === null || value === "") continue
    params.set(key, String(value))
  }
  const text = params.toString()
  return text ? `?${text}` : ""
}

export const listOpportunities = (query: OpportunityQuery = {}) =>
  get<Paged<Opportunity>>(`/api/opportunities${opportunityParams(query)}`)
export const getOpportunity = (id: string) => get<Opportunity>(`/api/opportunities/${id}`)
export const opportunityFacets = () => get<OpportunityFacets>("/api/opportunities/facets")
export const trackedOpportunities = () => get<Record<string, string>>("/api/opportunities/tracked")
export const trackOpportunity = (id: string) =>
  post<ApplicationOut>(`/api/opportunities/${id}/track`)
export const submitOpportunity = (body: OpportunitySubmit) =>
  post<Opportunity>("/api/opportunities", body)
export const startOpportunityScan = (body: ScanRequest) =>
  post<ScanStarted>("/api/opportunities/scans", body)
/** Absolute URL of one opportunity's .ics file (no auth needed). */
export const opportunityIcsUrl = (id: string) => `${API_BASE}/api/opportunities/${id}/calendar.ics`

export const listTodos = (status: "open" | "done" | "all" = "open") =>
  get<Todo[]>(`/api/todos?status=${status}`)
export const createTodo = (body: TodoCreate) => post<Todo>("/api/todos", body)
export const updateTodo = (id: string, body: TodoUpdate) => patch<Todo>(`/api/todos/${id}`, body)
export const deleteTodo = (id: string) => del<{ status: string }>(`/api/todos/${id}`)

export const getCalendarFeed = () => get<CalendarFeed>("/api/calendar/feed")
export const rotateCalendarFeed = () => post<CalendarFeed>("/api/calendar/feed/rotate")
