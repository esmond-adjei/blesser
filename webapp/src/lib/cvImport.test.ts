import { describe, expect, it } from "vitest"
import { applyCv, cvSuggestions, defaultChoice, filledMessage, readableCvs, type CvProfile } from "./cvImport"
import type { KitDocument, ProfileInput } from "./kitTypes"

const profile = (patch: Partial<ProfileInput> = {}): ProfileInput => ({
  given_name: "", family_name: "", preferred_name: "", pronouns: "", date_of_birth: null, gender: "", nationality: "", country_of_birth: "", place_of_birth: "",
  country_of_residence: "", city: "", address_line1: "", address_line2: "", postal_code: "", email: "", phone: "",
  linkedin_url: "", website_url: "", github_url: "", other_links: [], headline: "", short_bio: "", long_bio: "",
  education: [], experience: [], skills: [], languages: [], awards: [], publications: [], references: [],
  sensitive: { national_id: "GHA-•••", passport_number: "", passport_expiry: null },
  ...patch,
})

const found: CvProfile = {
  given_name: "Ama Serwaa",
  family_name: "Mensah",
  date_of_birth: "1998-03-14",
  city: "Kumasi",
  linkedin_url: "https://linkedin.com/in/ama",
  skills: ["Python", "Fundraising"],
  education: [
    { institution: "KNUST", qualification: "BSc", field: "Computer Science", grade: "", start: "2016-01-01", end: "2020-07-01", country: "Ghana" },
  ],
  experience: [
    { organization: "Siwa Ltd", role: "Lead Engineer", start: "2022-03-01", end: null, current: true, location: "Kumasi", summary: "" },
    { organization: "Farmhub", role: "Engineer", start: "2020-08-01", end: "2022-02-01", current: false, location: "", summary: "" },
  ],
  languages: [{ language: "Twi", level: "native" }],
}

describe("cvSuggestions", () => {
  it("lists every found detail for an empty profile, ticked, in profile order", () => {
    const list = cvSuggestions(profile(), found)
    expect(list.map((s) => s.id)).toEqual([
      "given_name", "family_name", "date_of_birth", "city", "linkedin_url",
      "education:0", "experience:0", "experience:1", "skills", "languages:0",
    ])
    expect(list.find((s) => s.id === "date_of_birth")?.value).toBe("14 Mar 1998")
    expect(list.find((s) => s.id === "education:0")?.value).toBe("BSc in Computer Science, KNUST, 2016 to 2020")
    expect(list.find((s) => s.id === "experience:0")?.value).toBe("Lead Engineer, Siwa Ltd, 2022 to present")
    expect(list.find((s) => s.id === "languages:0")?.value).toBe("Twi, Native")
    expect(list.find((s) => s.id === "skills")?.value).toBe("Python, Fundraising")
    expect(defaultChoice(list).size).toBe(list.length)
  })

  it("skips what the profile already holds and leaves conflicts unticked", () => {
    const current = profile({
      given_name: "Ama Serwaa",
      family_name: "Owusu",
      linkedin_url: "linkedin.com/in/ama/",
      skills: ["python"],
      experience: [{ organization: "siwa ltd", role: "Lead engineer", start: null, end: null, current: true, location: "", summary: "" }],
    })
    const list = cvSuggestions(current, found)
    const ids = list.map((s) => s.id)
    expect(ids).not.toContain("given_name")
    expect(ids).not.toContain("linkedin_url")
    expect(ids).not.toContain("experience:0")
    expect(list.find((s) => s.id === "skills")?.value).toBe("Fundraising")
    const family = list.find((s) => s.id === "family_name")
    expect(family).toMatchObject({ value: "Mensah", current: "Owusu" })
    expect(defaultChoice(list).has("family_name")).toBe(false)
    expect(defaultChoice(list).has("city")).toBe(true)
  })

  it("lists nothing when the CV adds nothing", () => {
    expect(cvSuggestions(profile({ given_name: "Ama" }), { given_name: "  ama " })).toEqual([])
    expect(cvSuggestions(profile(), {})).toEqual([])
  })

  it("adds an entry the CV repeats only once", () => {
    const twice: CvProfile = { languages: [{ language: "Twi", level: "native" }, { language: "twi", level: "fluent" }] }
    expect(cvSuggestions(profile(), twice).map((s) => s.id)).toEqual(["languages:0"])
  })
})

describe("applyCv", () => {
  it("writes only ticked details, appends new entries and keeps everything else", () => {
    const current = profile({
      family_name: "Owusu",
      phone: "+233 24 000 0000",
      skills: ["python"],
      experience: [{ organization: "Old Co", role: "Intern", start: null, end: null, current: false, location: "", summary: "" }],
    })
    const chosen = defaultChoice(cvSuggestions(current, found))
    chosen.delete("experience:1")
    const next = applyCv(current, found, chosen)
    expect(next.given_name).toBe("Ama Serwaa")
    expect(next.family_name).toBe("Owusu")
    expect(next.phone).toBe("+233 24 000 0000")
    expect(next.skills).toEqual(["python", "Fundraising"])
    expect(next.experience.map((e) => e.organization)).toEqual(["Old Co", "Siwa Ltd"])
    expect(next.education).toHaveLength(1)
    expect(next.sensitive).toEqual(current.sensitive)
    expect(current.experience).toHaveLength(1)
  })

  it("replaces a conflicting value only when the member ticks it", () => {
    const current = profile({ family_name: "Owusu" })
    expect(applyCv(current, found, new Set(["family_name"])).family_name).toBe("Mensah")
    expect(applyCv(current, found, new Set()).family_name).toBe("Owusu")
  })
})

describe("filledMessage", () => {
  it("counts details", () => {
    expect(filledMessage(1)).toBe("Added 1 detail from your CV.")
    expect(filledMessage(6)).toBe("Added 6 details from your CV.")
  })
})

describe("readableCvs", () => {
  const doc = (id: string, patch: Partial<KitDocument>): KitDocument => ({
    id, kind: "other", title: id, filename: `${id}.pdf`, content_type: "application/pdf", size_bytes: 1, project_ids: [], is_default: false, created_at: "2026-11-01T10:00:00", ...patch,
  })

  it("keeps PDF and Word files, CVs first, then the default, then newest", () => {
    const list = readableCvs([
      doc("letter", { kind: "cover_letter", created_at: "2026-11-20T10:00:00" }),
      doc("old-cv", { kind: "cv" }),
      doc("main-cv", { kind: "cv", is_default: true }),
      doc("new-cv", { kind: "cv", content_type: "application/vnd.openxmlformats-officedocument.wordprocessingml.document", created_at: "2026-11-10T10:00:00" }),
      doc("photo", { kind: "cv", content_type: "image/png" }),
      doc("legacy", { kind: "cv", content_type: "application/msword" }),
    ])
    expect(list.map((d) => d.id)).toEqual(["main-cv", "new-cv", "old-cv", "letter"])
  })
})
