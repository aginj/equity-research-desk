import Link from "next/link";

import { Button, Card } from "@/components/ui";

export default function NotFound() {
  return (
    <Card className="fade-up mx-auto max-w-xl p-8">
      <div className="eyebrow">404</div>
      <h1 className="mt-3 text-2xl font-semibold tracking-tight text-fg">That page is not on the desk.</h1>
      <p className="mt-2 text-sm text-muted">Check the address, or head back to the ranked book.</p>
      <Link href="/" className="mt-6 inline-block">
        <Button variant="secondary">Back to book</Button>
      </Link>
    </Card>
  );
}
