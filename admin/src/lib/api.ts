import * as s from "./schema";

export const statuses = [
  "draft",
  "in_review",
  "published",
  "archived",
  "hidden",
] as const;
export const audiences = ["public", "members"] as const;
export const roles = ["member", "editor", "admin"] as const;
export type Status = (typeof statuses)[number];
export type Audience = (typeof audiences)[number];
export type Role = (typeof roles)[number];
export type Page<T> = { items: T[]; total: number };
export const statusSchema = s.choice(...statuses);
export const audienceSchema = s.choice(...audiences);
export const roleSchema = s.choice(...roles);
const publicFields = {
  id: s.text,
  slug: s.text,
  title: s.text,
  organization: s.text,
  category: s.text,
  kind: s.text,
  summary: s.text,
  eligibility: s.text,
  benefits: s.text,
  location: s.text,
  countries: s.array(s.text),
  requirements: s.array(s.text),
  tags: s.array(s.text),
  deadline: s.text,
  deadline_date: s.nullable(s.text),
  rolling: s.boolean,
  link: s.text,
  source_url: s.text,
  verified_at: s.nullable(s.text),
  published_at: s.nullable(s.text),
  is_open: s.boolean,
  days_left: s.nullable(s.number),
  closed: s.boolean,
};
const memberFields = {
  ...publicFields,
  audience: audienceSchema,
  found_by: s.choice("agent", "community", "staff"),
  created_at: s.text,
  is_new: s.boolean,
};
const opportunityFields = {
  ...memberFields,
  status: statusSchema,
  review_reason: s.nullable(s.text),
  editor_note: s.text,
  featured_rank: s.nullable(s.number),
  source: s.text,
  scan_id: s.nullable(s.text),
  created_by: s.nullable(s.text),
  published_by: s.nullable(s.text),
  updated_at: s.text,
  dedupe_key: s.text,
  checked_at: s.optional(s.nullable(s.text)),
  check_outcome: s.optional(s.text),
};
const opportunitySchema = s.shape(opportunityFields);
const duplicatePairSchema = s.shape({
  first: opportunitySchema,
  second: opportunitySchema,
  score: s.number,
  reason: s.choice("similar_title", "same_page"),
});
const aliasSchema = s.shape({ alias: s.text, canonical: s.text });
const auditSchema = s.shape({
  id: s.text,
  actor_id: s.text,
  actor_email: s.text,
  action: s.text,
  entity_type: s.text,
  entity_id: s.text,
  before: s.nullable(s.record),
  after: s.nullable(s.record),
  at: s.text,
});
const detailSchema = s.shape({
  ...opportunityFields,
  history: s.array(auditSchema),
  trace_excerpt: s.nullable(s.text),
});
const userSchema = s.shape({
  id: s.text,
  email: s.text,
  display_name: s.nullable(s.text),
  role: roleSchema,
  email_verified: s.boolean,
  disabled: s.boolean,
  created_at: s.text,
  scans_last_30_days: s.number,
});
const collectionSchema = s.shape({
  id: s.text,
  slug: s.text,
  title: s.text,
  intro: s.text,
  audience: audienceSchema,
  filter: s.nullable(s.record),
  item_ids: s.array(s.text),
  position: s.number,
  published: s.boolean,
});
const siteSchema = s.shape({
  hero_title: s.text,
  hero_subtitle: s.text,
  announcement: s.nullable(
    s.shape({
      text: s.text,
      link: s.text,
      starts_on: s.nullable(s.text),
      ends_on: s.nullable(s.text),
    }),
  ),
});
const settingsSchema = s.shape({
  agent_default: s.shape({ status: statusSchema, audience: audienceSchema }),
  community_default: s.shape({ status: statusSchema }),
  auto_archive: s.boolean,
  member_scan_limits: s.shape({ per_hour: s.number, per_day: s.number }),
  scheduled_scans: s.shape({
    member_max: s.number,
    runs_per_hour: s.number,
    daily_token_budget: s.number,
  }),
  crawler: s.optional(
    s.shape({
      hours: s.number,
      max_sources: s.number,
      max_items_per_source: s.number,
      max_candidates_per_task: s.number,
      host_interval_seconds: s.number,
      page_cache_seconds: s.number,
    }),
  ),
  freshness: s.optional(
    s.shape({
      recheck_days: s.number,
      closing_days: s.number,
      closing_recheck_days: s.number,
      cycle_days: s.number,
      stale_days: s.number,
      max_checks: s.number,
      max_agent_checks: s.number,
    }),
  ),
});
const scheduleSchema = s.shape({
  id: s.text,
  audience: s.choice("member", "staff"),
  name: s.text,
  categories: s.array(s.text),
  region: s.text,
  focus: s.text,
  sites: s.array(s.text),
  interval_hours: s.number,
  paused: s.boolean,
  pause_reason: s.nullable(s.text),
  next_run_at: s.nullable(s.text),
  last_run_at: s.nullable(s.text),
  runs: s.number,
  last_run: s.nullable(
    s.shape({
      scan_id: s.text,
      status: s.text,
      created_at: s.text,
      new: s.number,
      updated: s.number,
    }),
  ),
  created_at: s.text,
});
export type ScanSchedule = ReturnType<typeof scheduleSchema>;
const schedulesSchema = s.shape({
  schedules: s.array(scheduleSchema),
  member_schedules: s.number,
  member_schedules_active: s.number,
  runs_last_7_days: s.number,
  tokens_today: s.number,
  run_as: s.nullable(s.text),
  intervals: s.array(s.number),
});
export type ScanScheduleInput = {
  name: string;
  categories: string[];
  region: string;
  focus: string;
  interval_hours: number;
  paused?: boolean;
};
export const sourceKindSchema = s.choice("rss", "sitemap", "listing");
const sourceSchema = s.shape({
  id: s.text,
  url: s.text,
  kind: sourceKindSchema,
  category_hints: s.array(s.text),
  enabled: s.boolean,
  proposed: s.boolean,
  last_crawled_at: s.nullable(s.text),
  next_crawl_at: s.text,
  crawl_requested: s.boolean,
  etag: s.text,
  last_modified: s.text,
  consecutive_failures: s.number,
  last_error: s.text,
  candidates_found: s.number,
  opportunities_saved: s.number,
  last_candidates: s.number,
  created_at: s.text,
});
export type Source = ReturnType<typeof sourceSchema>;
export type SourceInput = Pick<
  Source,
  "url" | "kind" | "category_hints" | "enabled"
