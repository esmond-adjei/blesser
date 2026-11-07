import { WAITLIST_MODE } from "./site"

/**
 * The questions a cautious applicant actually asks. Used on the home page
 * (a short list) and on its own page (the full list).
 */

export interface FaqLink {
  label: string
  href: string
}

export interface FaqItem {
  question: string
  answer: string
  links?: FaqLink[]
}

export const FAQ: FaqItem[] = [
  {
    question: "Does Graduator email professors for me?",
    answer:
      "No. Every draft waits in your Outbox until you edit it, approve it and send it yourself from your own address. Nothing is ever sent on your behalf, and there is no bulk-mail feature to misuse.",
  },
  {
    question: "Where does the publication data come from?",
    answer:
      "OpenAlex is the main source. When OpenAlex has nobody at a school, Graduator falls back to DBLP, and to NIH RePORTER and NSF award records for US schools. It also reads ORCID and DBLP ids linked next to a name on a faculty page. Every match names the source behind it.",
  },
  {
    question: "How are the fit scores calculated?",
    answer:
      "They are measured similarity between your interest statement and the professor's papers, using embeddings, not a language model's opinion. Each match shows the papers behind its score, a plain-English reason, and which embedding model scored it.",
  },
  {
    question: "How long does a run take?",
    answer:
      "Minutes to a couple of hours, depending on how many programmes and professors you cover. Progress is saved after every step, so you can close the tab, come back later and pick up where it stopped.",
  },
  {
    question: "What happens if a professor is not in any source?",
    answer:
      "They do not appear. Graduator only reports what a tool actually returned, so a missing professor is a gap in the public sources rather than a guess. It will tell you when it had to fall back to a weaker source.",
  },
  {
    question: "Can I use my own AI model and key?",
    answer:
      "Yes. Anthropic, OpenAI, Gemini, Ollama, or any OpenAI-compatible server. Your key is encrypted at rest, used only for your own calls, and never shown again. Without one, a default model is used.",
  },
  {
    question: "Is my CV sent anywhere?",
    answer:
      "Only to the model provider you chose, and only when you ask it to read the CV. You can export everything your account owns as one ZIP and delete your account in a click.",
  },
  {
    question: "Do I need a credit card?",
    answer:
      "No. The Free plan needs no card. Paid plans take a card or mobile money, and none of them renews on its own.",
    ...(WAITLIST_MODE ? {} : { links: [{ label: "See the plans", href: "/pricing" }] }),
  },
]
