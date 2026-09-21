import type { Metadata } from "next";

import { LegalPage } from "@/components/LegalPage";

export const metadata: Metadata = { title: "Terms" };

export default function TermsPage() {
  return (
    <LegalPage eyebrow="Terms of use" title="Research only. Not investment advice." updated="September 2026">
      <h2>What this is</h2>
      <p>
        Equity Research Desk is an automated equity research tool. It aggregates licensed news, regulatory filings, and market
        data, then produces ranked, sourced write-ups under a deterministic policy layer. It is provided for research
        and educational purposes.
      </p>

      <h2>What this is not</h2>
      <p>
        Nothing on this site is personalised investment advice, a recommendation to buy or sell any security, or an
        offer or solicitation. The operator is not a broker-dealer or registered investment adviser and does not
        execute trades. Ratings such as &ldquo;accumulate&rdquo; or &ldquo;reduce&rdquo; are outputs of a model and a
        rule set applied to a fixed universe; they are not tailored to your circumstances.
      </p>

      <h2>Accuracy</h2>
      <p>
        Data vendors, filings, and language models can be wrong, late, or incomplete. Headlines are often already
        reflected in prices. Every idea page lists its sources so you can verify them yourself. You are responsible
        for your own decisions and for consulting a qualified professional where appropriate.
      </p>

      <h2>Accounts</h2>
      <p>
        Accounts are optional and free. You must not attempt to access other users&apos; workspaces, bypass rate
        limits, or automate requests beyond ordinary browsing. The operator may suspend accounts that abuse the
        service.
      </p>

      <h2>Content and licensing</h2>
      <p>
        Headlines, filings, and quotes remain the property of their publishers and are displayed with attribution
        and a link to the source. Do not redistribute vendor data obtained through this site.
      </p>

      <h2>Availability and changes</h2>
      <p>
        The service is provided &ldquo;as is&rdquo; without warranties of any kind. Runs may be delayed or fail; the
        book may be stale. The operator may change or discontinue features, and may update these terms; continued
        use after a change constitutes acceptance.
      </p>

      <h2>Liability</h2>
      <p>
        To the fullest extent permitted by law, the operator is not liable for any loss arising from reliance on
        information presented here, including trading losses.
      </p>
    </LegalPage>
  );
}