>;
const scanTaskSchema = s.shape({
  id: s.text,
  task_type: s.text,
  target: s.nullable(s.text),
  status: s.text,
  error: s.nullable(s.text),
  final_text: s.nullable(s.text),
  log: s.array(s.record),
});
const scanSchema = s.shape({
  id: s.text,
  region: s.text,
  categories: s.array(s.text),
  focus: s.text,
  status: s.text,
  created_at: s.text,
  opportunities_added: s.number,
  owner_email: s.optional(s.nullable(s.text)),
  tasks: s.optional(s.array(scanTaskSchema)),
});
const reportSchema = s.shape({
  id: s.text,
  opportunity_id: s.text,
  reason: s.text,
  email: s.optional(s.nullable(s.text)),
  resolved: s.boolean,
  created_at: s.text,
});
export type PublicOpportunity = {
  [K in keyof typeof publicFields]: ReturnType<(typeof publicFields)[K]>;
};
export type MemberOpportunity = {
  [K in keyof typeof memberFields]: ReturnType<(typeof memberFields)[K]>;
};
export type AdminOpportunity = ReturnType<typeof opportunitySchema>;
export type OpportunityDetail = ReturnType<typeof detailSchema>;
export type AuditEntry = ReturnType<typeof auditSchema>;
export type StaffUser = ReturnType<typeof userSchema>;
export type Collection = ReturnType<typeof collectionSchema>;
export type SiteContent = ReturnType<typeof siteSchema>;
export type Settings = ReturnType<typeof settingsSchema>;
export type DuplicatePair = ReturnType<typeof duplicatePairSchema>;
export type OrganizationAlias = ReturnType<typeof aliasSchema>;
export type Scan = ReturnType<typeof scanSchema>;
export type Report = ReturnType<typeof reportSchema>;
export type OpportunityInput = Pick<
  AdminOpportunity,
  | "title"
  | "slug"
  | "organization"
  | "category"
  | "kind"
  | "summary"
  | "eligibility"
  | "benefits"
  | "location"
  | "countries"
  | "requirements"
  | "tags"
  | "deadline"
  | "deadline_date"
  | "rolling"
  | "link"
  | "source_url"
  | "verified_at"
  | "status"
  | "audience"
  | "featured_rank"
  | "editor_note"
  | "review_reason"
