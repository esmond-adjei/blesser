import * as React from "react"
import { Link } from "react-router-dom"
import { AppLogo } from "../components/layout/AppLogo"

/** Bumped with api TERMS_VERSION when either notice changes. */
export const TERMS_VERSION = "2026-11-07"

/** Operator contact for privacy and removal requests (build-time). */
const CONTACT = import.meta.env.VITE_CONTACT_EMAIL as string | undefined

function LegalShell({ title, children }: { title: string; children: React.ReactNode }) {
  React.useEffect(() => {
    document.title = `${title}, Blesser`
  }, [title])
  return (
    <div className="mx-auto max-w-2xl px-4 py-10 sm:px-6">
      <a href="/" className="mb-8 flex items-center gap-2.5">
        <AppLogo className="size-8" />
        <span className="text-lg font-bold tracking-tight">Blesser</span>
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
    <>the operator of this Blesser instance</>
  )
}

export function Privacy() {
  return (
    <LegalShell title="Privacy notice">
      <section>
        <h2>What we store about you</h2>
        <ul>
          <li>Your account: email, a hashed password (or your Google sign-in) and display name.</li>
          <li>What you track: applications, their checklists and notes, to-dos, and your notification settings.</li>
          <li>Scans you start, with their agent traces (searches, pages read, tool calls), deleted 90 days after a scan finishes.</li>
          <li>Opportunities you share, which become part of the public catalogue once published.</li>
        </ul>
        <p className="mt-2">
          Deleting your account in Settings removes all of it except opportunities in the public catalogue.
        </p>
      </section>
      <section>
        <h2>Who else sees it</h2>
        <ul>
          <li>The opportunity catalogue is public. Nothing else you store is.</li>
          <li>Your calendar link is private: anyone who has it can see your deadlines and dated to-dos. Make a new one in To-dos if it leaks.</li>
          <li>Scans send search queries, including any focus notes you give, to the web search provider and the language model provider this service uses, and fetch public web pages.</li>
        </ul>
        <p className="mt-2">Nothing is sold.</p>
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
          Blesser lists grants, accelerators, fellowships, scholarships and other opportunities, and helps you track
          your applications, to-dos and deadlines. Listings are found by automated agents and by people, and can be
          wrong or out of date: always check the official page before you apply or rely on a deadline.
        </p>
      </section>
      <section>
        <h2>Your responsibilities</h2>
        <ul>
          <li>Keep your sign-in details safe.</li>
          <li>Only share real opportunities, with a link to their official page.</li>
          <li>Don't use Blesser to send spam, to harass anyone, or to overload the service.</li>
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
