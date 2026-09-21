"use client";

import Link from "next/link";
import { useMemo, useState, type FormEvent } from "react";

import { AppetiteCards } from "@/components/AppetiteCards";
import { IconAlert, IconArrowUpRight, IconPlus, IconStarFilled, IconX } from "@/components/icons";
import { MarketSwitcher } from "@/components/MarketSwitcher";
import { useWorkspace } from "@/components/WorkspaceProvider";
import { Alert, Badge, Button, Card, CardHeader, EmptyState, PageHeader, Skeleton } from "@/components/ui";
import { ideaHref, relativeTime } from "@/lib/format";

export default function WorkspacePage() {
  const { auth, user, market, appetite, setAppetite, watchlist, toggleWatch, loading, error } = useWorkspace();
  const [draft, setDraft] = useState("");
  const [adding, setAdding] = useState(false);

  const covered = useMemo(() => watchlist.filter((w) => w.covered), [watchlist]);
  const requested = useMemo(() => watchlist.filter((w) => !w.covered), [watchlist]);

  async function addTicker(event: FormEvent) {
    event.preventDefault();
    const symbol = draft.trim().toUpperCase();
    if (!symbol) return;
    setAdding(true);
    try {
      await toggleWatch(symbol);
      setDraft("");
    } finally {
      setAdding(false);
    }
  }

  // Middleware already redirects anonymous visitors; this guards the brief client-side gap.
  if (auth === "anonymous") {
    return (
      <EmptyState
        title="Sign in to open your workspace"
        description="Your venue, appetite, and watchlist are saved to your account."
        action={
          <Link href="/signin?callbackUrl=%2Fworkspace" className="inline-flex h-10 items-center rounded-xl bg-accent px-4 text-sm font-medium text-accent-fg">
            Sign in
          </Link>
        }
      />
    );
  }

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Personal workspace"
        title={user?.name ? `${user.name.split(" ")[0]}'s desk view` : "Your desk view"}
        description="These settings change how you see the shared book: which venue, which policy appetite, and which names are starred. They never change what the desk analyzes or cost anything to run."
        actions={market ? <Badge tone="accent">{market.label}</Badge> : null}
      />

      {error ? (
        <Alert tone="danger" icon={<IconAlert size={16} />}>
          {error}
        </Alert>
      ) : null}

      <div className="grid gap-4 lg:grid-cols-[0.9fr_1.1fr]">
        <Card className="fade-up">
          <CardHeader title="Venue" description="The book, tape, and run history follow this venue." />
          <div className="px-5 py-4">
            <MarketSwitcher />
          </div>
        </Card>

        <Card className="fade-up">
          <CardHeader
            title="Risk appetite"
            description="Re-ranks the latest run under your limits — no new agents, no new data pulls."
          />
          <div className="p-5">
            <AppetiteCards value={loading ? null : appetite} onChange={(next) => void setAppetite(next)} disabled={loading} />
          </div>
        </Card>
      </div>

      <Card className="fade-up">
        <CardHeader
          title="Watchlist"
          description={`Starred names for ${market?.label ?? "this venue"}. Filter the desk to them, or star from any idea page.`}
          action={
            <Badge tone="neutral" className="mono tabular">
              {watchlist.length}
            </Badge>
          }
        />
        <div className="grid gap-5 p-5 lg:grid-cols-[0.8fr_1.2fr]">
          <form onSubmit={addTicker} className="space-y-3">
            <label className="block">
              <span className="mb-1.5 block text-xs font-medium text-fg-2">Add a symbol</span>
              <input
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                placeholder={market?.symbol_hint ?? "AAPL"}
                spellCheck={false}
                className="mono h-11 w-full rounded-xl border border-border-strong bg-surface px-3 text-sm uppercase text-fg placeholder:normal-case placeholder:text-muted-2 focus:border-accent"
              />
            </label>
            <Button type="submit" loading={adding} disabled={adding || !draft.trim() || !market}>
              <IconPlus size={14} />
              Star it
            </Button>
            <p className="text-[11px] leading-relaxed text-muted-2">
              Names outside the analyzed universe are kept and shown to the desk admins as coverage requests.
            </p>
          </form>

          <div className="space-y-4">
            {loading ? (
              <div className="grid gap-2 sm:grid-cols-2">
                {Array.from({ length: 4 }).map((_, i) => (
                  <Skeleton key={i} className="h-16" />
                ))}
              </div>
            ) : watchlist.length === 0 ? (
              <EmptyState
                icon={<IconStarFilled size={20} />}
                title="Nothing starred yet"
                description="Star names from the ranked book or add symbols here."
              />
            ) : (
              <>
                {covered.length ? (
                  <div>
                    <div className="mb-2 text-xs font-medium text-muted">In coverage</div>
                    <ul className="grid gap-2 sm:grid-cols-2">
                      {covered.map((item) => (
                        <WatchRow key={item.ticker} ticker={item.ticker} name={item.name} added={item.added_at} covered onRemove={() => void toggleWatch(item.ticker)} />
                      ))}
                    </ul>
                  </div>
                ) : null}
                {requested.length ? (
                  <div>
                    <div className="mb-2 text-xs font-medium text-muted">Not in coverage · requested</div>
                    <ul className="grid gap-2 sm:grid-cols-2">
                      {requested.map((item) => (
                        <WatchRow key={item.ticker} ticker={item.ticker} name={item.name} added={item.added_at} covered={false} onRemove={() => void toggleWatch(item.ticker)} />
                      ))}
                    </ul>
                  </div>
                ) : null}
              </>
            )}
          </div>
        </div>
      </Card>
    </div>
  );
}

function WatchRow({
  ticker,
  name,
  added,
  covered,
  onRemove,
}: {
  ticker: string;
  name?: string | null;
  added: string;
  covered: boolean;
  onRemove: () => void;
}) {
  return (
    <li className="flex items-center gap-3 rounded-xl border border-border bg-surface px-3 py-2.5">
      <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-warning-soft text-warning">
        <IconStarFilled size={14} />
      </span>
      <span className="min-w-0 flex-1">
        <span className="flex items-center gap-2">
          <span className="mono text-xs font-semibold text-fg">{ticker}</span>
          {covered ? null : <Badge tone="warning" className="text-[10px]">requested</Badge>}
        </span>
        <span className="block truncate text-[11px] text-muted">{name ?? relativeTime(added)}</span>
      </span>
      {covered ? (
        <Link href={ideaHref(ticker)} aria-label={`Open ${ticker}`} className="text-muted hover:text-accent">
          <IconArrowUpRight size={16} />
        </Link>
      ) : null}
      <button onClick={onRemove} aria-label={`Remove ${ticker}`} className="text-muted-2 hover:text-danger">
        <IconX size={16} />
      </button>
    </li>
  );
}