>;
export type CollectionInput = Omit<Collection, "id">;
export type BulkAction =
  "publish_public" | "publish_members" | "archive" | "hide" | "to_review";
export type OpportunityQuery = {
  q?: string;
  status?: Status;
  audience?: Audience;
  review_reason?: string;
  category?: string;
  kind?: string;
  source?: string;
  sort?: "updated" | "deadline" | "created";
  limit?: number;
  offset?: number;
};
export type ScanRequest = {
  categories: string[];
  region: string;
  focus: string;
};
const tokensSchema = s.shape({ access_token: s.text, refresh_token: s.text });
const loginSchema = s.shape({
  access_token: s.text,
  refresh_token: s.text,
  user: userSchema,
});
const refreshSchema = s.shape({ user: userSchema, tokens: tokensSchema });
export const REFRESH_KEY = "blesser.admin.refresh_token";
let accessToken: string | null = null;
let refreshFlight: Promise<void> | null = null;
let sessionVersion = 0;
let sessionUser: StaffUser | null = null;
const listeners = new Set<() => void>();
export const subscribeSession = (listener: () => void) => {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
};
export const getSessionUser = () => sessionUser;
export const getAccessToken = () => accessToken;
function storedRefresh(): string | null {
  try {
    return localStorage.getItem(REFRESH_KEY);
  } catch {
    return null;
  }
}
function saveSession(
  user: StaffUser,
  tokens: { access_token: string; refresh_token: string },
) {
  accessToken = tokens.access_token;
  sessionUser = user;
  try {
    localStorage.setItem(REFRESH_KEY, tokens.refresh_token);
  } catch {
    /* Storage may be unavailable in private browsing. */
  }
  listeners.forEach((listener) => listener());
}
export function clearSession() {
  sessionVersion++;
  accessToken = null;
  sessionUser = null;
  try {
    localStorage.removeItem(REFRESH_KEY);
  } catch {
    /* Storage may be unavailable in private browsing. */
  }
  listeners.forEach((listener) => listener());
}
export class ApiError extends Error {
  readonly status: number;
  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}
