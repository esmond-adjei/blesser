import { useQuery } from "@tanstack/react-query"
import { API_BASE, ApiError, getAccessToken, parseDetail, refreshAccessToken, request } from "./api"
import type { Answer, AnswerInput, Correction, DocumentPatch, KitDocument, Profile, ProfileInput, Project, ProjectInput, StorageUsage } from "./kitTypes"

const json = (method: string, body?: unknown): RequestInit => ({ method, body: body === undefined ? undefined : JSON.stringify(body) })
const qs = (params: Record<string, string | null | undefined>) => {
  const q = new URLSearchParams()
  for (const [k, v] of Object.entries(params)) if (v) q.set(k, v)
  const text = q.toString()
  return text ? `?${text}` : ""
}

export const getKitProfile = (reveal = false) => request<Profile>(`/api/app/profile${reveal ? "?reveal=1" : ""}`)
export const putKitProfile = (body: ProfileInput) => request<Profile>("/api/app/profile", json("PUT", body))

export const listProjects = () => request<Project[]>("/api/app/projects")
export const getProject = (id: string) => request<Project>(`/api/app/projects/${encodeURIComponent(id)}`)
export const createProject = (body: ProjectInput) => request<Project>("/api/app/projects", json("POST", body))
export const putProject = (id: string, body: ProjectInput) => request<Project>(`/api/app/projects/${encodeURIComponent(id)}`, json("PUT", body))
export const deleteProject = (id: string) => request<unknown>(`/api/app/projects/${encodeURIComponent(id)}`, json("DELETE"))

export const listDocuments = (params: { kind?: string; project_id?: string } = {}) =>
  request<KitDocument[]>(`/api/app/documents${qs(params)}`)
export const patchDocument = (id: string, body: DocumentPatch) => request<KitDocument>(`/api/app/documents/${encodeURIComponent(id)}`, json("PATCH", body))
export const deleteDocument = (id: string) => request<unknown>(`/api/app/documents/${encodeURIComponent(id)}`, json("DELETE"))
export const documentUsage = () => request<StorageUsage>("/api/app/documents/usage")

export const listAnswers = (params: { q?: string; project_id?: string } = {}) => request<Answer[]>(`/api/app/answers${qs(params)}`)
export const createAnswer = (body: AnswerInput) => request<Answer>("/api/app/answers", json("POST", body))
export const putAnswer = (id: string, body: AnswerInput) => request<Answer>(`/api/app/answers/${encodeURIComponent(id)}`, json("PUT", body))
export const deleteAnswer = (id: string) => request<unknown>(`/api/app/answers/${encodeURIComponent(id)}`, json("DELETE"))

export const listCorrections = () => request<Correction[]>("/api/app/autofill/corrections")
export const deleteCorrection = (id: string) => request<unknown>(`/api/app/autofill/corrections/${encodeURIComponent(id)}`, json("DELETE"))

export type UploadInput = { file: File; kind: string; title: string; project_ids?: string[]; is_default?: boolean }

/** Multipart upload over XHR so the caller sees progress (0..1); retries once after a token refresh. */
export function uploadDocument(input: UploadInput, onProgress: (fraction: number) => void, signal?: AbortSignal): Promise<KitDocument> {
  const form = new FormData()
  form.append("file", input.file)
  form.append("kind", input.kind)
  form.append("title", input.title)
  for (const id of input.project_ids ?? []) form.append("project_ids", id)
  if (input.is_default) form.append("is_default", "true")

  const send = () =>
    new Promise<{ status: number; text: string }>((resolve, reject) => {
      const xhr = new XMLHttpRequest()
      xhr.open("POST", `${API_BASE}/api/app/documents`)
      const token = getAccessToken()
      if (token) xhr.setRequestHeader("Authorization", `Bearer ${token}`)
      xhr.upload.onprogress = (e) => e.lengthComputable && onProgress(e.loaded / e.total)
      xhr.onload = () => resolve({ status: xhr.status, text: xhr.responseText })
      xhr.onerror = () => reject(new Error("The upload didn't reach Blesser. Check your connection."))
      xhr.onabort = () => reject(new DOMException("Upload cancelled", "AbortError"))
      signal?.addEventListener("abort", () => xhr.abort(), { once: true })
      xhr.send(form)
    })

  return (async () => {
    let res = await send()
    if (res.status === 401 && (await refreshAccessToken())) {
      onProgress(0)
      res = await send()
    }
    if (res.status < 200 || res.status >= 300) {
      const { message, detail } = parseDetail(res.text)
      throw new ApiError(res.status, res.text, (res.status === 413 ? "That file is too large." : message || `Upload failed (${res.status})`).slice(0, 500), detail)
    }
    return JSON.parse(res.text) as KitDocument
  })()
}

/** Fetches the file with the member token and hands it to the browser as a download. */
export async function downloadDocument(doc: Pick<KitDocument, "id" | "filename">): Promise<void> {
  const url = `${API_BASE}/api/app/documents/${encodeURIComponent(doc.id)}/download`
  const send = () => {
    const token = getAccessToken()
    return fetch(url, { headers: token ? { Authorization: `Bearer ${token}` } : {} })
  }
  let res = await send()
  if (res.status === 401 && (await refreshAccessToken())) res = await send()
  if (!res.ok) {
    const text = await res.text().catch(() => "")
    throw new ApiError(res.status, text, parseDetail(text).message.slice(0, 500) || "Couldn't download that file")
  }
  const href = URL.createObjectURL(await res.blob())
  const link = document.createElement("a")
  link.href = href
  link.download = doc.filename
  link.click()
  window.setTimeout(() => URL.revokeObjectURL(href), 1000)
}

export const kitKeys = {
  profile: ["kit", "profile"] as const,
  projects: ["kit", "projects"] as const,
  project: (id: string) => ["kit", "projects", id] as const,
  documents: ["kit", "documents"] as const,
  usage: ["kit", "documents", "usage"] as const,
  answers: (q: string, projectId: string) => ["kit", "answers", q, projectId] as const,
  corrections: ["kit", "corrections"] as const,
}

export const useKitProfile = () => useQuery({ queryKey: kitKeys.profile, queryFn: () => getKitProfile(), staleTime: Infinity })
export const useProjects = () => useQuery({ queryKey: kitKeys.projects, queryFn: listProjects })
export const useProject = (id: string) => useQuery({ queryKey: kitKeys.project(id), queryFn: () => getProject(id), staleTime: Infinity })
export const useDocuments = () => useQuery({ queryKey: kitKeys.documents, queryFn: () => listDocuments() })
export const useUsage = () => useQuery({ queryKey: kitKeys.usage, queryFn: documentUsage })
export const useAnswers = (q: string, projectId: string) =>
  useQuery({ queryKey: kitKeys.answers(q, projectId), queryFn: () => listAnswers({ q, project_id: projectId }), placeholderData: (prev) => prev })
export const useCorrections = () => useQuery({ queryKey: kitKeys.corrections, queryFn: listCorrections })
