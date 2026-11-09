import type { PublicOpportunity } from "./api"
import { kindLabel } from "./format"

const PROGRAM_KINDS = new Set(["scholarship", "fellowship", "accelerator", "incubator", "training", "internship"])
const GRANT_KINDS = new Set(["grant", "call_for_proposals"])

export function organizationLd(site: string) {
  return {
    "@context": "https://schema.org",
    "@type": "Organization",
    name: "Blesser",
    url: `${site}/`,
    logo: `${site}/favicon.svg`,
    description: "Grants, fellowships, scholarships and accelerators for startups, researchers and students in Ghana.",
    areaServed: { "@type": "Country", name: "Ghana" },
  }
}

/** JobPosting would misdescribe these listings, so pick the closest honest schema.org type. */
export function opportunityLd(opp: PublicOpportunity, url: string) {
  const provider = opp.organization ? { "@type": "Organization", name: opp.organization } : undefined
  const base = {
    "@context": "https://schema.org",
    name: opp.title,
    description: opp.summary || undefined,
    url,
    sameAs: opp.link || undefined,
    keywords: [kindLabel(opp.kind), ...opp.tags].join(", "),
  }
  if (PROGRAM_KINDS.has(opp.kind))
    return {
      ...base,
      "@type": "EducationalOccupationalProgram",
      provider,
      applicationDeadline: opp.deadline_date ?? undefined,
      programPrerequisites: opp.eligibility || undefined,
    }
  if (GRANT_KINDS.has(opp.kind)) return { ...base, "@type": "MonetaryGrant", funder: provider }
  return {
    ...base,
    "@type": "CreativeWork",
    author: provider,
    datePublished: opp.published_at ?? undefined,
    expires: opp.deadline_date ?? undefined,
  }
}
