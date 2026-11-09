import * as React from "react"
import { useQueryClient } from "@tanstack/react-query"
import { Lock } from "lucide-react"
import { SettingsSection } from "../../components/settings/controls"
import { ErrorState } from "../../components/feedback/EmptyState"
import {
  CheckField,
  KitGroup,
  KitMeterCard,
  KitRail,
  FormGrid,
  KitSkeleton,
  Repeatable,
  SecretField,
  SelectField,
  TagInput,
  TextAreaField,
  TextField,
} from "../../components/kit/parts"
import { useAuth } from "../../lib/auth"
import {
  LANGUAGE_LEVELS,
  SHORT_BIO_MAX,
  dateToMonth,
  emptyEducation,
  emptyExperience,
  emptyReference,
  maskSecret,
  nextSteps,
  normalizeProfile,
  profileGaps,
} from "../../lib/kit"
import { getKitProfile, kitKeys, putKitProfile, useKitProfile } from "../../lib/kitApi"
import type { LanguageLevel, Profile, ProfileInput, Sensitive } from "../../lib/kitTypes"
import { useDraft } from "../../lib/useDraft"
import { toastError } from "../../lib/toast"

const SECTIONS = [
  { id: "kit-identity", label: "Identity" },
  { id: "kit-contact", label: "Contact" },
  { id: "kit-about", label: "About you" },
  { id: "kit-education", label: "Education" },
  { id: "kit-experience", label: "Experience" },
  { id: "kit-skills", label: "Skills and languages" },
  { id: "kit-recognition", label: "Awards and publications" },
  { id: "kit-references", label: "References" },
  { id: "kit-private", label: "Private details" },
] as const

type SecretKey = keyof Sensitive
const SECRET_KEYS: SecretKey[] = ["national_id", "passport_number", "passport_expiry"]
type Draft = { profile: ProfileInput; secrets: Partial<Record<SecretKey, string | null>> }
type Payload = { profile: ProfileInput; edited: SecretKey[] }

export function ProfileTab() {
  const query = useKitProfile()
  return (
    <SettingsSection id="kit-profile" title="Your profile" description="The details application forms ask for again and again. Everything saves as you type.">
      {query.data ? (
        <ProfileForm initial={query.data} />
      ) : query.isError ? (
        <ErrorState title="Your profile didn't load" description="Check your connection and try again." onRetry={() => void query.refetch()} />
      ) : (
        <KitSkeleton rows={4} />
      )}
    </SettingsSection>
  )
}

