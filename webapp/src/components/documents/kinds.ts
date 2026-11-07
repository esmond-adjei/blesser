import type { DocumentKind } from "../../lib/types"

/** The kinds of document, in menu order (api/cv/kinds.py). Emails are
 * not one: they are Outbox drafts. */
export const KINDS: DocumentKind[] = ["cv", "sop", "diversity_statement", "research_proposal", "interest", "note"]

export const KIND: Record<
  DocumentKind,
  { label: string; plural: string; short: string; noun: string; title: string; starter: string; placeholder: string }
> = {
  cv: {
    label: "CV",
    plural: "CVs",
    short: "CV",
    noun: "CV",
    title: "My CV",
    starter: "# Your Name\n\nemail@example.com\n\n## Education\n\n## Research experience\n\n## Publications\n\n## Skills\n",
    placeholder: "Write your CV: a Title for your name, headings for sections, lists for details.",
  },
  sop: {
    label: "Statement of purpose",
    plural: "Statements of purpose",
    short: "SOP",
    noun: "statement of purpose",
    title: "Statement of purpose",
    starter: "# Statement of purpose\n\n",
    placeholder: "Write your statement: why this field, what you've done, why this program.",
  },
  diversity_statement: {
    label: "Diversity statement",
    plural: "Diversity statements",
    short: "Diversity",
    noun: "diversity statement",
    title: "Diversity statement",
    starter: "# Diversity statement\n\n",
    placeholder: "Write your diversity statement.",
  },
  research_proposal: {
    label: "Research proposal",
    plural: "Research proposals",
    short: "Proposal",
    noun: "research proposal",
    title: "Research proposal",
    starter: "# Research proposal\n\n## Background\n\n## Questions\n\n## Approach\n\n## Timeline\n",
    placeholder: "Write your proposal: background, questions, approach.",
  },
  interest: {
    label: "Interest statement",
    plural: "Interest statements",
    short: "Interests",
    noun: "interest statement",
    title: "Interest statement",
    starter: "# Research interests\n\n",
    placeholder: "Write what you want to work on, and why.",
  },
  note: {
    label: "Note",
    plural: "Notes",
    short: "Note",
    noun: "note",
    title: "Note",
    starter: "",
    placeholder: "Write a note.",
  },
}

export function kindOf(kind: string | null | undefined): DocumentKind {
  return (KINDS as string[]).includes(kind ?? "") ? (kind as DocumentKind) : "cv"
}

export function isKind(value: string | null | undefined): value is DocumentKind {
  return (KINDS as string[]).includes(value ?? "")
}