export function errorMessage(error: unknown): string {
  return error instanceof Error
    ? error.message
    : "The request failed. Try again.";
}
async function responseError(response: Response): Promise<ApiError> {
  const raw = await response.text();
  let message = `The request failed (${response.status}). Try again.`;
  try {
    const value = s.record(JSON.parse(raw));
    if (typeof value.detail === "string") message = value.detail;
    else if (
      typeof value.detail === "object" &&
      value.detail !== null &&
      "message" in value.detail &&
      typeof value.detail.message === "string"
    )
      message = value.detail.message;
    else if (Array.isArray(value.detail))
      message = value.detail
        .map((item: unknown) => {
          const issue = s.record(item);
          return `${Array.isArray(issue.loc) ? issue.loc.join(" / ") : "Field"}: ${s.text(issue.msg)}`;
        })
        .join(". ");
  } catch {
    /* Non-JSON upstream errors use the actionable fallback. */
  }
  return new ApiError(response.status, message);
}
const base = import.meta.env.VITE_API_URL ?? "";
async function raw(
  path: string,
  method: string,
  body?: unknown,
  authenticated = true,
): Promise<Response> {
  const headers = new Headers({ "Content-Type": "application/json" });
  if (authenticated && accessToken)
    headers.set("Authorization", `Bearer ${accessToken}`);
  return fetch(`${base}/api/admin${path}`, {
    method,
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
  });
}
export async function refreshSession(): Promise<void> {
  if (refreshFlight) return refreshFlight;
  const token = storedRefresh();
  if (!token) {
    clearSession();
    throw new ApiError(401, "Your session ended. Sign in again.");
  }
  const version = sessionVersion;
  refreshFlight = (async () => {
    const response = await raw(
      "/auth/refresh",
      "POST",
      { refresh_token: token },
      false,
    );
    if (!response.ok) {
      if (
        version === sessionVersion &&
        (response.status === 401 || response.status === 403)
      )
        clearSession();
      throw await responseError(response);
    }
    const result = refreshSchema(await response.json());
    if (version === sessionVersion) saveSession(result.user, result.tokens);
  })().finally(() => {
    refreshFlight = null;
  });
  return refreshFlight;
}
async function request<T>(
  path: string,
  decode: s.Decoder<T>,
  method = "GET",
  body?: unknown,
): Promise<T> {
  const attemptedToken = accessToken;
  let response = await raw(path, method, body);
  if (response.status === 401) {
    if (attemptedToken === accessToken) await refreshSession();
    if (!accessToken)
      throw new ApiError(401, "Your session ended. Sign in again.");
    response = await raw(path, method, body);
  }
  if (!response.ok) {
    if (response.status === 401) clearSession();
    throw await responseError(response);
  }
  const bodyText = await response.text();
  return decode(bodyText ? JSON.parse(bodyText) : undefined);
}
export async function login(email: string, password: string) {
  const response = await raw("/auth/login", "POST", { email, password }, false);
  if (!response.ok) throw await responseError(response);
  const result = loginSchema(await response.json());
  if (
    result.user.role === "member" ||
    !result.user.email_verified ||
    result.user.disabled
  )
    throw new ApiError(403, "Use a verified staff account to sign in.");
  sessionVersion++;
  saveSession(result.user, result);
}
export async function logout() {
  const token = storedRefresh();
  clearSession();
  if (token) {
    const response = await raw(
      "/auth/logout",
      "POST",
      { refresh_token: token },
      false,
    );
    if (!response.ok) throw await responseError(response);
  }
}
function query(params: object): string {
  const result = new URLSearchParams();
  for (const [key, value] of Object.entries(params))
    if (value !== undefined && value !== null && value !== "")
      result.set(key, String(value));
  return result.size ? `?${result}` : "";
}
const page = <T>(decode: s.Decoder<T>) =>
  s.shape({ items: s.array(decode), total: s.number });
const idPath = (id: string) => encodeURIComponent(id);
export const me = () => request("/auth/me", userSchema);
export const opportunities = (params: OpportunityQuery = {}) =>
  request(`/opportunities${query(params)}`, page(opportunitySchema));
export const counts = () =>
  request(
    "/opportunities/counts",
    s.shape({
      in_review: s.number,
      members_only: s.number,
      published_public: s.number,
      archived: s.number,
      hidden: s.number,
      draft: s.number,
    }),
  );
export const opportunity = (id: string) =>
  request(`/opportunities/${idPath(id)}`, detailSchema);
export const createOpportunity = (body: OpportunityInput) =>
  request("/opportunities", opportunitySchema, "POST", body);
export const updateOpportunity = (
  id: string,
  body: Partial<OpportunityInput>,
) => request(`/opportunities/${idPath(id)}`, opportunitySchema, "PATCH", body);
export const bulkOpportunities = (ids: string[], action: BulkAction) =>
  request("/opportunities/bulk", s.shape({ updated: s.number }), "POST", {
    ids,
    action,
  });
