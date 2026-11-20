import * as React from "react"
import { Navigate, NavLink, useNavigate, useParams, useSearchParams } from "react-router-dom"
import { useQueryClient } from "@tanstack/react-query"
import { Bell, CalendarDays, Copy, Palette, RefreshCw, ShieldCheck, Target, UserRound } from "lucide-react"
import { ConnectedBrowsers } from "../components/settings/ConnectedBrowsers"
import { Button, Field, Input, Select, buttonVariants, cn } from "@blesser/ui"
import * as api from "../lib/api"
import { useAuth } from "../lib/auth"
import { accountName } from "../lib/format"
import { useCalendarFeed } from "../lib/opportunities"
import { THEME_MODES, useTheme } from "../lib/theme"
import { toastError, toastSuccess } from "../lib/toast"
import { PageHeader } from "../components/layout/PageHeader"
import { Avatar } from "../components/layout/AccountMenu"
import { NotificationsPanel } from "../components/settings/NotificationsPanel"
import { MatchingPanel } from "../components/settings/MatchingPanel"
import { SettingRow, SettingsGroup, SettingsSection } from "../components/settings/controls"
import { useAutosave } from "../lib/autosave"
import { Dialog, DialogBody, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "../components/ui/dialog"

const SECTIONS = [
  { id: "profile", label: "Profile", icon: UserRound, description: "How you appear in Blesser and in the emails it sends." },
  { id: "account", label: "Account and security", icon: ShieldCheck, description: "Your sign-in email, password, connected browsers and account." },
  { id: "matching", label: "What you're looking for", icon: Target, description: "Your For you list, match alerts and saved searches." },
  { id: "notifications", label: "Notifications", icon: Bell, description: "What you hear about, where it reaches you and when it waits." },
  { id: "calendar", label: "Calendar", icon: CalendarDays, description: "Your application deadlines and dated to-dos in your own calendar app." },
  { id: "appearance", label: "Appearance", icon: Palette, description: "How Blesser looks on this device." },
] as const

type SectionId = (typeof SECTIONS)[number]["id"]

const isSection = (value: string | null | undefined): value is SectionId => SECTIONS.some((s) => s.id === value)

export function Settings() {
  const { section } = useParams()
  const [params] = useSearchParams()
  const navigate = useNavigate()
  const legacy = params.get("section")
  if (!section && isSection(legacy)) return <Navigate to={`/settings/${legacy}`} replace />
  if (section && !isSection(section)) return <Navigate to="/settings" replace />
  const active = SECTIONS.find((s) => s.id === (section ?? "profile"))!

  return (
    <div className="space-y-6">
      <PageHeader title="Settings" />
      <div className="lg:grid lg:grid-cols-[13rem_minmax(0,1fr)] lg:gap-12">
        <nav aria-label="Settings sections" className="hidden lg:block">
          <ul className="sticky top-0 space-y-0.5">
            {SECTIONS.map((s) => (
              <li key={s.id}>
                <NavLink
                  to={`/settings/${s.id}`}
                  className={() =>
                    cn(
                      "flex h-8 items-center gap-2.5 rounded-sm px-2.5 text-callout transition-colors duration-160 [&_svg]:size-4",
                      s.id === active.id ? "bg-forest-soft font-semibold text-link" : "font-medium text-ink-secondary hover:bg-highlight hover:text-ink",
                    )
                  }
                  aria-current={s.id === active.id ? "page" : undefined}
                >
                  <s.icon strokeWidth={1.75} aria-hidden="true" />
                  {s.label}
                </NavLink>
              </li>
            ))}
          </ul>
        </nav>
        <div className="mb-6 lg:hidden">
          <Select aria-label="Settings section" value={active.id} onChange={(e) => navigate(`/settings/${e.target.value}`)} className="w-full">
            {SECTIONS.map((s) => (
              <option key={s.id} value={s.id}>{s.label}</option>
            ))}
          </Select>
        </div>
        <div key={active.id} className="bl-enter max-w-3xl min-w-0">
          <SettingsSection id={active.id} title={active.label} description={active.description}>
            {active.id === "profile" ? <ProfileSection /> : null}
            {active.id === "account" ? <AccountSection /> : null}
            {active.id === "matching" ? <MatchingPanel /> : null}
            {active.id === "notifications" ? <NotificationsPanel /> : null}
            {active.id === "calendar" ? <CalendarSection /> : null}
            {active.id === "appearance" ? <AppearanceSection /> : null}
          </SettingsSection>
        </div>
      </div>
    </div>
  )
}

function ProfileSection() {
  const { user, updateUser } = useAuth()
  const track = useAutosave()
  const saved = user?.display_name ?? ""
  const [name, setName] = React.useState(saved)
  const nameId = React.useId()

  const save = async () => {
    const next = name.trim()
    if (next === saved) return
    const updated = await track(api.updateProfile(next || null))
    if (updated) {
      updateUser(updated)
      setName(updated.display_name ?? "")
    }
  }

  return (
    <SettingsGroup>
      <div className="flex items-center gap-3 px-4 py-4 sm:px-5">
        <Avatar name={accountName(user)} className="size-11 text-base" />
        <div className="min-w-0">
          <p className="truncate text-callout font-semibold text-ink">{accountName(user)}</p>
          <p className="truncate text-footnote text-ink-secondary">{user?.email}</p>
        </div>
      </div>
      <SettingRow
        stack
        htmlFor={nameId}
        label="Display name"
        description="Shown in the app and in emails. Leave it empty to use your email."
        control={
          <form
            className="w-full sm:w-64"
            onSubmit={(e) => {
              e.preventDefault()
              void save()
            }}
          >
            <Input id={nameId} value={name} onChange={(e) => setName(e.target.value)} onBlur={() => void save()} maxLength={80} placeholder={user?.email.split("@")[0]} autoComplete="name" className="h-control-sm w-full text-callout" />
          </form>
        }
      />
    </SettingsGroup>
  )
}

function AccountSection() {
  const { user, signOut } = useAuth()
  const navigate = useNavigate()
  const [passwordOpen, setPasswordOpen] = React.useState(false)
  const [deleteOpen, setDeleteOpen] = React.useState(false)
  const [sending, setSending] = React.useState(false)

  return (
    <>
      <SettingsGroup title="Sign-in">
        <SettingRow
          stack
          label="Email"
          description={
            <span className="flex flex-wrap items-center gap-x-2 gap-y-0.5">
              <span className="break-all text-ink">{user?.email}</span>
              <span className="inline-flex items-center gap-1.5">
                <span aria-hidden="true" className={cn("size-1.5 rounded-full", user?.email_verified ? "bg-positive" : "bg-caution")} />
                {user?.email_verified ? "Verified" : "Not verified yet"}
              </span>
            </span>
          }
          control={
            user && !user.email_verified ? (
              <Button
                size="sm"
                variant="secondary"
                disabled={sending}
                onClick={async () => {
                  setSending(true)
                  try {
                    toastSuccess((await api.resendVerification()).status)
                  } catch (err) {
                    toastError(err, "Couldn't send")
                  } finally {
                    setSending(false)
                  }
                }}
              >
                Resend link
              </Button>
            ) : null
          }
        />
        <SettingRow
          stack
          label="Password"
          description={user?.has_password ? "At least 8 characters. Devices already signed in stay signed in." : "You sign in with a provider such as Google, so there's no password to change."}
          control={user?.has_password ? <Button size="sm" variant="secondary" onClick={() => setPasswordOpen(true)}>Change password</Button> : null}
        />
        <SettingRow
          stack
          label="Sign out"
          description="Signs out of Blesser on this device and stops its push notifications."
          control={
            <Button
              size="sm"
              variant="secondary"
              onClick={async () => {
                await signOut()
                navigate("/login")
              }}
            >
              Sign out
            </Button>
          }
        />
      </SettingsGroup>

      <ConnectedBrowsers />

      <SettingsGroup title="Danger zone" danger>
        <SettingRow
          stack
          label="Delete account"
          description="Removes your account, tracked applications, to-dos and scans for good. Opportunities you found stay in the public catalogue."
          control={<Button size="sm" variant="danger" onClick={() => setDeleteOpen(true)}>Delete account</Button>}
        />
      </SettingsGroup>

      <PasswordDialog open={passwordOpen} onOpenChange={setPasswordOpen} />
      <DeleteDialog open={deleteOpen} onOpenChange={setDeleteOpen} />
    </>
  )
}

function PasswordDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  const [current, setCurrent] = React.useState("")
  const [next, setNext] = React.useState("")
  const [busy, setBusy] = React.useState(false)
  const close = React.useCallback(() => {
    onOpenChange(false)
    setCurrent("")
    setNext("")
  }, [onOpenChange])

  return (
    <Dialog open={open} onOpenChange={(o) => (o ? onOpenChange(true) : close())}>
      <DialogContent onClose={close} className="max-w-md">
        <DialogHeader>
          <DialogTitle>Change password</DialogTitle>
          <DialogDescription>Devices already signed in stay signed in.</DialogDescription>
        </DialogHeader>
        <DialogBody>
          <form
            className="space-y-4"
            onSubmit={async (e) => {
              e.preventDefault()
              setBusy(true)
              try {
                await api.changePassword(current, next)
                toastSuccess("Password changed")
                close()
              } catch (err) {
                toastError(err)
              } finally {
                setBusy(false)
              }
            }}
          >
            <Field label="Current password" type="password" autoComplete="current-password" value={current} onChange={(e) => setCurrent(e.target.value)} required autoFocus />
            <Field label="New password" hint="At least 8 characters." type="password" autoComplete="new-password" value={next} onChange={(e) => setNext(e.target.value)} minLength={8} required />
            <div className="flex justify-end gap-2 pt-1">
              <Button size="sm" variant="quiet" onClick={close}>Cancel</Button>
              <Button type="submit" size="sm" variant="brand" disabled={busy || !current || next.length < 8}>Change password</Button>
            </div>
          </form>
        </DialogBody>
      </DialogContent>
    </Dialog>
  )
}

function DeleteDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  const { user, signOut } = useAuth()
  const navigate = useNavigate()
  const [confirm, setConfirm] = React.useState("")
  const [busy, setBusy] = React.useState(false)
  const byPassword = !!user?.has_password
  const close = React.useCallback(() => {
    onOpenChange(false)
    setConfirm("")
  }, [onOpenChange])

  return (
    <Dialog open={open} onOpenChange={(o) => (o ? onOpenChange(true) : close())}>
      <DialogContent onClose={close} className="max-w-md">
        <DialogHeader>
          <DialogTitle>Delete your account?</DialogTitle>
          <DialogDescription>
            Your tracked applications, to-dos, scans and settings go for good. This can't be undone.
          </DialogDescription>
        </DialogHeader>
        <DialogBody>
          <form
            className="space-y-4"
            onSubmit={async (e) => {
              e.preventDefault()
              setBusy(true)
              try {
                await api.deleteAccount(confirm)
                await signOut()
                navigate("/login")
              } catch (err) {
                toastError(err)
                setBusy(false)
              }
            }}
          >
            <Field
              label={byPassword ? "Enter your password to confirm" : "Type your email to confirm"}
              type={byPassword ? "password" : "email"}
              autoComplete={byPassword ? "current-password" : "off"}
              placeholder={byPassword ? undefined : user?.email}
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              required
              autoFocus
            />
            <div className="flex justify-end gap-2 pt-1">
              <Button size="sm" variant="quiet" onClick={close}>Cancel</Button>
              <Button type="submit" size="sm" variant="danger" disabled={busy || !confirm}>Delete account</Button>
            </div>
          </form>
        </DialogBody>
      </DialogContent>
    </Dialog>
  )
}

