import * as React from "react"
import { Link } from "react-router-dom"
import { useAuth } from "../../lib/auth"
import * as api from "../../lib/api"
import { toastError, toastSuccess } from "../../lib/toast"
import { Avatar } from "../ui/avatar"
import { Button } from "../ui/button"
import { Dialog, DialogBody, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "../ui/dialog"
import { Field, Input } from "../ui/input"
import { SettingDisclosure, SettingSection, SettingsPanel } from "./controls"
import { apiAssetUrl, identityName } from "../../lib/format"
import type { AuthUser } from "../../lib/types"
import { Camera, Loader2, X } from "lucide-react"

export function ProfilePanel({ onRequestClose }: { onRequestClose?: () => void }) {
  const { user, signOut } = useAuth()

  return (
    <SettingsPanel
      title="Profile"
      description="Manage your identity, account security and personal data."
      action={user && (
        <Button variant="outline" size="sm" onClick={() => void signOut()}>
          Sign out
        </Button>
      )}
    >

      {user ? (
        <>
          <IdentitySection user={user} />
          <SettingDisclosure title="Account security" description={user.has_password ? "Change your password" : "Set up a password for this account"}>
            {user.has_password ? <PasswordSection /> : <SetPasswordSection email={user.email} />}
          </SettingDisclosure>
          <ExportSection verified={user.email_verified} />
          <DataControlSection
            email={user.email}
            hasPassword={user.has_password}
            onDeleted={() => void signOut().then(() => toastSuccess("Account deleted"))}
          />
        </>
      ) : (
        <div className="mt-4">
          <Link
            to="/login"
            onClick={onRequestClose}
            className="text-sm text-primary hover:underline"
          >
            Sign in with email
          </Link>
        </div>
      )}
    </SettingsPanel>
  )
}

const AVATAR_TYPES = ["image/png", "image/jpeg", "image/webp"]
const AVATAR_MAX_BYTES = 5 * 1024 * 1024

/** Centre-crop to a square and downscale to 512px WebP; the server re-encodes too. */
async function squareCrop(file: File): Promise<Blob> {
  const url = URL.createObjectURL(file)
  try {
    const img = await new Promise<HTMLImageElement>((resolve, reject) => {
      const el = new Image()
      el.onload = () => resolve(el)
      el.onerror = () => reject(new Error("That file isn't a readable image."))
      el.src = url
    })
    const side = Math.min(img.naturalWidth, img.naturalHeight)
    const out = Math.min(512, side)
    const canvas = document.createElement("canvas")
    canvas.width = out
    canvas.height = out
    canvas.getContext("2d")?.drawImage(
      img,
      (img.naturalWidth - side) / 2,
      (img.naturalHeight - side) / 2,
      side,
      side,
      0,
      0,
      out,
      out,
    )
    return await new Promise<Blob>((resolve, reject) =>
      canvas.toBlob((b) => (b ? resolve(b) : reject(new Error("Couldn't process that image."))), "image/webp", 0.9),
    )
  } finally {
    URL.revokeObjectURL(url)
  }
}

/** Name and picture; an empty name falls back to the email wherever identity renders. */
function IdentitySection({ user }: { user: AuthUser }) {
  const { updateUser } = useAuth()
  const [name, setName] = React.useState(user.display_name ?? "")
  const [savingName, setSavingName] = React.useState(false)
  const [uploading, setUploading] = React.useState(false)
  const fileRef = React.useRef<HTMLInputElement>(null)
  const dirty = name.trim() !== (user.display_name ?? "")

  async function saveName() {
    if (!dirty || savingName) return
    setSavingName(true)
    try {
      updateUser(await api.updateProfile(name.trim() || null))
      toastSuccess(name.trim() ? "Name updated" : "Name cleared")
    } catch (err) {
      toastError(err)
    } finally {
      setSavingName(false)
    }
  }

  async function onPick(file: File | undefined) {
    if (!file) return
    if (!AVATAR_TYPES.includes(file.type)) {
      toastError("Use a PNG, JPEG or WebP image.")
      return
    }
    if (file.size > AVATAR_MAX_BYTES) {
      toastError("Pictures must be 5 MB or smaller.")
      return
    }
    setUploading(true)
    try {
      updateUser(await api.uploadAvatar(await squareCrop(file)))
      toastSuccess("Picture updated")
    } catch (err) {
      toastError(err, "Couldn't update your picture")
    } finally {
      setUploading(false)
      if (fileRef.current) fileRef.current.value = ""
    }
  }

  async function onRemove() {
    try {
      updateUser(await api.removeAvatar())
      toastSuccess("Picture removed")
    } catch (err) {
      toastError(err)
    }
  }

  return (
    <SettingSection title="Your profile">
      <div className="flex flex-col gap-5 py-4 sm:flex-row sm:items-start">
        <div className="flex items-center gap-4 sm:flex-col sm:items-center sm:gap-2">
          <div className="relative">
            <button
              type="button"
              onClick={() => fileRef.current?.click()}
              disabled={uploading}
              aria-label="Change profile picture"
              className="group relative cursor-pointer rounded-full focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              <Avatar name={identityName(user)} src={apiAssetUrl(user.avatar_url)} size="lg" className="size-20 text-2xl" />
              <span className="absolute inset-0 flex items-center justify-center rounded-full bg-black/45 text-white opacity-0 transition-opacity group-hover:opacity-100 group-focus-visible:opacity-100">
                {uploading ? <Loader2 className="size-5 animate-spin" /> : <Camera className="size-5" />}
              </span>
            </button>
            {
              user.avatar_url && !uploading && (
                <button
                  type="button"
                  onClick={() => void onRemove()}
                  aria-label="Remove profile picture"
                  data-tooltip="Remove profile picture"
                  className="absolute top-0 right-0 cursor-pointer rounded-full bg-critical-soft p-1 text-critical hover:bg-critical hover:text-on-critical"
                >
                  <X className="size-4" />
                </button>
              )
            }
          </div>
          <input
            ref={fileRef}
            type="file"
            accept={AVATAR_TYPES.join(",")}
            className="hidden"
            onChange={(e) => void onPick(e.target.files?.[0])}
          />
        </div>

        <div className="min-w-0 flex-1 space-y-4">
          <Field label="Display name">
            <Input
              value={name}
              maxLength={80}
              placeholder={user.email}
              autoComplete="name"
              onChange={(e) => setName(e.target.value)}
              onBlur={() => void saveName()}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.preventDefault()
                  void saveName()
                }
              }}
            />
          </Field>
          <p className="-mt-2 type-caption">
            {savingName && " Saving…"}
          </p>
          <div>
            <p className="text-compact font-medium">Email</p>
            <p className="mt-1 type-meta">{user.email}</p>
          </div>
        </div>
      </div>
    </SettingSection>
  )
}

