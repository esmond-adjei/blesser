import { useNavigate } from "react-router-dom"
import { Bell, Check, ChevronsUpDown, Info, LogOut, Settings } from "lucide-react"
import { cn } from "@blesser/ui"
import { useAuth } from "../../lib/auth"
import { accountName, initials } from "../../lib/format"
import { SITE_URL } from "../../lib/site"
import { THEME_MODES, useTheme, parseTheme } from "../../lib/theme"
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuRadioGroup, DropdownMenuRadioItem, DropdownMenuSeparator, DropdownMenuTrigger } from "../ui/dropdown-menu"

export function Avatar({ name, className }: { name: string; className?: string }) {
  return <span aria-hidden="true" className={cn("grid size-8 shrink-0 place-items-center rounded-full bg-forest-soft text-[13px] font-semibold text-link select-none", className)}>{initials(name)}</span>
}

export function AccountMenu({ variant = "sidebar" }: { variant?: "sidebar" | "compact" }) {
  const { user, signOut } = useAuth()
  const { mode, setTheme } = useTheme()
  const navigate = useNavigate()
  const name = accountName(user)
  const compact = variant === "compact"

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button type="button" aria-label={compact ? `Account menu for ${name}` : undefined} className={cn("cursor-pointer transition-colors duration-160", compact ? "grid size-9 place-items-center rounded-full hover:bg-surface-sunk" : "flex w-full min-w-0 items-center gap-2.5 rounded-sm px-2 py-1.5 text-left hover:bg-surface-sunk data-[state=open]:bg-surface-sunk")}>
          <Avatar name={name} className={compact ? "size-7 text-xs" : undefined} />
          {!compact && <><span className="min-w-0 flex-1 truncate text-callout font-semibold text-ink">{name}</span><ChevronsUpDown aria-hidden="true" className="size-4 shrink-0 text-ink-tertiary" /></>}
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent side={compact ? "bottom" : "top"} align={compact ? "end" : "start"} aria-label="Account">
        <div className="flex items-center gap-2.5 px-2.5 pt-2 pb-2.5"><Avatar name={name} /><div className="min-w-0"><p className="truncate text-callout font-semibold text-ink">{name}</p><p className="truncate text-footnote text-ink-secondary">{user?.email}</p></div></div>
        <DropdownMenuSeparator />
        <DropdownMenuItem onSelect={() => navigate("/settings")}><Settings strokeWidth={1.75} /> Settings</DropdownMenuItem>
        <DropdownMenuItem onSelect={() => navigate("/settings/notifications")}><Bell strokeWidth={1.75} /> Notifications</DropdownMenuItem>
        <DropdownMenuSeparator />
        <div className="px-2.5 pt-1 text-footnote font-semibold text-ink-secondary">Theme</div>
        <DropdownMenuRadioGroup value={mode} onValueChange={(value) => setTheme(parseTheme(value))}>
          {THEME_MODES.map(({ value, label, Icon }) => <DropdownMenuRadioItem key={value} value={value} onSelect={(event) => event.preventDefault()}><Icon className="mr-2.5 size-4 text-ink-secondary" strokeWidth={1.75} />{label}{mode === value && <Check className="ml-auto size-4" />}</DropdownMenuRadioItem>)}
        </DropdownMenuRadioGroup>
        {SITE_URL && <DropdownMenuItem asChild><a href={`${SITE_URL}/about`} target="_blank" rel="noopener"><Info strokeWidth={1.75} /> About Blesser</a></DropdownMenuItem>}
        <DropdownMenuSeparator />
        <DropdownMenuItem onSelect={() => { void signOut().then(() => navigate("/login")) }}><LogOut strokeWidth={1.75} /> Sign out</DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
