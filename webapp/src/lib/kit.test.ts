import { describe, expect, it } from "vitest"
import {
  completenessLabel,
  emptyProject,
  formatBytes,
  guessKind,
  limitFromQuestion,
  limitStatus,
  maskSecret,
  monthToDate,
  nextSteps,
  normalizeAnswer,
  normalizeMoney,
  normalizeProfile,
  normalizeProject,
  normalizeUrl,
  parseYear,
  profileGaps,
  titleFromFilename,
  uploadProblem,
  wordCount,
} from "./kit"
import type { Profile } from "./kitTypes"

const profile = (patch: Partial<Profile> = {}): Profile => ({
  given_name: "", family_name: "", preferred_name: "", pronouns: "", date_of_birth: null, gender: "", nationality: "",
  country_of_residence: "", city: "", address_line1: "", address_line2: "", postal_code: "", email: "", phone: "",
  linkedin_url: "", website_url: "", github_url: "", other_links: [], headline: "", short_bio: "", long_bio: "",
  education: [], experience: [], skills: [], languages: [], awards: [], publications: [], references: [],
  sensitive: { national_id: "", passport_number: "", passport_expiry: null },
  completeness: 0, updated_at: "2026-11-09T10:00:00Z",
  ...patch,
})

describe("completenessLabel", () => {
  it("names each band and clamps out-of-range values", () => {
    expect(completenessLabel(0)).toBe("Not started")
    expect(completenessLabel(12)).toBe("Just started")
    expect(completenessLabel(55)).toBe("Taking shape")
    expect(completenessLabel(99.4)).toBe("Nearly there")
    expect(completenessLabel(100)).toBe("Complete")
    expect(completenessLabel(140)).toBe("Complete")
    expect(completenessLabel(-5)).toBe("Not started")
    expect(completenessLabel(Number.NaN)).toBe("Not started")
  })
})

describe("nextSteps and profileGaps", () => {
  it("lists the first gaps and counts the rest", () => {
    expect(nextSteps(["a phone number", "a short bio", "your education", "skills", "languages"])).toBe(
      "Add a phone number, a short bio, your education and 2 more.",
    )
    expect(nextSteps(["a headline"])).toBe("Add a headline.")
    expect(nextSteps([])).toBeNull()
  })

  it("treats blank repeatable rows as missing", () => {
    const gaps = profileGaps(profile({ given_name: "Ama", family_name: "Mensah", education: [{ institution: " ", qualification: "", field: "", start: null, end: null, grade: "", country: "" }] }))
    expect(gaps).not.toContain("your name")
    expect(gaps).toContain("your education")
  })
})

describe("wordCount", () => {
  it("counts words the way forms do", () => {
    expect(wordCount("")).toBe(0)
    expect(wordCount("   ")).toBe(0)
    expect(wordCount("Siwa keeps produce cold.")).toBe(4)
    expect(wordCount("Cold-chain — for 2,000 farmers\nin Tamale")).toBe(6)
    expect(wordCount("Ɔdɔ yɛ dɛ")).toBe(3)
  })
})

describe("limitFromQuestion", () => {
  it("reads word and character limits", () => {
    expect(limitFromQuestion("Describe your solution in 100 words")).toEqual({ count: 100, unit: "words" })
    expect(limitFromQuestion("Why this fellowship? (max 1,500 characters)")).toEqual({ count: 1500, unit: "characters" })
    expect(limitFromQuestion("Your pitch, 250-word limit")).toEqual({ count: 250, unit: "words" })
    expect(limitFromQuestion("Tell us about your team")).toBeNull()
  })

  it("flags answers that run over or close to the limit", () => {
    expect(limitStatus("one two three", { count: 2, unit: "words" })).toEqual({ used: 3, over: true, near: false })
    expect(limitStatus("abcdefghij", { count: 10, unit: "characters" })).toEqual({ used: 10, over: false, near: true })
    expect(limitStatus("one two", null)).toEqual({ used: 2, over: false, near: false })
  })
})

