import * as React from "react"
import { useQuery, useQueryClient } from "@tanstack/react-query"
import { RefreshCw } from "lucide-react"
import { Button } from "@blesser/ui"
import * as api from "../../lib/api"
import { formatAgo, formatDate } from "../../lib/format"
import { toastError, toastSuccess } from "../../lib/toast"
import { SettingRow, SettingsGroup } from "./controls"

const KEY = ["extension-sessions"]

export function ConnectedBrowsers() {
  const client = useQueryClient()
  const sessions = useQuery({ queryKey: KEY, queryFn: api.listExtensionSessions })
  const [removing, setRemoving] = React.useState<string | null>(null)

  const disconnect = async (session: api.ExtensionSession) => {
    setRemoving(session.id)
    try {
      await api.revokeExtensionSession(session.id)
      client.setQueryData<api.ExtensionSession[]>(KEY, (list) => list?.filter((s) => s.id !== session.id))
      toastSuccess(`${session.name} disconnected`)
    } catch (err) {
      toastError(err, "Couldn't disconnect")
    } finally {
      setRemoving(null)
    }
  }

  return (
    <SettingsGroup title="Connected browsers" description="Browsers where the Blesser extension can fill forms from your Apply kit.">
      {sessions.isLoading ? (
        <div className="p-4 sm:px-5"><div className="h-10 animate-pulse rounded-sm bg-surface-sunk motion-reduce:animate-none" /></div>
      ) : sessions.isError ? (
        <SettingRow
          label="Connected browsers didn't load"
          description="Try again in a moment."
          control={<Button size="sm" variant="secondary" onClick={() => void sessions.refetch()} icon={<RefreshCw />}>Try again</Button>}
        />
      ) : !sessions.data?.length ? (
        <SettingRow label="No browsers connected" description="Install the Blesser extension in Chrome or Edge and press Connect in it." />
      ) : (
        sessions.data.map((session) => (
          <SettingRow
            key={session.id}
            stack
            label={session.name}
            description={
              <span title={formatDate(session.created_at)}>
                Connected {formatAgo(session.created_at)}. {session.last_used_at ? `Last used ${formatAgo(session.last_used_at)}` : "Not used yet"}
              </span>
            }
            control={
              <Button size="sm" variant="secondary" disabled={removing === session.id} onClick={() => void disconnect(session)}>
                Disconnect
              </Button>
            }
          />
        ))
      )}
    </SettingsGroup>
  )
}
