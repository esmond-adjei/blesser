import type { ImageMetadata } from "astro"
import startups from "@blesser/ui/illustrations/site-startups-768.webp"
import researchers from "@blesser/ui/illustrations/site-researchers-768.webp"
import students from "@blesser/ui/illustrations/site-students-768.webp"

export type Landing = {
  slug: string
  title: string
  intro: string
  filter: { kind: string } | { category: string }
  illustration?: ImageMetadata
}

const kind = (slug: string, k: string, title: string, intro: string): Landing => ({
  slug,
  title,
  intro,
  filter: { kind: k },
})

export const CATEGORY_LANDINGS: Landing[] = [
  {
    slug: "startups",
    title: "For startups",
    intro: "Accelerators, grants, competitions and equity-free funding for founders building in Ghana.",
    filter: { category: "startup" },
    illustration: startups,
  },
  {
    slug: "researchers",
    title: "For researchers",
    intro: "Research grants, calls for proposals and fellowships for researchers at Ghanaian institutions and beyond.",
    filter: { category: "research" },
    illustration: researchers,
  },
  {
    slug: "students",
    title: "For students",
    intro: "Scholarships, internships, exchanges and competitions for students in Ghana, at home and abroad.",
    filter: { category: "student" },
    illustration: students,
  },
]

export const KIND_LANDINGS: Landing[] = [
  kind("grants", "grant", "Grants", "Funding you don't pay back, for projects, research and ventures."),
  kind("scholarships", "scholarship", "Scholarships", "Funded places to study, from first degrees to doctorates."),
  kind("fellowships", "fellowship", "Fellowships", "Paid programmes that back you to learn, lead or research."),
  kind("accelerators", "accelerator", "Accelerators", "Cohort programmes with mentoring, investor access and often funding."),
  kind("incubators", "incubator", "Incubators", "Space, support and advice for early-stage ventures."),
  kind("competitions", "competition", "Competitions", "Pitch, prize and innovation challenges with real rewards."),
  kind("internships", "internship", "Internships", "Paid and funded placements to gain experience."),
  kind("calls-for-proposals", "call_for_proposals", "Calls for proposals", "Funders inviting proposals for projects and research."),
  kind("training", "training", "Training", "Courses, bootcamps and programmes to build your skills."),
  kind("conferences", "conference", "Conferences", "Events with funded places, travel grants or calls to present."),
  kind("jobs", "job", "Jobs", "Roles with organisations that back opportunity in Ghana."),
]

export const LANDINGS = [...CATEGORY_LANDINGS, ...KIND_LANDINGS]

export const landingFor = (slug: string) => LANDINGS.find((l) => l.slug === slug)

export const landingForKind = (k: string) =>
  KIND_LANDINGS.find((l) => "kind" in l.filter && l.filter.kind === k)
