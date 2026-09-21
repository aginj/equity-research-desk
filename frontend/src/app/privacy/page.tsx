import type { Metadata } from "next";

import { LegalPage } from "@/components/LegalPage";

export const metadata: Metadata = { title: "Privacy" };

export default function PrivacyPage() {
  return (
    <LegalPage eyebrow="Privacy notice" title="What we store, and why" updated="September 2026">
      <h2>Reading the desk</h2>
      <p>
        You can read the ranked book, research tape, idea pages, and run history without an account. For anonymous
        visitors we keep standard server access logs (IP address, user agent, requested URL, timestamp) for security
        and rate limiting, rotated automatically. Your chosen venue and appetite are stored only in your browser&apos;s
        local storage.
      </p>

      <h2>Signing in</h2>
      <p>
        Sign-in is optional and uses Google, GitHub, or a one-time email link. We do not store passwords. When you sign
        in we receive and store your <strong>email address</strong>, <strong>display name</strong>, and{" "}
        <strong>profile image URL</strong> from the provider, plus the technical identifiers needed to recognise your
        account on the next visit. We never receive your provider password and do not request access to your contacts,
        repositories, or calendars.
      </p>

      <h2>Your workspace</h2>
      <p>
        Signed-in users can save a preferred venue, a risk appetite, and a watchlist of ticker symbols with optional
        notes. This data is used solely to render your view of the shared research and to show desk administrators
        which uncovered tickers users are interested in (aggregated by ticker, not attributed to you).
      </p>

      <h2>Cookies</h2>
      <p>
        We set a single encrypted session cookie after sign-in and a CSRF token required by the sign-in flow. Both are{" "}
        <code>HttpOnly</code>, <code>Secure</code>, and <code>SameSite=Lax</code>. No advertising or third-party
        analytics cookies are set.
      </p>

      <h2>Third parties</h2>
      <p>
        Identity providers (Google, GitHub, Resend for email delivery) process the data needed to sign you in under
        their own privacy policies. Market data and news are fetched from licensed vendors by the server; your personal
        data is never sent to them or to language-model providers.
      </p>

      <h2>Retention and deletion</h2>
      <p>
        Account and workspace data is kept until you ask us to delete it. Email the operator listed on the sign-in
        page to delete your account; we remove the account, preferences, and watchlist within 30 days. Encrypted
        database backups are retained for 14 days and then expire.
      </p>

      <h2>Contact</h2>
      <p>Questions about this notice go to the operator email configured for this deployment.</p>
    </LegalPage>
  );
}
