import * as React from "react"
import { Link } from "react-router-dom"
import { AppLogo } from "../components/layout/AppLogo"

/** Bumped with api TERMS_VERSION when either notice changes. */
export const TERMS_VERSION = "2026-10-15"

/** Operator contact for privacy and removal requests (build-time). */
const CONTACT = import.meta.env.VITE_CONTACT_EMAIL as string | undefined

/** The marketing site (build-time). */
const SITE_URL = (import.meta.env.VITE_SITE_URL as string | undefined)?.trim()

function LegalShell({ title, children }: { title: string; children: React.ReactNode }) {
  React.useEffect(() => {
    document.title = `${title}, Graduator`
  }, [title])
  return (
    <div className="mx-auto max-w-2xl px-4 py-10 sm:px-6">
      <a href={SITE_URL ?? "/"} className="mb-8 flex items-center gap-2.5">
        <AppLogo className="size-8" />
        <span className="text-lg font-bold tracking-tight">Graduator</span>
      </a>
      <h1 className="type-page-title">{title}</h1>
      <p className="mt-1 type-caption">Version {TERMS_VERSION}</p>
      <div className="rich-text mt-6 space-y-6">
        {children}
      </div>
      <p className="mt-10 flex gap-4 type-caption">
        <Link to="/privacy" className="hover:text-foreground">Privacy</Link>
        <Link to="/terms" className="hover:text-foreground">Terms</Link>
      </p>
    </div>
  )
}

function Contact() {
  return CONTACT ? (
    <a className="text-primary hover:underline" href={`mailto:${CONTACT}`}>{CONTACT}</a>
  ) : (
    <>the operator of this Graduator instance</>
  )
}

export function Privacy() {
  return (
    <LegalShell title="Privacy notice">
      <section>
        <h2>What we store about you</h2>
        <ul>
          <li>Your account: email, a hashed password, display name and profile picture.</li>
          <li>Your research: runs, interest statements, programmes, professors, scores, drafts, applications and chats.</li>
          <li>Uploaded CVs (the file, your base CV text and every tailored version) and any data-export archive you create (kept 7 days).</li>
          <li>Agent traces (pages read, tool calls, checkpoints), deleted 90 days after a task finishes.</li>
          <li>Model usage counts, and model keys you add (encrypted, never shown again).</li>
        </ul>
        <p className="mt-2">
          Deleting your account removes all of it, including CV files and export archives. You can export
          everything first from Settings.
        </p>
      </section>
      <section>
        <h2>Who else sees it</h2>
        <p>To do the research, parts of your data are sent to:</p>
        <ul>
          <li>The language model provider you choose (or the instance's default): your interest statement, CV text when you ask about it, chats, and the pages the agent reads.</li>
          <li>The embedding provider used for alignment scores: your interest statement and paper abstracts.</li>
          <li>Web search providers (Tavily, Brave, or DuckDuckGo where enabled): search queries, which can paraphrase your interest statement.</li>
          <li>OpenAlex, for publication data: professor names and author ids.</li>
          <li>University and lab websites, fetched directly, and the Internet Archive as a fallback copy.</li>
        </ul>
        <p className="mt-2">Nothing is sold, and no email is ever sent on your behalf.</p>
      </section>
      <section>
        <h2>People we research</h2>
        <p>
          Graduator collects publicly available academic information about faculty (name, institution, publications,
          public profile and lab links, photo and bio from faculty pages) into the accounts of students who research
          them. If you are one of them and want your information removed from every account and excluded from future
          research, contact <Contact />. We delete it and record an opt-out.
        </p>
      </section>
      <section>
        <h2>Contact</h2>
        <p>
          Questions, access or deletion requests: <Contact />.
        </p>
      </section>
    </LegalShell>
  )
}

export function Terms() {
  return (
    <LegalShell title="Terms of use">
      <section>
        <h2>The service</h2>
        <p>
          Graduator helps you find graduate programmes and supervisors and drafts outreach emails for you to review.
          Research results come from automated tools and public sources and can be wrong or out of date: check
          anything important before you rely on it.
        </p>
      </section>
      <section>
        <h2>Your responsibilities</h2>
        <ul>
          <li>Keep your sign-in details safe and only upload content you have the right to use.</li>
          <li>Review every draft before you send it. You are the sender, and you are responsible for what it says.</li>
          <li>Don't use Graduator to send bulk or automated email, to harass anyone, or to collect data about people for any other purpose.</li>
        </ul>
      </section>
      <section>
        <h2>Contacting professors</h2>
        <ul>
          <li>Send individual, relevant messages from your own address, and stop if someone asks you to.</li>
          <li>In the US (CAN-SPAM) and the EU/UK (GDPR, ePrivacy), unsolicited messages must identify you honestly and respect opt-outs; academic enquiries are usually fine, mass mailing is not.</li>
          <li>Never claim qualifications you don't have. Fill in every [placeholder] in a draft yourself.</li>
        </ul>
      </section>
      <section>
        <h2>Accounts</h2>
        <p>
          You can delete your account at any time in Settings. We may suspend accounts that break these terms or put
          the service at risk. See the <Link to="/privacy" className="text-primary hover:underline">Privacy notice</Link>{" "}
          for how your data is handled.
        </p>
      </section>
    </LegalShell>
  )
}