/** Provider-only accounts have no current password, so they set one via email. */
function SetPasswordSection({ email }: { email: string }) {
  const [sent, setSent] = React.useState(false)
  const [busy, setBusy] = React.useState(false)
  async function send() {
    setBusy(true)
    try {
      await api.forgotPassword(email)
      setSent(true)
    } catch (err) {
      toastError(err)
    } finally {
      setBusy(false)
    }
  }
  return (
    <SettingSection title="Password">
      <div className="flex flex-col items-start justify-between gap-4 py-3 sm:flex-row">
        <p className="type-meta">
          You sign in with Google. Add a password to also sign in with your email.
        </p>
        <Button data-tooltip="Send a password reset link to your account email" size="sm" variant="outline" disabled={busy || sent} onClick={() => void send()}>
          {sent ? "Link sent" : "Email me a link"}
        </Button>
      </div>
    </SettingSection>
  )
}

function PasswordSection() {
  const [current, setCurrent] = React.useState("")
  const [next, setNext] = React.useState("")
  const [confirm, setConfirm] = React.useState("")
  const [busy, setBusy] = React.useState(false)

  const mismatch = next !== "" && confirm !== "" && next !== confirm
  const canSave = current !== "" && next.length >= 8 && next === confirm && !busy

  async function onSave() {
    if (!canSave) return
    setBusy(true)
    try {
      await api.changePassword(current, next)
      setCurrent("")
      setNext("")
      setConfirm("")
      toastSuccess("Password updated")
    } catch (err) {
      toastError(err)
    } finally {
      setBusy(false)
    }
  }

  return (
    <SettingSection title="Password">
      <div className="grid gap-3 py-3 sm:grid-cols-2">
        <Field label="Current password">
          <Input
            type="password"
            autoComplete="current-password"
            value={current}
            onChange={(e) => setCurrent(e.target.value)}
            placeholder="••••••••"
          />
        </Field>
        <div className="hidden sm:block" aria-hidden />
        <Field label="New password">
          <Input
            type="password"
            autoComplete="new-password"
            value={next}
            onChange={(e) => setNext(e.target.value)}
            placeholder="At least 8 characters"
          />
        </Field>
        <Field label="Confirm new password">
          <Input
            type="password"
            autoComplete="new-password"
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
            placeholder="Repeat the new password"
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault()
                void onSave()
              }
            }}
          />
        </Field>
      </div>
      {mismatch && (
        <p className="pb-1 text-xs text-destructive">New passwords don't match.</p>
      )}
      <div className="flex items-center gap-3 pb-1">
        <Button data-tooltip="Save your new account password" size="sm" disabled={!canSave} onClick={() => void onSave()}>
          {busy ? "Updating…" : "Update password"}
        </Button>
        <span className="type-caption">Other signed-in sessions stay active.</span>
      </div>
    </SettingSection>
  )
}

function formatBytes(n: number | null) {
  if (!n) return ""
  return n > 1_000_000 ? `${(n / 1_000_000).toFixed(1)} MB` : `${Math.max(1, Math.round(n / 1000))} KB`
}

