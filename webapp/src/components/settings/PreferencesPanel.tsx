import { THEME_OPTIONS, useTheme } from "../../lib/theme"
import { SettingDisclosure, SettingRow, SettingSection, SettingsPanel, Switch } from "./controls"
import { useAutoPageContext } from "../../lib/chatPreferences"
import { cn } from "../../lib/utils"

export function PreferencesPanel() {
  const { mode, setTheme } = useTheme()
  const [autoContext, setAutoContext] = useAutoPageContext()
  return (
    <SettingsPanel title="Preferences" description="Make Blesser feel at home on this device.">
      <SettingSection title="Gradis context">
        <SettingRow title="Include the current page automatically" description="Give Gradis the page and record you're viewing. Selected text is attached only when you choose Add to Gradis context." control={<Switch checked={autoContext} onChange={setAutoContext} label="Include current page context" />} />
      </SettingSection>
      <SettingSection title="Appearance" description="Choose a theme, or follow your device's appearance.">
        <div role="group" aria-label="Theme" className="grid grid-cols-3 gap-2 py-4">
          {THEME_OPTIONS.map(({ value, label, Icon }) => (
            <button key={value} type="button" aria-pressed={mode === value}
              onClick={() => setTheme(value)}
              className={cn("flex min-w-0 cursor-pointer flex-col items-center gap-3 rounded-md border p-4 text-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring", mode === value ? "border-primary bg-primary/5 text-primary" : "border-border bg-background text-muted-foreground hover:bg-accent")}>
              <Icon className="size-6" aria-hidden />
              <span className="font-medium">{label}</span>
            </button>
          ))}
        </div>
      </SettingSection>
    </SettingsPanel>
  )
}

export function DataProviderPanel() {
  return (
    <SettingsPanel title="Data & AI providers" description="Understand how your information is stored and used.">
      <SettingSection title="Your workspace" description="Your records stay in your workspace database. Uploaded CV files are stored on its server.">
        <div className="py-3 text-sm leading-relaxed text-muted-foreground">Deleting your account removes your records and uploaded files. You can export your data in Profile settings.</div>
      </SettingSection>
      <SettingSection title="When information is shared" description="AI and research services receive only the information needed for the work you request.">
        <SettingDisclosure title="Research runs" description="Search queries, research interests and academic sources">
          <p className="text-sm leading-relaxed text-muted-foreground">Your model provider receives your interest statement and the pages and papers the agent reads. Search queries go to the search provider, and paper abstracts go to the embedding provider for fit scoring.</p>
        </SettingDisclosure>
        <SettingDisclosure title="CV assistance" description="CV content is shared when you ask Gradis for help">
          <p className="text-sm leading-relaxed text-muted-foreground">Reading or tailoring a CV, or choosing Suggest from my CV, shares relevant CV text with your model provider. Each read includes up to 20,000 characters. Whole files are never sent.</p>
        </SettingDisclosure>
        <SettingDisclosure title="Account privacy" description="Passwords stay private, and email drafts stay drafts">
          <p className="text-sm leading-relaxed text-muted-foreground">Your password is never sent to AI providers. API keys are sent only to their own provider. Creating an email draft does not send an email. Uploads and AI requests have account limits to prevent runaway activity.</p>
        </SettingDisclosure>
      </SettingSection>
    </SettingsPanel>
  )
}
