import * as React from "react"
import { useNavigate } from "react-router-dom"
import * as api from "../lib/api"
import { useAuth } from "../lib/auth"
import { toastError, toastSuccess } from "../lib/toast"
import { Button } from "../components/ui/button"
import { Field, Input } from "../components/ui/input"
import { NotificationsPanel } from "../components/settings/NotificationsPanel"
import { SettingSection, SettingsPanel } from "../components/settings/controls"

export function Settings() {
  return (
    <div className="space-y-10">
      <h1 className="type-page-title">Settings</h1>
      <AccountPanel />
      <NotificationsPanel />
    </div>
  )
}

function AccountPanel() {
  const { user, updateUser, signOut } = useAuth()
  const navigate = useNavigate()
  const [name, setName] = React.useState(user?.display_name ?? "")
  const [current, setCurrent] = React.useState("")
  const [next, setNext] = React.useState("")
  const [confirmDelete, setConfirmDelete] = React.useState("")
  const [busy, setBusy] = React.useState<string | null>(null)

  const run = async (key: string, action: () => Promise<void>) => {
    setBusy(key)
    try {
      await action()
    } catch (err) {
      toastError(err)
    } finally {
      setBusy(null)
    }
  }

  return (
    <SettingsPanel title="Account" description={user?.email ?? ""}>
      <SettingSection title="Name" description="Shown in the app and in emails.">
        <form
          className="flex flex-wrap gap-2"
          onSubmit={(e) => {
            e.preventDefault()
            void run("name", async () => {
              updateUser(await api.updateProfile(name.trim() || null))
              toastSuccess("Name saved")
            })
          }}
        >
          <Input aria-label="Name" value={name} onChange={(e) => setName(e.target.value)} maxLength={80} className="min-w-[220px] flex-1" />
          <Button type="submit" size="sm" variant="outline" disabled={busy === "name"}>
            Save
          </Button>
        </form>
      </SettingSection>

      {user?.has_password ? (
        <SettingSection title="Password">
          <form
            className="grid gap-2 sm:grid-cols-2"
            onSubmit={(e) => {
              e.preventDefault()
              void run("password", async () => {
                await api.changePassword(current, next)
                setCurrent("")
                setNext("")
                toastSuccess("Password changed")
              })
            }}
          >
            <Field label="Current password">
              <Input type="password" autoComplete="current-password" value={current} onChange={(e) => setCurrent(e.target.value)} required />
            </Field>
            <Field label="New password">
              <Input type="password" autoComplete="new-password" value={next} onChange={(e) => setNext(e.target.value)} minLength={8} required />
            </Field>
            <div>
              <Button type="submit" size="sm" variant="outline" disabled={busy === "password"}>
                Change password
              </Button>
            </div>
          </form>
        </SettingSection>
      ) : null}

      <SettingSection
        title="Delete account"
        description="Removes your account, tracked applications, to-dos and scans. Opportunities you found stay in the public catalogue."
      >
        <form
          className="flex flex-wrap gap-2"
          onSubmit={(e) => {
            e.preventDefault()
            void run("delete", async () => {
              await api.deleteAccount(confirmDelete)
              await signOut()
              navigate("/opportunities")
            })
          }}
        >
          <Input
            aria-label={user?.has_password ? "Password to confirm" : "Your email to confirm"}
            type={user?.has_password ? "password" : "email"}
            placeholder={user?.has_password ? "Password" : "Your email"}
            value={confirmDelete}
            onChange={(e) => setConfirmDelete(e.target.value)}
            className="min-w-[220px] flex-1"
            required
          />
          <Button type="submit" size="sm" variant="destructive" disabled={busy === "delete" || !confirmDelete}>
            Delete account
          </Button>
        </form>
      </SettingSection>
    </SettingsPanel>
  )
}
