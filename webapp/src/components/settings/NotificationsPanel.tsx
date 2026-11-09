import * as React from "react"
import { useQuery, useQueryClient } from "@tanstack/react-query"
import { BellRing, Smartphone } from "lucide-react"
import * as api from "../../lib/api"
import { browserTimezone, currentSubscription, disablePush, enablePush, permission, pushSupport } from "../../lib/push"
import { toastError, toastInfo, toastSuccess } from "../../lib/toast"
import { formatAgo } from "../../lib/format"
import { Button, Input } from "@blesser/ui"
import { SkeletonStack } from "../ui/feedback"
import { useAutosave } from "../../lib/autosave"
import { SettingRow, SettingsGroup, Switch } from "./controls"

const CHANNELS: { id: api.NotificationChannel; label: string }[] = [
  { id: "inbox", label: "Inbox" },
  { id: "push", label: "Push" },
  { id: "email", label: "Email" },
]

export function NotificationsPanel() {
  const qc = useQueryClient()
  const track = useAutosave()
  const prefs = useQuery({ queryKey: ["notification-prefs"], queryFn: api.getNotificationPreferences })

  async function save(patch: api.NotificationPreferencesPatch) {
    const next = await track(api.updateNotificationPreferences(patch))
    if (!next) return
    qc.setQueryData(["notification-prefs"], next)
    void qc.invalidateQueries({ queryKey: ["notifications"] })
  }

  return (
    <>
      <SettingsGroup title="What to notify you about" description="Choose where each update reaches you.">
        {!prefs.data ? (
          <SkeletonStack aria-label="Loading notification settings" aria-busy="true" className="space-y-3 p-4" blocks={["h-10", "h-10", "h-10"]} />
        ) : (
          <>
            <table className="w-full text-callout">
              <thead>
                <tr className="text-left text-footnote text-ink-secondary">
                  <th scope="col" className="py-2.5 pr-3 pl-4 font-medium sm:pl-5">Update</th>
                  {CHANNELS.map((channel) => (
                    <th key={channel.id} scope="col" className="w-14 py-2.5 text-center font-medium last:pr-3 sm:w-20 sm:last:pr-5">{channel.label}</th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-separator border-t border-separator">
                {prefs.data.kinds.map((kind) => (
                  <tr key={kind.kind}>
                    <th scope="row" className="py-3.5 pr-3 pl-4 text-left align-top font-normal sm:pl-5">
                      <span className="block font-medium text-ink">{kind.label}</span>
                      <span className="mt-0.5 block text-footnote text-ink-secondary">{kind.description}</span>
                    </th>
                    {CHANNELS.map((channel) => (
                      <td key={channel.id} className="py-3.5 text-center align-top last:pr-3 sm:last:pr-5">
                        <span className="inline-flex pt-0.5">
                          <Switch checked={kind.channels[channel.id]} label={`${kind.label}: ${channel.label}`}
                            onChange={(on) => save({ channels: { [kind.kind]: { [channel.id]: on } } })} />
                        </span>
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="px-4 py-3 text-footnote text-ink-secondary sm:px-5">
              Push and email carry a short update and a link back here. Your notes and application details stay private. Email goes to verified addresses only.
            </p>
          </>
        )}
      </SettingsGroup>

      {prefs.data ? <QuietHours prefs={prefs.data} onSave={save} /> : null}

      {prefs.data ? (
        <SettingsGroup title="Email digest">
          <SettingRow
            label="Daily digest"
            description="One email each morning listing the last day's unread notifications."
            control={<Switch checked={prefs.data.email_digest} label="Daily email digest" onChange={(on) => save({ email_digest: on })} />}
          />
        </SettingsGroup>
      ) : null}

      <ThisBrowser />
    </>
  )
}

function QuietHours({
  prefs,
  onSave,
}: {
  prefs: api.NotificationPreferences
  onSave: (patch: api.NotificationPreferencesPatch) => Promise<void>
}) {
  const [start, setStart] = React.useState(prefs.quiet_start ?? "")
  const [end, setEnd] = React.useState(prefs.quiet_end ?? "")
  const [zone, setZone] = React.useState(prefs.timezone ?? browserTimezone() ?? "UTC")
  const [zones] = React.useState(listZones)
  const listId = React.useId()
  const zoneId = React.useId()

  const saveWindow = (nextStart: string, nextEnd: string) => {
    if (nextStart === (prefs.quiet_start ?? "") && nextEnd === (prefs.quiet_end ?? "")) return
    void onSave({ quiet_start: nextStart || null, quiet_end: nextEnd || null })
  }

  return (
    <SettingsGroup title="Quiet hours" description="Push and email wait until the window ends. The inbox keeps updating.">
      <SettingRow
        stack
        label="Pause push and email"
        description="Leave both times empty to turn quiet hours off."
        control={
          <div className="flex items-center gap-2">
            <Input type="time" aria-label="Quiet hours start" className="h-control-sm w-[7.5rem] text-callout" value={start}
              onChange={(e) => setStart(e.target.value)} onBlur={() => saveWindow(start, end)} />
            <span className="text-footnote text-ink-secondary">to</span>
            <Input type="time" aria-label="Quiet hours end" className="h-control-sm w-[7.5rem] text-callout" value={end}
              onChange={(e) => setEnd(e.target.value)} onBlur={() => saveWindow(start, end)} />
            {start || end ? (
              <Button size="sm" variant="quiet" onClick={() => { setStart(""); setEnd(""); saveWindow("", "") }}>Clear</Button>
            ) : null}
          </div>
        }
      />
      <SettingRow
        stack
        htmlFor={zoneId}
        label="Timezone"
        description="Quiet hours and deadline reminders (14, 7 and 1 days before, from 8:00) follow this clock."
        control={
          <>
            <Input
              id={zoneId}
              className="h-control-sm w-full text-callout sm:w-56"
              list={listId}
              value={zone}
              onChange={(e) => setZone(e.target.value)}
              onBlur={() => {
                if (zone && zone !== prefs.timezone) void onSave({ timezone: zone })
              }}
            />
            <datalist id={listId}>
              {zones.map((z) => (
                <option key={z} value={z} />
              ))}
            </datalist>
          </>
        }
      />
    </SettingsGroup>
  )
}

function listZones(): string[] {
  try {
    return (Intl as unknown as { supportedValuesOf?: (k: string) => string[] }).supportedValuesOf?.("timeZone") ?? []
  } catch {
    return []
  }
}

function ThisBrowser() {
  const qc = useQueryClient()
  const config = useQuery({ queryKey: ["push-config"], queryFn: api.getPushConfig })
  const devices = useQuery({ queryKey: ["push-devices"], queryFn: api.listPushDevices })
  // This browser's own subscription, read from the service worker.
  const own = useQuery({
    queryKey: ["push-endpoint"],
    queryFn: async () => (await currentSubscription())?.endpoint ?? null,
    staleTime: 0,
  })
  const endpoint = own.data
  const [busy, setBusy] = React.useState(false)
  const support = pushSupport()

  const refresh = () =>
    Promise.all([
      qc.invalidateQueries({ queryKey: ["push-endpoint"] }),
      qc.invalidateQueries({ queryKey: ["push-devices"] }),
    ])

  // Subscribed here but missing on the server (removed elsewhere): offer
  // to turn it on again rather than claiming it works.
  const known = devices.data?.some((d) => d.endpoint === endpoint) ?? false
  const subscribed = !!endpoint && known

  async function turnOn() {
    setBusy(true)
    try {
      const result = await enablePush()
      if (result === "ok") toastSuccess("Push notifications are on for this browser")
      else if (result === "denied") toastInfo("Notifications are blocked for this site. Allow them in the browser's site settings.")
      else if (result === "server-off") toastInfo("Push isn't set up on this server yet.")
      else toastInfo("This browser can't receive push notifications.")
    } catch (err) {
      toastError(err, "Couldn't turn on push")
    } finally {
      setBusy(false)
      await refresh()
    }
  }

  async function remove(device: api.PushDevice) {
    try {
      if (device.endpoint === endpoint) await disablePush()
      else await api.removePushSubscription(device.endpoint)
    } catch (err) {
      toastError(err, "Couldn't remove")
    }
    await refresh()
  }

  async function test() {
    try {
      const result = await api.sendTestNotification()
      void qc.invalidateQueries({ queryKey: ["notifications"] })
      if (!result.push_enabled) toastInfo("Sent to your inbox. Push isn't set up on this server.")
      else if (result.pushed === 0) toastInfo("Sent to your inbox. No device has push turned on.")
      else toastSuccess(`Sent to your inbox and ${result.pushed} device${result.pushed === 1 ? "" : "s"}`)
    } catch (err) {
      toastError(err, "Couldn't send")
    }
  }

  async function testEmail() {
    try {
      const result = await api.sendTestEmail()
      if (!result.sent) toastError(new Error(`Couldn't send to ${result.to}. Check the server's SMTP settings and logs.`))
      else if (result.backend === "console") toastInfo(`Mail isn't set up on this server: the test email to ${result.to} was printed to the server log.`)
      else toastSuccess(`Test email sent to ${result.to}`)
    } catch (err) {
      toastError(err, "Couldn't send")
    }
  }

  let status: string
  if (config.data && !config.data.enabled) status = "Push isn't set up on this server (the inbox and email still work)."
  else if (support === "ios-needs-home-screen")
    status = "On iPhone and iPad, push works only once Blesser is on your Home Screen: tap Share, then Add to Home Screen, and open it from there (iOS 16.4 or later)."
  else if (support === "unsupported") status = "This browser can't receive push notifications."
  else if (permission() === "denied") status = "Notifications are blocked for this site. Allow them in the browser's site settings, then turn push on."
  else if (subscribed) status = "This browser gets push notifications."
  else status = "Push is off for this browser."

  const canEnable = support === "supported" && config.data?.enabled && permission() !== "denied" && !subscribed

  const others = (devices.data ?? []).filter((d) => d.endpoint !== endpoint)

  return (
    <>
      <SettingsGroup title="Push notifications" description="Push reaches a browser or phone even when Blesser isn't open.">
        {config.isLoading || devices.isLoading || own.isLoading ? (
          <SkeletonStack aria-label="Loading push settings" aria-busy="true" className="space-y-3 p-4" blocks={["h-10"]} />
        ) : (
          <SettingRow
            stack
            label="This browser"
            description={status}
            control={
              subscribed ? (
                <Button
                  size="sm"
                  variant="secondary"
                  onClick={() => {
                    const mine = devices.data?.find((d) => d.endpoint === endpoint)
                    if (mine) void remove(mine)
                  }}
                >
                  Turn off
                </Button>
              ) : canEnable ? (
                <Button size="sm" variant="secondary" onClick={turnOn} disabled={busy} icon={<BellRing />}>
                  Turn on
                </Button>
              ) : null
            }
          />
        )}
        {others.map((d) => (
          <SettingRow
            key={d.id}
            label={<span className="flex items-center gap-2"><Smartphone className="size-4 shrink-0 text-ink-tertiary" aria-hidden="true" />{deviceName(d.user_agent)}</span>}
            description={`Added ${formatAgo(d.created_at)}`}
            control={<Button size="sm" variant="quiet" onClick={() => remove(d)}>Remove</Button>}
          />
        ))}
      </SettingsGroup>

      <SettingsGroup title="Check delivery" description="Tests send right away; quiet hours don't apply.">
        <SettingRow
          stack
          label="Test notification"
          description="Goes to your inbox and every device with push on."
          control={<Button size="sm" variant="secondary" onClick={test}>Send test</Button>}
        />
        <SettingRow
          stack
          label="Test email"
          description="Goes to your verified address, so you can check email notifications arrive."
          control={<Button size="sm" variant="secondary" onClick={testEmail}>Send test email</Button>}
        />
      </SettingsGroup>
    </>
  )
}

function deviceName(userAgent: string | null): string {
  const ua = userAgent ?? ""
  const browser = /Edg\//.test(ua) ? "Edge" : /Firefox\//.test(ua) ? "Firefox" : /Chrome\//.test(ua) ? "Chrome" : /Safari\//.test(ua) ? "Safari" : "Browser"
  const os = /iPhone|iPad/.test(ua) ? "iOS" : /Android/.test(ua) ? "Android" : /Mac OS X/.test(ua) ? "macOS" : /Windows/.test(ua) ? "Windows" : /Linux/.test(ua) ? "Linux" : ""
  return os ? `${browser} on ${os}` : browser
}