function CalendarSection() {
  const [enabled, setEnabled] = React.useState(false)
  const feed = useCalendarFeed(enabled)
  const client = useQueryClient()
  const [rotating, setRotating] = React.useState(false)
  const linkId = React.useId()
  const shown = enabled || !!feed.data

  const copy = async (text: string) => {
    try {
      await navigator.clipboard.writeText(text)
      toastSuccess("Link copied")
    } catch (err) {
      toastError(err, "Couldn't copy")
    }
  }

  return (
    <SettingsGroup title="Calendar subscription" description="Subscribe once and deadlines stay up to date in Google Calendar, Apple Calendar or Outlook.">
        {!shown ? (
          <SettingRow
            stack
            label="Subscription link"
            description="A private link: anyone who has it can see your deadlines."
            control={<Button size="sm" variant="secondary" onClick={() => setEnabled(true)}>Get my calendar link</Button>}
          />
        ) : feed.isLoading ? (
          <div className="p-4 sm:px-5"><div className="h-10 animate-pulse rounded-sm bg-surface-sunk motion-reduce:animate-none" /></div>
        ) : feed.data ? (
          <>
            <SettingRow htmlFor={linkId} label="Subscription link" description="A private link: anyone who has it can see your deadlines.">
              <div className="mt-3 flex flex-wrap gap-2">
                <Input id={linkId} readOnly value={feed.data.url} className="h-control-sm min-w-0 flex-1 basis-60 font-mono text-footnote" onFocus={(e) => e.currentTarget.select()} />
                <Button size="sm" variant="secondary" onClick={() => void copy(feed.data.url)} icon={<Copy />}>Copy</Button>
                <a href={feed.data.webcal_url} className={buttonVariants({ size: "sm", variant: "secondary" })}>Open in calendar app</a>
              </div>
            </SettingRow>
            <SettingRow
              label="Adding it by hand"
              description={
                <ul className="mt-1 list-disc space-y-0.5 pl-4">
                  <li>Google Calendar: Other calendars, then From URL, and paste the link.</li>
                  <li>Apple Calendar: File, then New Calendar Subscription.</li>
                  <li>Outlook: Add calendar, then Subscribe from web.</li>
                </ul>
              }
            />
            <SettingRow
              stack
              label="Make a new link"
              description="Use this if the link was shared by mistake. Calendars using the old link stop updating."
              control={
                <Button
                  size="sm"
                  variant="secondary"
                  disabled={rotating}
                  icon={<RefreshCw />}
                  onClick={async () => {
                    setRotating(true)
                    try {
                      client.setQueryData(["calendar-feed"], await api.rotateCalendarFeed())
                      toastSuccess("New link made. The old one no longer works.")
                    } catch (err) {
                      toastError(err, "Couldn't make a new link")
                    } finally {
                      setRotating(false)
                    }
                  }}
                >
                  New link
                </Button>
              }
            />
          </>
        ) : (
          <SettingRow
            label="Your calendar link didn't load"
            description="Try again in a moment."
            control={<Button size="sm" variant="secondary" onClick={() => void feed.refetch()} icon={<RefreshCw />}>Try again</Button>}
          />
        )}
    </SettingsGroup>
  )
}

