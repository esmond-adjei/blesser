import { describe, expect, it } from "vitest"
import { collectFields } from "../src/content/collect"
import { byLabel, loadFixture } from "./helpers"

const collect = (name: string) => collectFields(loadFixture(name)).fields

describe("collectFields", () => {
  it("reads Microsoft Forms labels without question numbers or hidden type hints", () => {
    const fields = collect("microsoft-forms.html")
    expect(fields.map((f) => f.label)).toEqual(["Full name (as shown on official identification)", "Date of birth", "Gender"])
    expect(byLabel(fields, "Date of birth")).toMatchObject({ tag: "input", type: "text", placeholder: "Please input date (M/d/yyyy)" })
    expect(byLabel(fields, "Gender").options.map((o) => o.label)).toEqual(["Woman", "Man"])
  })

  it("reads Google Forms questions, descriptions and custom widgets", () => {
    const fields = collect("google-forms.html")
    const name = byLabel(fields, "Full name")
    expect(name).toMatchObject({ tag: "input", type: "text", required: true, help_text: "As it appears on your ID", custom: false })
    expect(byLabel(fields, "Email").type).toBe("email")
    const problem = byLabel(fields, "Describe the problem your venture solves")
    expect(problem).toMatchObject({ tag: "textarea", word_limit: 150, required: true })
    const stage = byLabel(fields, "Stage of your venture")
    expect(stage).toMatchObject({ type: "radio", custom: true })
    expect(stage.options.map((o) => o.label)).toEqual(["Idea", "Prototype", "Early revenue"])
    expect(byLabel(fields, "Sectors")).toMatchObject({ type: "checkbox", custom: true })
    expect(byLabel(fields, "Sectors").options.map((o) => o.value)).toEqual(["Agriculture", "Health"])
    const country = byLabel(fields, "Country")
    expect(country).toMatchObject({ tag: "select", custom: true })
    expect(country.options.map((o) => o.label)).toEqual(["Choose", "Ghana", "Nigeria"])
    expect(name.section).toBe("Siwa Accelerator 2026: application")
  })

  it("reads Greenhouse labels, file inputs, selects and checkbox groups, and skips honeypots", () => {
    const fields = collect("greenhouse.html")
    expect(fields.map((f) => f.label)).toEqual([
      "First Name",
      "Last Name",
      "Email",
      "Phone",
      "Resume/CV",
      "LinkedIn Profile",
      "Are you legally authorized to work in Ghana?",
      "Why do you want to work with us? (300 words max)",
      "Which programmes interest you?",
      "Gender",
    ])
    expect(byLabel(fields, "First Name")).toMatchObject({ required: true, max_length: 255, autocomplete: "given-name", section: "Submit your application" })
    expect(byLabel(fields, "Resume/CV")).toMatchObject({ type: "file", accept: ".pdf,.doc,.docx,.txt,.rtf", required: true })
    expect(byLabel(fields, "Resume/CV").help_text).toContain("File types")
    expect(byLabel(fields, "Are you legally authorized to work in Ghana?").options).toEqual([
      { value: "0", label: "No" },
      { value: "1", label: "Yes" },
    ])
    expect(byLabel(fields, "Why do you want to work with us? (300 words max)")).toMatchObject({ word_limit: 300, section: "Additional questions" })
    const programmes = byLabel(fields, "Which programmes interest you?")
    expect(programmes).toMatchObject({ type: "checkbox", required: true })
    expect(programmes.options).toEqual([
      { value: "101", label: "Fellowship" },
      { value: "102", label: "Accelerator" },
      { value: "103", label: "Grants" },
    ])
    expect(byLabel(fields, "Gender").custom).toBe(true)
  })

  it("reads Lever's wrapping labels, descriptions and radio cards", () => {
    const fields = collect("lever.html")
    expect(fields.map((f) => f.label)).toEqual([
      "Resume/CV",
      "Full name",
      "Email",
      "Current company",
      "LinkedIn URL",
      "Tell us about a project you are proud of",
      "Will you need visa sponsorship?",
    ])
    expect(byLabel(fields, "Resume/CV")).toMatchObject({ type: "file", required: true })
    expect(byLabel(fields, "LinkedIn URL").section).toBe("Links")
    expect(byLabel(fields, "Tell us about a project you are proud of")).toMatchObject({
      required: true,
      help_text: "Keep it under 200 words.",
      word_limit: 200,
    })
    expect(byLabel(fields, "Will you need visa sponsorship?").options).toEqual([
      { value: "Yes", label: "Yes" },
      { value: "No", label: "No" },
    ])
  })

  it("reads Workable fields and never collects passwords", () => {
    const fields = collect("workable.html")
    expect(fields.map((f) => f.label)).toEqual([
      "First name",
      "Last name",
      "Phone",
      "Date of birth",
      "Summary",
      "Country",
      "Cover letter",
      "I agree to the processing of my data",
    ])
    expect(byLabel(fields, "First name").required).toBe(true)
    expect(byLabel(fields, "Summary")).toMatchObject({ max_length: 500, help_text: "Max 500 characters", section: "Profile" })
    expect(byLabel(fields, "Country").options.map((o) => o.value)).toEqual(["GH", "KE", "NG"])
    expect(byLabel(fields, "Date of birth").type).toBe("date")
    expect(byLabel(fields, "I agree to the processing of my data")).toMatchObject({ type: "checkbox", options: [{ value: "true", label: "I agree to the processing of my data" }] })
  })

  it("reads Submittable legends and rich text, and skips payment fields", () => {
    const fields = collect("submittable.html")
    expect(fields.map((f) => f.label)).toEqual([
      "Organisation name",
      "Registration number",
      "Year founded",
      "Project summary",
      "Amount requested (USD)",
      "Budget",
    ])
    expect(byLabel(fields, "Organisation name")).toMatchObject({ section: "About your organisation", required: true })
    expect(byLabel(fields, "Project summary")).toMatchObject({ tag: "contenteditable", word_limit: 250, required: true, section: "Project narrative" })
  })

  it("reads a plain grant form with unlabelled inputs and skips hidden and password fields", () => {
    const fields = collect("plain-grant.html")
    expect(fields.map((f) => f.label)).toEqual([
      "Applicant name",
      "Date of birth (DD/MM/YYYY)",
      "Phone number",
      "Project title",
      "What will the grant pay for? (up to 100 words)",
      "Is the project led by women?",
    ])
    expect(byLabel(fields, "Project title").section).toBe("Your project")
    expect(byLabel(fields, "What will the grant pay for? (up to 100 words)").word_limit).toBe(100)
    expect(byLabel(fields, "Is the project led by women?").options).toEqual([
      { value: "yes", label: "Yes" },
      { value: "no", label: "No" },
    ])
  })

  it("gives every field a unique key", () => {
    const fields = collect("greenhouse.html")
    expect(new Set(fields.map((f) => f.key)).size).toBe(fields.length)
  })
})
