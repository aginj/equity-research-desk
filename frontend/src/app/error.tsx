"use client";

import Link from "next/link";
import { useEffect } from "react";

import { IconAlert } from "@/components/icons";
import { Button, Card } from "@/components/ui";

export default function ErrorBoundary({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  useEffect(() => {
    // Surface to the browser console; wire a real reporter (Sentry, etc.) here in production.
    console.error("Desk page crashed", error);
  }, [error]);

  return (
    <Card className="fade-up mx-auto max-w-xl p-8">
      <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-danger-soft text-danger">
        <IconAlert size={22} />
      </div>
      <h1 className="mt-5 text-2xl font-semibold tracking-tight text-fg">Something went wrong rendering this page.</h1>
      <p className="mt-2 text-sm leading-relaxed text-muted">
        {error.message || "Unexpected error."}
        {error.digest ? <span className="mono"> · ref {error.digest}</span> : null}
      </p>
      <div className="mt-6 flex gap-3">
        <Button onClick={reset}>Try again</Button>
        <Link href="/">
          <Button variant="secondary">Back to desk</Button>
        </Link>
      </div>
    </Card>
  );
}
