/** Application tracker hooks and labels. */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import * as api from "./api"
import type { Application, ApplicationInput, ApplicationStatus } from "./types"

export const STATUSES: { value: ApplicationStatus; label: string }[] = [
  { value: "saved", label: "Saved" },
  { value: "preparing", label: "Preparing" },
  { value: "submitted", label: "Submitted" },
  { value: "interview", label: "Interview" },
  { value: "accepted", label: "Accepted" },
  { value: "rejected", label: "Not this time" },
]

export const STATUS_LABEL = Object.fromEntries(STATUSES.map((s) => [s.value, s.label])) as Record<
  ApplicationStatus,
  string
>

/** Still working towards the deadline. */
export const OPEN_STATUSES: ApplicationStatus[] = ["saved", "preparing"]

export function useApplications() {
  return useQuery({ queryKey: ["applications"], queryFn: api.listApplications })
}

/** One application, fetched when its drawer or page opens. */
export function useApplication(id: string | undefined) {
  return useQuery({
    queryKey: ["application", id],
    queryFn: () => api.getApplication(id as string),
    enabled: !!id,
    staleTime: 60_000,
  })
}

export function useApplicationMutations() {
  const client = useQueryClient()
  const refresh = () => {
    void client.invalidateQueries({ queryKey: ["applications"] })
    void client.invalidateQueries({ queryKey: ["application"] })
    void client.invalidateQueries({ queryKey: ["opportunities", "tracked"] })
  }
  const create = useMutation({
    mutationFn: (body: ApplicationInput & { title: string }) => api.createApplication(body),
    onSuccess: refresh,
  })
  const update = useMutation({
    mutationFn: ({ id, body }: { id: string; body: ApplicationInput }) => api.updateApplication(id, body),
    // Optimistic: status changes and ticks move at once.
    onMutate: async ({ id, body }) => {
      await client.cancelQueries({ queryKey: ["applications"] })
      await client.cancelQueries({ queryKey: ["application", id] })
      const before = client.getQueryData<Application[]>(["applications"])
      if (before) {
        client.setQueryData<Application[]>(
          ["applications"],
          before.map((a) => (a.id === id ? ({ ...a, ...body } as Application) : a)),
        )
      }
      const beforeOne = client.getQueryData<Application>(["application", id])
      if (beforeOne) client.setQueryData<Application>(["application", id], { ...beforeOne, ...body } as Application)
      return { before, beforeOne }
    },
    onError: (_err, { id }, context) => {
      if (context?.before) client.setQueryData(["applications"], context.before)
      if (context?.beforeOne) client.setQueryData(["application", id], context.beforeOne)
    },
    onSettled: refresh,
  })
  const remove = useMutation({ mutationFn: (id: string) => api.deleteApplication(id), onSuccess: refresh })
  return { create, update, remove }
}