describe("normalisation", () => {
  it("adds a scheme to bare links and leaves full ones alone", () => {
    expect(normalizeUrl(" linkedin.com/in/ama ")).toBe("https://linkedin.com/in/ama")
    expect(normalizeUrl("http://siwa.africa")).toBe("http://siwa.africa")
    expect(normalizeUrl("mailto:ama@siwa.africa")).toBe("mailto:ama@siwa.africa")
    expect(normalizeUrl("  ")).toBe("")
  })

  it("turns months into dates and junk years into null", () => {
    expect(monthToDate("2019-09")).toBe("2019-09-01")
    expect(monthToDate("2019-09-14")).toBe("2019-09-14")
    expect(monthToDate("")).toBeNull()
    expect(parseYear("2024")).toBe(2024)
    expect(parseYear("24")).toBeNull()
    expect(parseYear(null)).toBeNull()
  })

  it("trims, drops empty rows and read-only fields from a profile", () => {
    const out = normalizeProfile(
      profile({
        given_name: "  Ama ",
        linkedin_url: "linkedin.com/in/ama",
        skills: [" Python ", "Python", ""],
        education: [
          { institution: "KNUST", qualification: "BSc", field: "", start: "2016-09", end: "2020-07", grade: "", country: "Ghana" },
          { institution: "", qualification: "", field: "", start: null, end: null, grade: "", country: "" },
        ],
        experience: [{ organization: "Siwa", role: "Founder", start: "2021-01", end: "2023-01", current: true, location: "", summary: "" }],
        awards: [{ title: "Tony Elumelu", issuer: "TEF", year: "2023" as unknown as number }],
        languages: [{ language: " ", level: "fluent" }],
        date_of_birth: "",
      }),
    )
    expect(out).not.toHaveProperty("completeness")
    expect(out).not.toHaveProperty("updated_at")
    expect(out.given_name).toBe("Ama")
    expect(out.linkedin_url).toBe("https://linkedin.com/in/ama")
    expect(out.skills).toEqual(["Python"])
    expect(out.education).toHaveLength(1)
    expect(out.education[0].start).toBe("2016-09-01")
    expect(out.experience[0].end).toBeNull()
    expect(out.awards[0].year).toBe(2023)
    expect(out.languages).toEqual([])
    expect(out.date_of_birth).toBeNull()
  })

  it("strips server fields from a project and cleans its lists", () => {
    const out = normalizeProject({
      ...emptyProject(" Siwa "),
      id: "p1", completeness: 40, created_at: "", updated_at: "",
      website_url: "siwa.africa",
      amount_sought: "250,000",
      team_size: 0,
      document_ids: ["d1", "d1", "d2"],
      custom_fields: [{ label: "TIN", value: "C000" }, { label: "", value: "" }],
      team: [{ name: "", role: "", bio: "", email: "", linkedin_url: "", is_founder: false, gender: "" }],
    } as never)
    expect(out).not.toHaveProperty("id")
    expect(out.name).toBe("Siwa")
    expect(out.website_url).toBe("https://siwa.africa")
    expect(out.document_ids).toEqual(["d1", "d2"])
    expect(out.custom_fields).toEqual([{ label: "TIN", value: "C000" }])
    expect(out.team).toEqual([])
    expect(out.amount_sought).toBe("250000")
    expect(out.team_size).toBeNull()
  })

  it("turns money into plain decimals", () => {
    expect(normalizeMoney("GHS 410,000")).toBe("410000")
    expect(normalizeMoney(" 25 000.50 ")).toBe("25000.50")
    expect(normalizeMoney("")).toBe("")
  })

  it("cleans an answer", () => {
    expect(normalizeAnswer({ question: " Why? ", answer: " Because ", tags: ["impact", " impact", ""], project_id: "" })).toEqual({
      question: "Why?", answer: "Because", tags: ["impact"], project_id: null,
    })
  })
})

describe("documents", () => {
  it("formats sizes", () => {
    expect(formatBytes(0)).toBe("0 B")
    expect(formatBytes(1536)).toBe("1.5 KB")
    expect(formatBytes(15 * 1024 * 1024)).toBe("15 MB")
    expect(formatBytes(250 * 1024 * 1024)).toBe("250 MB")
  })

  it("guesses a kind from the file name", () => {
    expect(guessKind("Ama_Mensah_CV_2026.pdf")).toBe("cv")
    expect(guessKind("resume.docx")).toBe("cv")
    expect(guessKind("Siwa Pitch Deck.pdf")).toBe("pitch_deck")
    expect(guessKind("siwa-logo.png")).toBe("logo")
    expect(guessKind("headshot.jpg")).toBe("photo")
    expect(guessKind("Ghana card scan.pdf")).toBe("id_document")
    expect(guessKind("budget 2027.xlsx")).toBe("budget")
    expect(guessKind("notes.pdf")).toBe("other")
  })

  it("makes a readable title", () => {
    expect(titleFromFilename("Ama_Mensah-CV_2026.pdf")).toBe("Ama Mensah CV 2026")
    expect(titleFromFilename(".pdf")).toBe(".pdf")
  })

  it("rejects files the server would refuse", () => {
    expect(uploadProblem({ name: "deck.pdf", size: 1000 })).toBeNull()
    expect(uploadProblem({ name: "virus.exe", size: 1000 })).toMatch(/isn't supported/)
    expect(uploadProblem({ name: "big.pdf", size: 16 * 1024 * 1024 })).toMatch(/up to 15 MB/)
    expect(uploadProblem({ name: "deck.pdf", size: 2000 }, { used_bytes: 9000, limit_bytes: 10000 })).toMatch(/storage/)
  })

  it("masks all but the last four characters", () => {
    expect(maskSecret("GHA-123456789-0")).toBe("••••••••89-0")
    expect(maskSecret("123")).toBe("•••")
    expect(maskSecret("")).toBe("")
  })
})
