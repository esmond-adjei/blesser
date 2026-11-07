/** Agent admin via the registry API. Tool switches apply on the next turn;
 * disabled tools leave the model's list and dispatch rejects them. */
import * as React from "react"
import { useQuery, useQueryClient } from "@tanstack/react-query"
import * as api from "./api"
import type { AgentTask, AgentTool, AgentToolGroup } from "./types"

const TOOLS_KEY = ["agent-tools"]
const GROUPS_KEY = ["agent-tool-groups"]
const TASKS_KEY = ["agent-tasks"]

export function useAgentTools() {
  const qc = useQueryClient()
  const query = useQuery({ queryKey: TOOLS_KEY, queryFn: api.listAgentTools })
  // Static per deploy (defined in code), so cache it for the session.
  const groupsQuery = useQuery({
    queryKey: GROUPS_KEY,
    queryFn: api.listAgentToolGroups,
    staleTime: Infinity,
  })
  const refresh = React.useCallback(
    () => qc.invalidateQueries({ queryKey: TOOLS_KEY }),
    [qc],
  )
  const update = React.useCallback(
    async (scope: string, name: string, body: { enabled?: boolean; confirm_required?: boolean }) => {
      await api.updateAgentTool(scope, name, body)
      await refresh()
    },
    [refresh],
  )
  const updateGroup = React.useCallback(
    async (scope: string, group: string, body: { enabled?: boolean; confirm_required?: boolean }) => {
      await api.updateAgentToolGroup(scope, group, body)
      await refresh()
    },
    [refresh],
  )
  return {
    tools: query.data ?? [],
    groups: groupsQuery.data ?? [],
    isLoading: query.isLoading,
    isError: query.isError,
    update,
    updateGroup,
    refresh,
  }
}

export type ToolEntry =
  | { kind: "tool"; tool: AgentTool }
  | {
      kind: "group"
      group: AgentToolGroup
      members: AgentTool[]
      state: "on" | "off" | "mixed"
    }

/** One scope's tools as display entries: groups with 2+ members collapse into
 * one entry at the first member's position. Shared by composer and settings. */
export function groupTools(tools: AgentTool[], groups: AgentToolGroup[]): ToolEntry[] {
  const byId = new Map(groups.map((g) => [g.id, g]))
  const seen = new Set<string>()
  const out: ToolEntry[] = []
  for (const tool of tools) {
    const group = tool.group ? byId.get(tool.group) : undefined
    if (!group) {
      out.push({ kind: "tool", tool })
      continue
    }
    if (seen.has(group.id)) continue
    seen.add(group.id)
    const members = tools.filter((t) => t.group === group.id)
    if (members.length < 2) {
      out.push({ kind: "tool", tool })
      continue
    }
    const on = members.filter((m) => m.enabled).length
    out.push({
      kind: "group",
      group,
      members,
      state: on === members.length ? "on" : on === 0 ? "off" : "mixed",
    })
  }
  return out
}

export function useAgentTasks() {
  const qc = useQueryClient()
  const query = useQuery({ queryKey: TASKS_KEY, queryFn: api.listAgentTasks })
  const refresh = React.useCallback(
    () => qc.invalidateQueries({ queryKey: TASKS_KEY }),
    [qc],
  )
  const update = React.useCallback(
    async (taskType: string, body: { enabled?: boolean; tools?: string[] }) => {
      await api.updateAgentTask(taskType, body)
      await refresh()
    },
    [refresh],
  )
  return { tasks: query.data ?? [], isLoading: query.isLoading, isError: query.isError, update, refresh }
}

export type { AgentTask, AgentTool }
