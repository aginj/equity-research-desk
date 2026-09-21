import type { ReactNode } from "react";

import { Card, PageHeader } from "@/components/ui";

/** Shared layout for static legal pages (privacy, terms). */
export function LegalPage({
  eyebrow,
  title,
  updated,
  children,
}: {
  eyebrow: string;
  title: string;
  updated: string;
  children: ReactNode;
}) {
  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <PageHeader eyebrow={eyebrow} title={title} description={`Last updated ${updated}.`} />
      <Card className="fade-up px-6 py-2 sm:px-8">
        <div className="legal">{children}</div>
      </Card>
    </div>
  );
}
