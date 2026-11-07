import * as React from "react"
import { useQuery, useQueryClient } from "@tanstack/react-query"
import { BellRing, Smartphone } from "lucide-react"
import * as api from "../../lib/api"
import { browserTimezone, currentSubscription, disablePush, enablePush, permission, pushSupport } from "../../lib/push"
import { toastError, toastInfo, toastSuccess } from "../../lib/toast"
import { formatAgo } from "../../lib/format"
import { Button } from "../ui/button"
import { Input } from "../ui/input"
import { Skeleton, SkeletonStack } from "../ui/feedback"
import { SettingRow, SettingSection, SettingsPanel, Switch } from "./controls"

const CHANNELS: { id: api.NotificationChannel; label: string }[] = [
  { id: "inbox", label: "Inbox" },
  { id: "push", label: "Push" },
  { id: "email", label: "Email" },
]

export function NotificationsPanel() {
  const qc = useQueryClient()
  const prefs = useQuery({ queryKey: ["notification-prefs"], queryFn: api.getNotificationPreferences })

  async function save(patch: api.NotificationPreferencesPatch) {
    try {
      const next = await api.updateNotificationPreferences(patch)
      qc.setQueryData(["notification-prefs"], next)
      void qc.invalidateQueries({ queryKey: ["notifications"] })
    } catch (err) {
      toastError(err, "Couldn't save")
    }
  }

  return (
    <SettingsPanel title="Notifications" description="Choose what you hear about, where it arrives and when to pause it.">

      <ThisBrowser />

      <SettingSection title="What to notify you about" description="Choose where each event reaches you: inbox, push or email.">
        {!prefs.data ? (
          <Skeleton className="my-3 h-40" />
        ) : (
          <div>
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left type-caption">
                  <th className="py-2 font-normal">Event</th>
                  {CHANNELS.map((channel) => (
                    <th key={channel.id} className="w-16 py-2 text-center font-normal sm:w-20">{channel.label}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {prefs.data.kinds.map((kind) => (
                  <tr key={kind.kind}>
                    <td className="py-3 pr-3 align-top">
                      <span className="block font-medium">{kind.label}</span>
                      <span className="mt-0.5 block text-xs leading-relaxed text-muted-foreground">{kind.description}</span>
                    </td>
                    {CHANNELS.map((channel) => (
                      <td key={channel.id} className="py-3 text-center align-top">
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
            <p className="py-3 text-xs leading-relaxed text-muted-foreground">
              Push and email include a brief update and a link back here. CV text, draft content and professor details stay private. Email goes to verified addresses only.
            </p>
          </div>
        )}
      </SettingSection>

      {prefs.data && <QuietHours prefs={prefs.data} onSave={save} />}

      {prefs.data && (
        <SettingSection title="Email digest">
          <SettingRow
            title="Daily digest"
            description="One email a morning listing unread notifications from the last day. Useful if you don't use push."
            control={
              <Switch
                checked={prefs.data.email_digest}
                label="Daily email digest"
                onChange={(on) => save({ email_digest: on })}
              />
            }
          />
        </SettingSection>
      )}
    </SettingsPanel>
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

  return (
    <SettingSection title="Quiet hours">
      <SettingRow
        title="Pause push and email"
        description="Push and email wait until this window ends. Inbox updates continue. Leave both times empty to turn quiet hours off."
        control={
          <div className="flex w-full flex-wrap items-center gap-1.5">
            <Input
              type="time"
              aria-label="Quiet hours start"
              className="h-9 w-28 min-w-0 flex-1 sm:flex-none"
              value={start}
              onChange={(e) => setStart(e.target.value)}
              onBlur={() => onSave({ quiet_start: start || null, quiet_end: end || null })}
            />
            <span className="text-xs text-muted-foreground">to</span>
            <Input
              type="time"
              aria-label="Quiet hours end"
              className="h-9 w-28 min-w-0 flex-1 sm:flex-none"
              value={end}
              onChange={(e) => setEnd(e.target.value)}
              onBlur={() => onSave({ quiet_start: start || null, quiet_end: end || null })}
            />
          </div>
        }
      />
      <SettingRow
        title="Timezone"
        description="Quiet hours and deadline reminders (14, 7 and 1 days before, from 8:00) follow this clock."
        control={
          <>
            <Input
              aria-label="Timezone"
              className="h-9 w-full min-w-0 sm:w-48"
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
    </SettingSection>
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

  if (config.isLoading || devices.isLoading || own.isLoading) {
    return (
      <SettingSection title="This browser">
        <SkeletonStack aria-label="Loading push settings" aria-busy="true" className="space-y-3 py-3" blocks={["h-10", "h-10"]} />
      </SettingSection>
    )
  }

  return (
    <SettingSection title="This browser">
      <SettingRow
        title="Push notifications"
        description={status}
        control={
          subscribed ? (
            <Button
              size="sm"
              variant="outline"
              onClick={() => {
                const own = devices.data?.find((d) => d.endpoint === endpoint)
                if (own) void remove(own)
              }}
            >
              Remove
            </Button>
          ) : canEnable ? (
            <Button data-tooltip="Allow browser notifications on this device" size="sm" onClick={turnOn} disabled={busy}>
              <BellRing /> Turn on
            </Button>
          ) : null
        }
      />
      {(devices.data ?? []).filter((d) => d.endpoint !== endpoint).length > 0 && (
        <div className="py-3">
          <p className="text-sm">Other devices</p>
          <ul className="mt-1.5 space-y-1.5">
            {(devices.data ?? [])
              .filter((d) => d.endpoint !== endpoint)
              .map((d) => (
                <li key={d.id} className="flex items-center gap-2 text-xs text-muted-foreground">
                  <Smartphone className="size-3.5 shrink-0" />
                  <span className="min-w-0 flex-1 truncate">{deviceName(d.user_agent)}</span>
                  <span>added {formatAgo(d.created_at)}</span>
                  <Button size="sm" variant="ghost" className="h-7" onClick={() => remove(d)}>
                    Remove
                  </Button>
                </li>
              ))}
          </ul>
        </div>
      )}
      <SettingRow
        title="Send a test notification"
        description="Goes to your inbox and every device with push on, right away (quiet hours don't apply)."
        control={
          <Button data-tooltip="Send a test notification to your registered devices" size="sm" variant="outline" onClick={test}>
            Send test
          </Button>
        }
      />
      <SettingRow
        title="Send a test email"
        description="Emails your verified address right away, so you can check email notifications arrive."
        control={
          <Button data-tooltip="Send a test email to your account's address" size="sm" variant="outline" onClick={testEmail}>
            Send test email
          </Button>
        }
      />
    </SettingSection>
  )
}

function deviceName(userAgent: string | null): string {
  const ua = userAgent ?? ""
  const browser = /Edg\//.test(ua) ? "Edge" : /Firefox\//.test(ua) ? "Firefox" : /Chrome\//.test(ua) ? "Chrome" : /Safari\//.test(ua) ? "Safari" : "Browser"
  const os = /iPhone|iPad/.test(ua) ? "iOS" : /Android/.test(ua) ? "Android" : /Mac OS X/.test(ua) ? "macOS" : /Windows/.test(ua) ? "Windows" : /Linux/.test(ua) ? "Linux" : ""
  return os ? `${browser} on ${os}` : browser
}
