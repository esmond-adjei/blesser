import { useQuery } from "@tanstack/react-query"
import * as api from "./api"

export const SCHEDULES_KEY = ["scan-schedules"]

/** The member's weekly scans. */
export function useSchedules(enabled = true) {
  return useQuery({ queryKey: SCHEDULES_KEY, queryFn: api.listSchedules, enabled, staleTime: 30_000 })
}