export const mergeOpportunity = (id: string, into_id: string) =>
  request(`/opportunities/${idPath(id)}/merge`, opportunitySchema, "POST", {
    into_id,
  });
export const duplicates = () =>
  request("/opportunities/duplicates", s.array(duplicatePairSchema));
export const dismissDuplicate = (pair: {
  first_id: string;
  second_id: string;
}) =>
  request("/opportunities/duplicates/dismiss", () => undefined, "POST", pair);
export const organizationAliases = () =>
  request("/organization-aliases", s.array(aliasSchema));
export const saveOrganizationAlias = (body: OrganizationAlias) =>
  request("/organization-aliases", aliasSchema, "PUT", body);
export const deleteOrganizationAlias = (alias: string) =>
  request(`/organization-aliases/${idPath(alias)}`, () => undefined, "DELETE");
export const reverifyOpportunity = (id: string) =>
  request(
    `/opportunities/${idPath(id)}/reverify`,
    s.shape({ scan_id: s.text }),
    "POST",
  );
export const reports = () => request("/reports", s.array(reportSchema));
export const resolveReport = (id: string) =>
  request(`/reports/${idPath(id)}`, reportSchema, "PATCH", { resolved: true });
export const collections = () =>
  request("/collections", s.array(collectionSchema));
export const createCollection = (body: CollectionInput) =>
  request("/collections", collectionSchema, "POST", body);
export const updateCollection = (id: string, body: CollectionInput) =>
  request(`/collections/${idPath(id)}`, collectionSchema, "PATCH", body);
export const deleteCollection = (id: string) =>
  request(`/collections/${idPath(id)}`, () => undefined, "DELETE");
export const site = () => request("/site", siteSchema);
export const updateSite = (body: SiteContent) =>
  request("/site", siteSchema, "PUT", body);
export const settings = () => request("/settings", settingsSchema);
export const updateSettings = (body: Settings) =>
  request("/settings", settingsSchema, "PUT", body);
export const scans = (params: { limit: number; offset: number }) =>
  request(`/scans${query(params)}`, s.array(scanSchema));
export const startScan = (body: ScanRequest) =>
  request("/scans", scanSchema, "POST", body);
export const users = (params: {
  q?: string;
  role?: Role;
  limit: number;
  offset: number;
}) => request(`/users${query(params)}`, page(userSchema));
export const updateUser = (
  id: string,
  body: { role?: Role; disabled?: boolean },
) => request(`/users/${idPath(id)}`, userSchema, "PATCH", body);
export const audit = (params: {
  actor_id?: string;
  entity_type?: string;
  entity_id?: string;
  action?: string;
  limit: number;
  offset: number;
}) => request(`/audit${query(params)}`, page(auditSchema));

export const scanSchedules = () => request("/scan-schedules", schedulesSchema);
export const createScanSchedule = (body: ScanScheduleInput) =>
  request("/scan-schedules", scheduleSchema, "POST", body);
export const updateScanSchedule = (
  id: string,
  body: Partial<ScanScheduleInput>,
) => request(`/scan-schedules/${idPath(id)}`, scheduleSchema, "PATCH", body);
export const deleteScanSchedule = (id: string) =>
  request(`/scan-schedules/${idPath(id)}`, () => undefined, "DELETE");

export const sources = () => request("/sources", s.array(sourceSchema));
export const createSource = (body: SourceInput) =>
  request("/sources", sourceSchema, "POST", body);
export const updateSource = (id: string, body: Partial<SourceInput>) =>
  request(`/sources/${idPath(id)}`, sourceSchema, "PATCH", body);
export const deleteSource = (id: string) =>
  request(`/sources/${idPath(id)}`, () => undefined, "DELETE");
export const crawlSource = (id: string) =>
  request(`/sources/${idPath(id)}/crawl`, sourceSchema, "POST");