function AppearanceSection() {
  const { mode, setTheme } = useTheme()
  return (
    <SettingsGroup title="Theme" description="Saved on this device.">
      <div role="radiogroup" aria-label="Theme" className="grid gap-3 p-4 sm:grid-cols-3 sm:px-5">
        {THEME_MODES.map(({ value, label, Icon }) => {
          const on = mode === value
          return (
            <label
              key={value}
              className={cn(
                "flex cursor-pointer flex-col gap-3 rounded-md border p-3 transition-colors duration-160 has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-focus",
                on ? "border-link bg-forest-soft/40" : "border-separator hover:bg-highlight",
              )}
            >
              <input type="radio" name="theme" value={value} checked={on} onChange={() => setTheme(value)} className="sr-only" />
              <ThemePreview mode={value} />
              <span className="flex items-center gap-2 text-callout font-medium text-ink">
                <Icon className="size-4 text-ink-secondary" strokeWidth={1.75} aria-hidden="true" />
                {label}
                {value === "system" ? <span className="text-footnote font-normal text-ink-secondary">matches your device</span> : null}
              </span>
            </label>
          )
        })}
      </div>
    </SettingsGroup>
  )
}

function ThemePreview({ mode }: { mode: "system" | "light" | "dark" }) {
  const pane = (theme: "light" | "dark") => (
    <div data-theme={theme} className="flex h-full flex-1 gap-1.5 bg-canvas p-2">
      <div className="w-1/4 space-y-1 rounded-[3px] bg-surface-sunk p-1">
        <div className="h-1 rounded-full bg-ink-tertiary/60" />
        <div className="h-1 w-2/3 rounded-full bg-ink-tertiary/40" />
      </div>
      <div className="flex-1 space-y-1.5 rounded-[3px] border border-separator bg-surface p-1.5">
        <div className="h-1.5 w-1/2 rounded-full bg-ink/70" />
        <div className="h-1 rounded-full bg-ink-tertiary/50" />
        <div className="h-1.5 w-6 rounded-full bg-sun" />
      </div>
    </div>
  )
  return (
    <div aria-hidden="true" className="flex h-20 overflow-hidden rounded-sm border border-separator">
      {mode === "system" ? (
        <>
          {pane("light")}
          {pane("dark")}
        </>
      ) : (
        pane(mode)
      )}
    </div>
  )
}