function ProfileForm({ initial }: { initial: Profile }) {
  const client = useQueryClient()
  const { user } = useAuth()
  const [completeness, setCompleteness] = React.useState(initial.completeness)
  const [plain, setPlain] = React.useState<Sensitive | null>(null)
  const plainRef = React.useRef<Promise<Sensitive> | null>(null)
  const [revealed, setRevealed] = React.useState(false)
  const [revealing, setRevealing] = React.useState(false)

  const loadPlain = React.useCallback(() => {
    plainRef.current ??= getKitProfile(true).then((p) => {
      setPlain(p.sensitive)
      return p.sensitive
    })
    plainRef.current.catch(() => (plainRef.current = null))
    return plainRef.current
  }, [])

  const toPayload = React.useCallback(({ profile, secrets }: Draft): Payload => {
    const edited = SECRET_KEYS.filter((k) => secrets[k] !== undefined)
    return { profile: normalizeProfile({ ...profile, sensitive: { ...profile.sensitive, ...secrets } as Sensitive }), edited }
  }, [])

  const save = React.useCallback(
    async ({ profile, edited }: Payload) => {
      // The API masks these on read and PUT replaces the whole profile, so unedited ones go back as their real values.
      const real = edited.length === SECRET_KEYS.length ? null : await loadPlain()
      const sensitive: Sensitive = { ...profile.sensitive }
      if (real) for (const k of SECRET_KEYS) if (!edited.includes(k)) Object.assign(sensitive, { [k]: real[k] })
      const saved = await putKitProfile({ ...profile, sensitive })
      setCompleteness(saved.completeness)
      client.setQueryData(kitKeys.profile, saved)
      return saved
    },
    [client, loadPlain],
  )

  const { draft, update } = useDraft<Draft, Payload>({ profile: initial, secrets: {} }, toPayload, save)
  const p = draft.profile
  const set = (patch: Partial<ProfileInput>) => update((d) => ({ ...d, profile: { ...d.profile, ...patch } }))

  const reveal = async () => {
    setRevealing(true)
    try {
      await loadPlain()
      setRevealed(true)
    } catch (err) {
      toastError(err, "Couldn't show your private details")
    } finally {
      setRevealing(false)
    }
  }

  const secretValue = (k: SecretKey) => (draft.secrets[k] !== undefined ? draft.secrets[k] : plain?.[k]) ?? ""
  const secretMask = (k: SecretKey) => (draft.secrets[k] !== undefined || plain ? maskSecret(secretValue(k)) : (initial.sensitive[k] ?? ""))
  const setSecret = (k: SecretKey, v: string) => update((d) => ({ ...d, secrets: { ...d.secrets, [k]: k === "passport_expiry" ? v || null : v } }))

  const hint = nextSteps(profileGaps(p))

  return (
    <div className="lg:grid lg:grid-cols-[minmax(0,1fr)_13rem] lg:gap-10">
      <div className="min-w-0 space-y-8">
        <KitMeterCard completeness={completeness} hint={hint} />

        <KitGroup id="kit-identity" title="Identity" description="As it appears on your passport or national ID.">
          <FormGrid>
            <TextField label="Given name" value={p.given_name} onChange={(v) => set({ given_name: v })} autoComplete="given-name" />
            <TextField label="Family name" value={p.family_name} onChange={(v) => set({ family_name: v })} autoComplete="family-name" />
            <TextField label="Preferred name" value={p.preferred_name} onChange={(v) => set({ preferred_name: v })} hint="What people call you, if different." autoComplete="nickname" />
            <TextField label="Pronouns" value={p.pronouns} onChange={(v) => set({ pronouns: v })} hint="Optional." placeholder="she/her" />
            <TextField label="Date of birth" type="date" value={p.date_of_birth} onChange={(v) => set({ date_of_birth: v || null })} autoComplete="bday" />
            <TextField label="Gender" value={p.gender} onChange={(v) => set({ gender: v })} hint="Optional. Some funds ask, for example women-focused grants." list="kit-genders" />
            <datalist id="kit-genders">
              <option value="Woman" />
              <option value="Man" />
              <option value="Non-binary" />
              <option value="Prefer not to say" />
            </datalist>
            <TextField label="Nationality" value={p.nationality} onChange={(v) => set({ nationality: v })} placeholder="Ghanaian" />
            <TextField label="Country of residence" value={p.country_of_residence} onChange={(v) => set({ country_of_residence: v })} autoComplete="country-name" />
            <TextField label="City" value={p.city} onChange={(v) => set({ city: v })} autoComplete="address-level2" />
            <TextField label="Postal code" value={p.postal_code} onChange={(v) => set({ postal_code: v })} autoComplete="postal-code" hint="Or digital address, such as GA-123-4567." />
            <TextField label="Address line 1" value={p.address_line1} onChange={(v) => set({ address_line1: v })} autoComplete="address-line1" />
            <TextField label="Address line 2" value={p.address_line2} onChange={(v) => set({ address_line2: v })} autoComplete="address-line2" />
          </FormGrid>
        </KitGroup>

        <KitGroup id="kit-contact" title="Contact" description="Where programmes reach you.">
          <FormGrid>
            <TextField label="Email" type="email" value={p.email} onChange={(v) => set({ email: v })} placeholder={user?.email} hint="Leave empty to use your account email." autoComplete="email" />
            <TextField label="Phone" type="tel" value={p.phone} onChange={(v) => set({ phone: v })} placeholder="+233 24 000 0000" autoComplete="tel" />
            <TextField label="LinkedIn" value={p.linkedin_url} onChange={(v) => set({ linkedin_url: v })} placeholder="linkedin.com/in/…" inputMode="url" />
            <TextField label="Website" value={p.website_url} onChange={(v) => set({ website_url: v })} inputMode="url" />
            <TextField label="GitHub" value={p.github_url} onChange={(v) => set({ github_url: v })} placeholder="github.com/…" inputMode="url" />
          </FormGrid>
          <div className="border-t border-separator">
            <Repeatable
              items={p.other_links}
              onChange={(other_links) => set({ other_links })}
              make={() => ({ label: "", url: "" })}
              noun="link"
              title={(l, i) => l.label || `Link ${i + 1}`}
              render={(l, s) => (
                <>
                  <TextField label="Label" value={l.label} onChange={(v) => s({ label: v })} placeholder="Portfolio" />
                  <TextField label="URL" value={l.url} onChange={(v) => s({ url: v })} inputMode="url" />
                </>
              )}
            />
          </div>
        </KitGroup>

        <KitGroup id="kit-about" title="About you" description="Short versions save the most time: forms love a one-line headline and a 300-character bio.">
          <FormGrid>
            <TextField wide label="Headline" value={p.headline} onChange={(v) => set({ headline: v })} maxLength={140} placeholder="Founder of Siwa, building cold storage for smallholder farmers" />
            <TextAreaField label="Short bio" value={p.short_bio} onChange={(v) => set({ short_bio: v })} maxLength={SHORT_BIO_MAX} rows={3} counter hint="A few sentences, in the third person works well." />
            <TextAreaField label="Long bio" value={p.long_bio} onChange={(v) => set({ long_bio: v })} rows={7} hint="Your story in full: background, what you work on and why." />
          </FormGrid>
        </KitGroup>

        <KitGroup id="kit-education" title="Education">
          <Repeatable
            items={p.education}
            onChange={(education) => set({ education })}
            make={emptyEducation}
            noun="education"
            empty="Degrees, diplomas and courses, most recent first."
            title={(e, i) => e.institution || `Education ${i + 1}`}
            render={(e, s) => (
              <>
                <TextField label="Institution" value={e.institution} onChange={(v) => s({ institution: v })} />
                <TextField label="Qualification" value={e.qualification} onChange={(v) => s({ qualification: v })} placeholder="BSc" />
                <TextField label="Field of study" value={e.field} onChange={(v) => s({ field: v })} />
                <TextField label="Grade" value={e.grade} onChange={(v) => s({ grade: v })} placeholder="First class" />
                <TextField label="Started" type="month" value={dateToMonth(e.start)} onChange={(v) => s({ start: v || null })} />
                <TextField label="Finished" type="month" value={dateToMonth(e.end)} onChange={(v) => s({ end: v || null })} hint="Expected date if you're still studying." />
                <TextField label="Country" value={e.country} onChange={(v) => s({ country: v })} />
              </>
            )}
          />
        </KitGroup>

        <KitGroup id="kit-experience" title="Experience">
          <Repeatable
            items={p.experience}
            onChange={(experience) => set({ experience })}
            make={emptyExperience}
            noun="experience"
            empty="Jobs, ventures, volunteering and research roles, most recent first."
            title={(e, i) => [e.role, e.organization].filter(Boolean).join(", ") || `Experience ${i + 1}`}
            render={(e, s) => (
              <>
                <TextField label="Organization" value={e.organization} onChange={(v) => s({ organization: v })} />
                <TextField label="Role" value={e.role} onChange={(v) => s({ role: v })} />
                <TextField label="Started" type="month" value={dateToMonth(e.start)} onChange={(v) => s({ start: v || null })} />
                {e.current ? (
                  <TextField label="Finished" value="Present" onChange={() => undefined} disabled />
                ) : (
                  <TextField label="Finished" type="month" value={dateToMonth(e.end)} onChange={(v) => s({ end: v || null })} />
                )}
                <TextField label="Location" value={e.location} onChange={(v) => s({ location: v })} />
                <CheckField label="I work here now" checked={e.current} onChange={(current) => s({ current, end: current ? null : e.end })} />
                <TextAreaField label="Summary" value={e.summary} onChange={(v) => s({ summary: v })} rows={3} hint="What you did and what changed because of it." />
              </>
            )}
          />
        </KitGroup>

        <KitGroup id="kit-skills" title="Skills and languages">
          <FormGrid>
            <TagInput className="sm:col-span-2" label="Skills" values={p.skills} onChange={(skills) => set({ skills })} placeholder="Product design, Python, Fundraising" hint="Press Enter or type a comma after each one." />
          </FormGrid>
          <div className="border-t border-separator">
            <Repeatable
              items={p.languages}
              onChange={(languages) => set({ languages })}
              make={() => ({ language: "", level: "fluent" as LanguageLevel })}
              noun="language"
              title={(l, i) => l.language || `Language ${i + 1}`}
              render={(l, s) => (
                <>
                  <TextField label="Language" value={l.language} onChange={(v) => s({ language: v })} placeholder="Twi" />
                  <SelectField label="Level" value={l.level} onChange={(v) => s({ level: v as LanguageLevel })} options={LANGUAGE_LEVELS} />
                </>
              )}
            />
          </div>
        </KitGroup>

        <KitGroup id="kit-recognition" title="Awards and publications">
          <Repeatable
            items={p.awards}
            onChange={(awards) => set({ awards })}
            make={() => ({ title: "", issuer: "", year: null })}
            noun="award"
            title={(a, i) => a.title || `Award ${i + 1}`}
            render={(a, s) => (
              <>
                <TextField wide label="Award" value={a.title} onChange={(v) => s({ title: v })} />
                <TextField label="Given by" value={a.issuer} onChange={(v) => s({ issuer: v })} />
                <YearField value={a.year} onChange={(year) => s({ year })} />
              </>
            )}
          />
          <div className="border-t border-separator">
            <Repeatable
              items={p.publications}
              onChange={(publications) => set({ publications })}
              make={() => ({ title: "", venue: "", year: null, url: "" })}
              noun="publication"
              title={(a, i) => a.title || `Publication ${i + 1}`}
              render={(a, s) => (
                <>
                  <TextField wide label="Title" value={a.title} onChange={(v) => s({ title: v })} />
                  <TextField label="Journal, conference or publisher" value={a.venue} onChange={(v) => s({ venue: v })} />
                  <YearField value={a.year} onChange={(year) => s({ year })} />
                  <TextField wide label="Link" value={a.url} onChange={(v) => s({ url: v })} inputMode="url" />
                </>
              )}
            />
          </div>
        </KitGroup>

        <KitGroup id="kit-references" title="References" description="Ask before you list someone, and tell them which programmes may get in touch.">
          <Repeatable
            items={p.references}
            onChange={(references) => set({ references })}
            make={emptyReference}
            noun="reference"
            empty="Most fellowships ask for two or three."
            title={(r, i) => r.name || `Reference ${i + 1}`}
            render={(r, s) => (
              <>
                <TextField label="Name" value={r.name} onChange={(v) => s({ name: v })} />
                <TextField label="Title" value={r.title} onChange={(v) => s({ title: v })} placeholder="Senior Lecturer" />
                <TextField label="Organization" value={r.organization} onChange={(v) => s({ organization: v })} />
                <TextField label="Relationship" value={r.relationship} onChange={(v) => s({ relationship: v })} placeholder="Thesis supervisor" />
                <TextField label="Email" type="email" value={r.email} onChange={(v) => s({ email: v })} />
                <TextField label="Phone" type="tel" value={r.phone} onChange={(v) => s({ phone: v })} />
              </>
            )}
          />
        </KitGroup>

        <KitGroup
          id="kit-private"
          title="Private details"
          description="Encrypted on Blesser. Never sent to an AI model, and only filled into fields that ask for exactly this."
        >
          <div className="flex items-center gap-2 border-b border-separator px-4 py-2.5 text-footnote text-ink-secondary sm:px-5">
            <Lock className="size-3.5 shrink-0" aria-hidden="true" />
            {revealed ? "Shown on this screen until you hide them or leave." : "Hidden. Select a field or the eye to show it."}
          </div>
          <FormGrid>
            <SecretField
              label="National ID number"
              value={secretValue("national_id")}
              masked={secretMask("national_id")}
              revealed={revealed}
              busy={revealing}
              onReveal={() => void reveal()}
              onHide={() => setRevealed(false)}
              onChange={(v) => setSecret("national_id", v)}
              hint="Ghana Card or your country's equivalent."
            />
            <SecretField
              label="Passport number"
              value={secretValue("passport_number")}
              masked={secretMask("passport_number")}
              revealed={revealed}
              busy={revealing}
              onReveal={() => void reveal()}
              onHide={() => setRevealed(false)}
              onChange={(v) => setSecret("passport_number", v)}
            />
            <SecretField
              label="Passport expiry"
              type="date"
              value={secretValue("passport_expiry")}
              masked={secretMask("passport_expiry")}
              revealed={revealed}
              busy={revealing}
              onReveal={() => void reveal()}
              onHide={() => setRevealed(false)}
              onChange={(v) => setSecret("passport_expiry", v)}
            />
          </FormGrid>
        </KitGroup>
      </div>

      <KitRail label="Profile sections" completeness={completeness} hint={hint} sections={SECTIONS} />
    </div>
  )
}

function YearField({ value, onChange }: { value: number | null; onChange: (year: number | null) => void }) {
  const [text, setText] = React.useState(value == null ? "" : String(value))
  return (
    <TextField
      label="Year"
      inputMode="numeric"
      maxLength={4}
      value={text}
      onChange={(v) => {
        const digits = v.replace(/\D/g, "").slice(0, 4)
        setText(digits)
        onChange(digits.length === 4 ? Number(digits) : null)
      }}
    />
  )
}
