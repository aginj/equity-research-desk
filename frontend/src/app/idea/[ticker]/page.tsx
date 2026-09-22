"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { ActionPill } from "@/components/ActionPill";
import { IconAlert, IconArrowLeft, IconExternal, IconFile, IconNews, IconStar, IconStarFilled } from "@/components/icons";
import { RatingTimeline } from "@/components/RatingTimeline";
import { ScoreBar } from "@/components/ScoreBar";
import { Sparkline } from "@/components/Sparkline";
import { useWorkspace } from "@/components/WorkspaceProvider";
import { Alert, Badge, Button, Card, CardHeader, EmptyState, Skeleton, cx } from "@/components/ui";
import { api } from "@/lib/api";
import { compactCap, horizonLabel, ideaHref, money, pct, relativeTime, when } from "@/lib/format";
import type { Book, RatingPoint, Recommendation, RiskAppetite, Source, TickerIntel } from "@/lib/types";

const SOURCE_TONE: Record<Source["kind"], "accent" | "success" | "warning" | "neutral"> = {
  news: "accent",
  filing: "success",
  market: "warning",
  internal: "neutral",
};

export default function IdeaPage() {
  const params = useParams<{ ticker: string }>();
  const ticker = (params.ticker || "").toUpperCase();
  const { market, appetite, auth, watched, toggleWatch, loading: workspaceLoading } = useWorkspace();
  const [rec, setRec] = useState<Recommendation | null>(null);
  const [intel, setIntel] = useState<TickerIntel | null>(null);
  const [viewAppetite, setViewAppetite] = useState<RiskAppetite | null>(null);
  const [history, setHistory] = useState<RatingPoint[]>([]);
  const [book, setBook] = useState<Book | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const marketId = market?.id;
  useEffect(() => {
    if (!ticker || workspaceLoading || !marketId) return;
    let cancelled = false;
    setLoading(true);
    api
      .idea(ticker, marketId, appetite)
      .then(async (payload) => {
        if (cancelled) return;
        setRec(payload.recommendation);
        setIntel(payload.intel);
        setViewAppetite(payload.appetite);
        setError(null);
        const [points, nextBook] = await Promise.all([
          api.ideaHistory(ticker, marketId).catch(() => ({ points: [] as RatingPoint[] })),
          api.book(marketId, appetite).catch(() => null),
        ]);
        if (cancelled) return;
        setHistory(points.points);
        setBook(nextBook);
      })
      .catch((err) => !cancelled && setError(err instanceof Error ? err.message : "Not found"))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [ticker, marketId, appetite, workspaceLoading]);

  const signedIn = auth === "authenticated";
  const starred = watched.has(ticker);
  const peers = useMemo(
    () =>
      rec
        ? (book?.run.recommendations ?? []).filter((row) => row.sector === rec.sector && row.ticker !== rec.ticker).slice(0, 8)
        : [],
    [book, rec],
  );

  if (error) {
    return (
      <div className="space-y-6">
        <BackLink />
        <Card>
          <EmptyState
            icon={<IconAlert size={22} />}
            title="No idea on file for this ticker"
            description={error}
            action={
              <Link href="/">
                <Button variant="secondary">Back to desk</Button>
              </Link>
            }
          />
        </Card>
      </div>
    );
  }

  if (loading || workspaceLoading || !rec) {
    return (
      <div className="space-y-6">
        <BackLink />
        <div className="grid gap-4 lg:grid-cols-[1.3fr_0.7fr]">
          <Skeleton className="h-40" />
          <Skeleton className="h-40" />
          <Skeleton className="h-72" />
          <Skeleton className="h-72" />
        </div>
      </div>
    );
  }

  const up = rec.quote.change_pct >= 0;

  return (
    <div className="space-y-6">
      <BackLink />

      {/* Header */}
      <Card className="fade-up overflow-hidden">
        <div className="grid gap-6 p-6 lg:grid-cols-[1fr_auto] lg:items-start">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <span className="mono text-xs font-semibold text-accent">{rec.ticker}</span>
              <Badge tone="neutral">{rec.sector}</Badge>
              <Badge tone="neutral">{horizonLabel(rec.horizon)}</Badge>
              <Badge tone={rec.synthesis_mode === "llm" ? "accent" : "neutral"}>
                {rec.synthesis_mode === "llm" ? "LLM synthesis" : "Heuristic synthesis"}
              </Badge>
              {viewAppetite ? <Badge tone="neutral">Policy · {viewAppetite}</Badge> : null}
              {intel?.next_earnings ? (
                <Badge tone="warning">Earnings {when(intel.next_earnings)}</Badge>
              ) : null}
            </div>
            <div className="mt-3 flex flex-wrap items-center gap-3">
              <h1 className="text-3xl font-semibold tracking-tight text-fg md:text-4xl">{rec.name}</h1>
              {signedIn ? (
                <button
                  onClick={() => void toggleWatch(rec.ticker)}
                  aria-pressed={starred}
                  className={cx(
                    "inline-flex h-9 items-center gap-1.5 rounded-xl border px-3 text-xs font-medium transition",
                    starred
                      ? "border-transparent bg-warning-soft text-warning"
                      : "border-border-strong bg-surface text-fg-2 hover:bg-surface-hover",
                  )}
                >
                  {starred ? <IconStarFilled size={14} /> : <IconStar size={14} />}
                  {starred ? "On your watchlist" : "Watch"}
                </button>
              ) : null}
            </div>
            <div className="mt-4 flex flex-wrap items-center gap-4">
              <ActionPill action={rec.action} size="md" />
              <div className="flex items-center gap-2 text-sm">
                <span className="text-muted">Conviction</span>
                <span className="mono tabular font-semibold text-fg">{Math.round(rec.conviction * 100)}</span>
                <div className="h-1.5 w-24 overflow-hidden rounded-full bg-surface-2">
                  <div className="h-full rounded-full bg-accent" style={{ width: `${rec.conviction * 100}%` }} />
                </div>
              </div>
            </div>
          </div>
          <div className="rounded-2xl border border-border bg-surface-2/60 p-4 lg:min-w-[280px]">
            <div className="flex items-baseline justify-between gap-4">
              <div className="mono tabular text-3xl font-semibold text-fg">{money(rec.quote.price, rec.quote.currency)}</div>
              <div className={cx("mono tabular text-sm font-medium", up ? "text-success" : "text-danger")}>{pct(rec.quote.change_pct)}</div>
            </div>
            <div className="mt-3">
              <Sparkline values={intel?.candle?.closes ?? []} width={248} height={56} strokeWidth={1.8} />
            </div>
            <div className="mt-3 flex items-center justify-between text-[11px] text-muted">
              <span>Cap {compactCap(rec.quote.market_cap, rec.quote.currency)}</span>
              <span>
                {rec.quote.source} · {relativeTime(rec.quote.as_of)}
              </span>
            </div>
          </div>
        </div>
      </Card>

      <section className="fade-up grid gap-4 lg:grid-cols-[1.3fr_0.7fr]">
        <div className="space-y-4">
          <Card className="p-6">
            <div className="eyebrow">Thesis</div>
            <p className="mt-3 text-lg leading-relaxed text-fg">{rec.thesis}</p>
          </Card>

          <div className="grid gap-4 md:grid-cols-2">
            <Card className="border-l-2 border-l-success p-5">
              <div className="text-xs font-semibold uppercase tracking-wider text-success">Bull case</div>
              <p className="mt-2 text-sm leading-relaxed text-fg-2">{rec.bull_case}</p>
            </Card>
            <Card className="border-l-2 border-l-danger p-5">
              <div className="text-xs font-semibold uppercase tracking-wider text-danger">Bear case</div>
              <p className="mt-2 text-sm leading-relaxed text-fg-2">{rec.bear_case}</p>
            </Card>
          </div>

          <Card className="border-l-2 border-l-accent p-5">
            <div className="text-xs font-semibold uppercase tracking-wider text-accent">Invalidation</div>
            <p className="mt-2 text-sm leading-relaxed text-fg">{rec.invalidation}</p>
          </Card>

          {rec.policy_notes.length ? (
            <Alert tone="neutral" title="Policy notes">
              <ul className="mt-1 space-y-1">
                {rec.policy_notes.map((note) => (
                  <li key={note}>— {note}</li>
                ))}
              </ul>
            </Alert>
          ) : null}
        </div>

        <aside className="space-y-4">
          <Card>
            <CardHeader title="Scorecard" description="0–100; risk is better when low" />
            <div className="space-y-3.5 px-5 py-4">
              <ScoreBar label="News materiality" value={rec.scores.news_materiality} />
              <ScoreBar label="Quality" value={rec.scores.fundamental_quality} />
              <ScoreBar label="Valuation" value={rec.scores.valuation_attractiveness} />
              <ScoreBar label="Momentum" value={rec.scores.momentum} />
              <ScoreBar label="Source quality" value={rec.scores.source_quality} />
              <ScoreBar label="Risk" value={rec.scores.risk} invert />
              <div className="border-t border-border pt-3.5">
                <ScoreBar label="Composite" value={rec.scores.composite} />
              </div>
            </div>
          </Card>

          <Card>
            <CardHeader title="Catalysts" />
            <ul className="space-y-2.5 px-5 py-4 text-sm text-fg-2">
              {rec.catalysts.length ? (
                rec.catalysts.map((item) => (
                  <li key={item} className="flex gap-2.5">
                    <span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-success" />
                    <span className="leading-relaxed">{item}</span>
                  </li>
                ))
              ) : (
                <li className="text-muted">No dated catalysts in the window.</li>
              )}
            </ul>
            <CardHeader title="Risks" className="border-t" />
            <ul className="space-y-2.5 px-5 py-4 text-sm text-fg-2">
              {rec.risks.map((item) => (
                <li key={item} className="flex gap-2.5">
                  <span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-danger" />
                  <span className="leading-relaxed">{item}</span>
                </li>
              ))}
            </ul>
          </Card>
        </aside>
      </section>

      {/* Sources */}
      <Card className="fade-up">
        <CardHeader title="Cited sources" description={`${rec.sources.length} references behind this rating`} />
        <ul className="divide-y divide-border">
          {rec.sources.map((source) => (
            <li key={source.id}>
              <a
                href={source.url}
                target="_blank"
                rel="noreferrer"
                className="row-hover group flex items-start justify-between gap-4 px-5 py-3.5"
              >
                <div className="min-w-0">
                  <div className="text-sm font-medium text-fg group-hover:text-accent">{source.title}</div>
                  <div className="mt-1 flex flex-wrap items-center gap-2 text-[11px] text-muted">
                    <Badge tone={SOURCE_TONE[source.kind]} className="px-2 py-0 text-[10px] uppercase">
                      {source.kind}
                    </Badge>
                    <span>{source.publisher}</span>
                    <span>·</span>
                    <span>{when(source.published_at)}</span>
                  </div>
                </div>
                <IconExternal size={14} className="mt-1 shrink-0 text-muted-2 group-hover:text-accent" />
              </a>
            </li>
          ))}
        </ul>
      </Card>

      {intel ? (
        <section className="fade-up grid gap-4 lg:grid-cols-2">
          <Card>
            <CardHeader title="News on this name" description={`${intel.news.length} headlines`} />
            {intel.news.length ? (
              <ul className="divide-y divide-border">
                {intel.news.map((item) => (
                  <li key={item.id}>
                    <a href={item.url} target="_blank" rel="noreferrer" className="row-hover group block px-5 py-3.5">
                      <div className="text-sm font-medium leading-snug text-fg group-hover:text-accent">{item.headline}</div>
                      <div className="mt-1 text-[11px] text-muted">
                        {item.publisher} · {relativeTime(item.published_at)}
                      </div>
                    </a>
                  </li>
                ))}
              </ul>
            ) : (
              <EmptyState icon={<IconNews size={20} />} title="No headlines" description="Nothing in the lookback window." />
            )}
          </Card>
          <Card>
            <CardHeader title="Filings" description={`${intel.filings.length} recent forms`} />
            {intel.filings.length ? (
              <ul className="divide-y divide-border">
                {intel.filings.map((item) => (
                  <li key={item.id}>
                    <a href={item.url} target="_blank" rel="noreferrer" className="row-hover group flex items-start gap-3 px-5 py-3.5">
                      <span className="mono mt-0.5 shrink-0 rounded-md bg-surface-2 px-1.5 py-0.5 text-[10px] font-semibold text-fg-2">
                        {item.form}
                      </span>
                      <span className="min-w-0">
                        <span className="block text-sm font-medium leading-snug text-fg group-hover:text-accent">{item.description}</span>
                        <span className="mt-1 block text-[11px] text-muted">{when(item.filed_at)}</span>
                      </span>
                    </a>
                  </li>
                ))}
              </ul>
            ) : (
              <EmptyState icon={<IconFile size={20} />} title="No filings" description="No regulator feed for this venue in this build." />
            )}
          </Card>
        </section>
      ) : null}

      <section className="fade-up grid gap-4 lg:grid-cols-[1.1fr_0.9fr]">
        <RatingTimeline points={history} />
        <Card>
          <CardHeader title="Peers in this book" description={rec.sector} />
          {peers.length ? (
            <div className="overflow-x-auto">
              <table className="min-w-full text-left text-sm">
                <thead>
                  <tr className="border-b border-border text-[11px] uppercase tracking-wider text-muted">
                    <th className="px-5 py-2 font-medium">Name</th>
                    <th className="px-3 py-2 font-medium">Rating</th>
                    <th className="px-3 py-2 font-medium">Conviction</th>
                    <th className="px-3 py-2 font-medium">Composite</th>
                    <th className="px-5 py-2 font-medium">Valuation</th>
                  </tr>
                </thead>
                <tbody>
                  {peers.map((row) => (
                    <tr key={row.ticker} className="border-b border-border last:border-0">
                      <td className="px-5 py-2.5">
                        <Link href={ideaHref(row.ticker)} className="mono text-xs font-semibold text-accent hover:underline">
                          {row.ticker}
                        </Link>
                        <div className="truncate text-[11px] text-muted">{row.name}</div>
                      </td>
                      <td className="px-3 py-2.5">
                        <ActionPill action={row.action} />
                      </td>
                      <td className="mono tabular px-3 py-2.5 text-xs">{Math.round(row.conviction * 100)}</td>
                      <td className="mono tabular px-3 py-2.5 text-xs">{Math.round(row.scores.composite * 100)}</td>
                      <td className="mono tabular px-5 py-2.5 text-xs">{Math.round(row.scores.valuation_attractiveness * 100)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <EmptyState title="No same-sector peers" description="This run has no other names in the sector." />
          )}
        </Card>
      </section>
    </div>
  );
}

function BackLink() {
  return (
    <Link href="/" className="inline-flex items-center gap-1.5 text-xs font-medium text-muted transition hover:text-accent">
      <IconArrowLeft size={14} /> Back to book
    </Link>
  );
}