/** Requires a verified email; download links last 5 minutes and archives expire after 7 days. */
function ExportSection({ verified }: { verified: boolean }) {
  const [exports, setExports] = React.useState<api.AccountExport[] | null>(null)
  const [busy, setBusy] = React.useState(false)
  const latest = exports?.[0] ?? null
  const pending = latest?.status === "pending"

  const load = React.useCallback(async () => {
    try {
      setExports(await api.listExports())
    } catch {
      setExports([])
    }
  }, [])

  React.useEffect(() => {
    void load()
  }, [load])

  React.useEffect(() => {
    if (!pending) return
    const t = window.setInterval(() => void load(), 1500)
    return () => window.clearInterval(t)
  }, [pending, load])

  async function start() {
    setBusy(true)
    try {
      await api.createExport()
      await load()
    } catch (err) {
      toastError(err)
    } finally {
      setBusy(false)
    }
  }

  async function download(id: string) {
    try {
      const { url } = await api.exportLink(id)
      window.location.assign(`${api.API_BASE}${url}`)
    } catch (err) {
      toastError(err)
    }
  }

  return (
    <SettingSection title="Your data">
      <div className="flex flex-col items-start justify-between gap-4 py-3 sm:flex-row">
        <div className="min-w-0">
          <p className="text-sm text-foreground">Export your data</p>
          <p className="mt-0.5 text-xs leading-relaxed text-muted-foreground">
            A ZIP of everything in this account: runs, professor matches, drafts, applications, chats, settings, and your
            CV files. API keys and passwords are never included.
          </p>
          {latest && (
            <p className="mt-1.5 type-caption" aria-live="polite">
              {latest.status === "pending"
                ? "Preparing your archive…"
                : latest.status === "failed"
                  ? <span className="text-destructive">The last export failed. Try again.</span>
                  : `Ready, ${formatBytes(latest.size_bytes)}, available until ${new Date(latest.expires_at).toLocaleDateString()}`}
            </p>
          )}
          {!verified && (
            <p className="mt-1.5 text-xs text-caution">Confirm your email first to export.</p>
          )}
        </div>
        <div className="flex shrink-0 items-center gap-2">
          {latest?.status === "ready" && (
            <Button data-tooltip="Download your account data as a ZIP file" size="sm" onClick={() => void download(latest.id)}>
              Download
            </Button>
          )}
          <Button data-tooltip={!verified ? "Verify your email before exporting your data" : "Prepare a ZIP containing your account data"} size="sm" variant="outline" disabled={!verified || busy || pending} onClick={() => void start()}>
            {pending ? "Preparing…" : latest?.status === "ready" ? "New export" : "Export"}
          </Button>
        </div>
      </div>
    </SettingSection>
  )
}

function DataControlSection({
  email,
  hasPassword,
  onDeleted,
}: {
  email: string
  hasPassword: boolean
  onDeleted: () => void
}) {
  const [confirmOpen, setConfirmOpen] = React.useState(false)
  const [password, setPassword] = React.useState("")
  const [busy, setBusy] = React.useState(false)

  async function onDelete() {
    if (password === "" || busy) return
    setBusy(true)
    try {
      await api.deleteAccount(password)
      setConfirmOpen(false)
      setPassword("")
      onDeleted()
    } catch (err) {
      toastError(err)
    } finally {
      setBusy(false)
    }
  }

  return (
    <SettingSection title="Data control">
      <div className="flex flex-col items-start justify-between gap-4 py-3 sm:flex-row">
        <div className="min-w-0">
          <p className="text-sm text-foreground">Delete account</p>
          <p className="mt-0.5 text-xs leading-relaxed text-muted-foreground">
            Permanently removes the runs, drafts, applications, CVs, chats, keys, and settings belonging to {email}.
            This cannot be undone.
          </p>
        </div>
        <div className="flex shrink-0 items-center">
          <Button data-tooltip="Review the permanent account deletion options" size="sm" variant="destructive" onClick={() => setConfirmOpen(true)}>
            Delete…
          </Button>
        </div>
      </div>

      <Dialog open={confirmOpen} onOpenChange={setConfirmOpen}>
        <DialogContent onClose={() => setConfirmOpen(false)}>
          <DialogHeader>
            <DialogTitle>Delete account?</DialogTitle>
            <DialogDescription>
              This permanently deletes {email}'s account and all its data, and signs every session out. This cannot
              be undone.
            </DialogDescription>
          </DialogHeader>
          <DialogBody>
            <Field label={hasPassword ? "Confirm with your password" : "Type your email to confirm"}>
              <Input
                type={hasPassword ? "password" : "email"}
                autoComplete={hasPassword ? "current-password" : "off"}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder={hasPassword ? "••••••••" : email}
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    e.preventDefault()
                    void onDelete()
                  }
                }}
              />
            </Field>
          </DialogBody>
          <DialogFooter>
            <Button variant="outline" onClick={() => setConfirmOpen(false)} disabled={busy}>
              Cancel
            </Button>
            <Button variant="destructive" onClick={() => void onDelete()} disabled={password === "" || busy}>
              {busy ? "Deleting…" : "Delete account"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </SettingSection>
  )
}
