"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";

import { ActionPill } from "@/components/ActionPill";
import {
  IconAlert,
  IconArrowUpRight,
  IconFile,
  IconLock,
  IconNews,
  IconPlay,
  IconSpark,
  IconStar,
  IconStarFilled,
  IconTrendUp,
} from "@/components/icons";
import { RunProgress } from "@/components/RunProgress";
import { ScoreBar } from "@/components/ScoreBar";
import { Sparkline } from "@/components/Sparkline";
import { TrackRecordCard } from "@/components/RatingTimeline";
import { TopIdeas } from "@/components/TopIdeas";
import { WhatChanged } from "@/components/WhatChanged";
import { useWorkspace } from "@/components/WorkspaceProvider";
import { Alert, Badge, Button, Card, CardHeader, EmptyState, Skeleton, Stat, cx } from "@/components/ui";
import { api, isTerminal, subscribeRun, waitForRun } from "@/lib/api";
import { compactCap, horizonLabel, ideaHref, money, pct, relativeTime } from "@/lib/format";
import type { AnalysisResult, Book, BookChanges, Health, RunEvent, TrackRecord } from "@/lib/types";

const STREAM_TIMEOUT_MS = 120_000;

export function DeskBoard() {
  const [book, setBook] = useState<Book | null>(null);
  const [health, setHealth] = useState<Health | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [live, setLive] = useState<RunEvent | null>(null);
  const [watchOnly, setWatchOnly] = useState(false);
  const [query, setQuery] = useState("");
  const [ratingFilter, setRatingFilter] = useState<string>("all");
  const [sectorFilter, setSectorFilter] = useState<string>("all");
  const [sortBy, setSortBy] = useState<"rank" | "conviction" | "name" | "change">("rank");
  const [openNotes, setOpenNotes] = useState<string | null>(null);
  const [changes, setChanges] = useState<BookChanges | null>(null);
  const [record, setRecord] = useState<TrackRecord | null>(null);
  const { market, appetite, auth, isAdmin, watched, toggleWatch, loading: workspaceLoading } = useWorkspace();
  const mounted = useRef(true);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  // Middleware bounces non-admins off /admin with ?denied=admin.
  useEffect(() => {
    if (typeof window === "undefined") return;
    const params = new URLSearchParams(window.location.search);
    if (params.get("denied") === "admin") {
      setNotice("That page is for desk administrators. Your account can use the workspace and read everything else.");
      window.history.replaceState(null, "", window.location.pathname);
    }
  }, []);

  const marketId = market?.id;
  const refresh = useCallback(async () => {
    if (!marketId) return;
    try {
      const [next, status, delta, track] = await Promise.all([
        api.book(marketId, appetite),
        api.health(),
        api.bookChanges(marketId, appetite).catch(() => null),
        api.trackRecord(marketId).catch(() => null),
      ]);
      if (!mounted.current) return;
      setBook(next);
      setHealth(status);
      setChanges(delta);
      setRecord(track);
      setError(null);
    } catch (err) {
      if (!mounted.current) return;
      setError(err instanceof Error ? err.message : "Unable to reach the research API.");
    } finally {
      if (mounted.current) setLoading(false);
    }
  }, [marketId, appetite]);

  useEffect(() => {
    if (workspaceLoading || !marketId) return;
    setLoading(true);
    void refresh();
  }, [refresh, workspaceLoading, marketId]);

  const run: AnalysisResult | null = book?.run ?? null;
  const setRun = useCallback(
    (next: AnalysisResult) => {
      setBook((current) => ({
        run: next,
        appetite: current?.appetite ?? next.summary?.risk_appetite ?? "balanced",
        repoliced: false,
      }));
    },
    [],
  );

  // If the page loads while a run is already executing (another tab, the scheduler), attach to it.
  const followed = useRef<Set<string>>(new Set());
  const activeRunId = health?.active_run_id ?? null;
  useEffect(() => {
    if (!activeRunId || busy || followed.current.has(activeRunId)) return;
    void followRun(activeRunId, true);
  });

  async function followRun(runId: string, attached: boolean) {
    followed.current.add(runId);
    setBusy(true);
    setError(null);
    setLive({
      run_id: runId,
      stage: "queued",
      message: attached ? "Attached to the run already in progress…" : "Opening the desk…",
      at: new Date().toISOString(),
      progress: 0.02,
    });
    try {
      await new Promise<void>((resolve) => {
        const stop = subscribeRun(
          runId,
          (event) => {
            if (mounted.current) setLive(event);
          },
          resolve,
        );
        setTimeout(() => {
          stop();
          resolve();
        }, STREAM_TIMEOUT_MS);
      });
      const final = await waitForRun(runId);
      if (!mounted.current) return;
      if (final.status === "failed") {
        setError(final.error ? `Run failed: ${final.error}` : "Run failed.");
      } else if (isTerminal(final.status) && final.recommendations.length && final.market_id === marketId) {
        setRun(final);
      }
    } catch (err) {
      if (mounted.current) setError(err instanceof Error ? err.message : "Run failed");
    } finally {
      if (mounted.current) {
        setBusy(false);
        setLive(null);
        void refresh();
      }
    }
  }

  async function runDesk() {
    setBusy(true);
    setError(null);
    try {
      const { run: started, attached } = await api.startRun({ market_id: marketId });
      await followRun(started.run_id, attached);
    } catch (err) {
      if (mounted.current) {
        setError(err instanceof Error ? err.message : "Run failed");
        setBusy(false);
      }
    }
  }

  const allRecs = run?.recommendations ?? [];
  const signedIn = auth === "authenticated";
  const filterActive = signedIn && watchOnly && watched.size > 0;
  const sectors = useMemo(
    () => Array.from(new Set(allRecs.map((row) => row.sector).filter(Boolean))).sort(),
    [allRecs],
  );
  const recs = useMemo(() => {
    const needle = query.trim().toLowerCase();
    let rows = filterActive ? allRecs.filter((row) => watched.has(row.ticker)) : allRecs;
    if (ratingFilter !== "all") rows = rows.filter((row) => row.action === ratingFilter);
    if (sectorFilter !== "all") rows = rows.filter((row) => row.sector === sectorFilter);
    if (needle) {
      rows = rows.filter(
        (row) =>
          row.ticker.toLowerCase().includes(needle) ||
          row.name.toLowerCase().includes(needle) ||
          row.sector.toLowerCase().includes(needle),
      );
    }
    const sorted = [...rows];
    if (sortBy === "conviction") sorted.sort((a, b) => b.conviction - a.conviction);
    else if (sortBy === "name") sorted.sort((a, b) => a.ticker.localeCompare(b.ticker));
    else if (sortBy === "change") sorted.sort((a, b) => b.quote.change_pct - a.quote.change_pct);
    return sorted;
  }, [allRecs, filterActive, watched, ratingFilter, sectorFilter, query, sortBy]);
  const filtersOn = ratingFilter !== "all" || sectorFilter !== "all" || query.trim().length > 0;
  const accumulate = useMemo(() => allRecs.filter((r) => r.action === "accumulate"), [allRecs]);
  const leaders = useMemo(() => allRecs.slice(0, 3), [allRecs]);
  const intelByTicker = useMemo(() => new Map((run?.intel ?? []).map((i) => [i.ticker, i])), [run]);
  const viewAppetite = book?.appetite ?? run?.summary?.risk_appetite ?? health?.risk_appetite ?? "balanced";
  const isLoading = loading || workspaceLoading;

  return (
    <div className="space-y-6">
      {/* Hero */}
      <section className="fade-up flex flex-col justify-between gap-6 lg:flex-row lg:items-end">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <span className="eyebrow">Morning book{market ? ` · ${market.exchange_code}` : ""}</span>
            {run ? (
              <Badge tone="neutral" className="mono">
                {run.run_id} · {relativeTime(run.finished_at ?? run.started_at)}
              </Badge>
            ) : null}
            {book?.repoliced ? (
              <Badge tone="accent" dot>
                Re-ranked for your appetite
              </Badge>
            ) : null}
          </div>
          {isLoading ? (
            <div className="mt-3 space-y-3">
              <Skeleton className="h-10 w-3/4 max-w-2xl" />
              <Skeleton className="h-4 w-1/2 max-w-md" />
            </div>
          ) : (
            <>
              <h1 className="gradient-text mt-3 max-w-3xl text-3xl font-semibold leading-[1.1] tracking-tight md:text-[2.6rem]">
                {run?.summary?.headline ?? "Run the desk to rank the universe with sourced research."}
              </h1>
              <p className="mt-3 max-w-2xl text-sm leading-relaxed text-muted">
                {run?.summary?.regime ??
                  (market
                    ? `Agents collect licensed news and ${market.filings_label} for ${market.label}, then policy caps risk.`
                    : "Agents collect licensed news, filings, and prices, then a policy layer caps risk. Nothing here is a buy order.")}
              </p>
            </>
          )}
        </div>
        <div className="flex flex-col items-start gap-3 lg:items-end">
          {isAdmin ? (
            <Button size="lg" onClick={() => void runDesk()} loading={busy} disabled={busy} data-testid="run-desk">
              {!busy ? <IconPlay size={14} /> : null}
              {busy ? "Running desk…" : "Run desk"}
            </Button>
          ) : busy ? (
            <Badge tone="accent" dot pulse className="h-9 px-3 text-xs">
              Desk run in progress
            </Badge>
          ) : signedIn || health?.auth === false ? (
            <Link
              href="/workspace"
              className="inline-flex h-11 items-center gap-2 rounded-xl border border-border-strong bg-surface px-5 text-sm font-medium text-fg transition hover:bg-surface-hover"
            >
              Tune your view
            </Link>
          ) : (
            <Link
              href="/signin"
              className="inline-flex h-11 items-center gap-2 rounded-xl bg-accent px-5 text-sm font-medium text-accent-fg shadow-[var(--shadow-glow)] transition hover:brightness-110"
            >
              Sign in for a personal view
            </Link>
          )}
          <div className="flex flex-wrap items-center gap-1.5">
            <Badge tone={health?.llm ? "accent" : "neutral"} dot>
              {health?.llm ? "LLM synthesis" : "Heuristic synthesis"}
            </Badge>
            <Badge tone={health?.live_market && !health.force_demo ? "success" : "warning"} dot>
              {health?.live_market && !health.force_demo ? "Live feeds" : "Demo feeds"}
            </Badge>
            <Badge tone="neutral">Appetite · {viewAppetite}</Badge>
          </div>
        </div>
      </section>

      {live ? <RunProgress event={live} /> : null}

      {notice ? (
        <Alert tone="warning" icon={<IconLock size={16} />}>
          {notice}
        </Alert>
      ) : null}

      {error ? (
        <Alert tone="danger" icon={<IconAlert size={16} />} title="Something needs attention">
          {error}
        </Alert>
      ) : null}

      {/* KPIs */}
      <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Stat
          label="Names analyzed"
          value={run?.summary?.tickers_analyzed ?? "—"}
          icon={<IconSpark size={18} />}
          tone="accent"
          loading={isLoading}
          hint={run?.summary?.market_label}
        />
        <Stat
          label="Headlines"
          value={run?.summary?.news_items ?? "—"}
          icon={<IconNews size={18} />}
          loading={isLoading}
          hint="In the lookback window"
        />
        <Stat
          label="Filings"
          value={run?.summary?.filings ?? "—"}
          icon={<IconFile size={18} />}
          loading={isLoading}
          hint={market?.filings_label}
        />
        <Stat
          label="Accumulate"
          value={run ? accumulate.length : "—"}
          icon={<IconTrendUp size={18} />}
          tone="success"
          loading={isLoading}
          hint="Cleared desk policy"
        />
      </section>

      {run ? <TopIdeas rows={accumulate.slice(0, 6)} /> : null}

      <div className="grid gap-4 lg:grid-cols-[1.4fr_0.6fr]">
        <WhatChanged changes={changes} />
        <TrackRecordCard record={record} />
      </div>

      {/* Ranked book */}
      <Card className="fade-up overflow-hidden">
        <CardHeader
          title="Ranked book"
          description={
            run
              ? `${recs.length}${filterActive ? ` of ${allRecs.length}` : ""} names · policy applied under ${viewAppetite} appetite`
              : "No run yet"
          }
          action={
            <div className="flex items-center gap-3">
              {run ? (
                <Link href="/research" className="inline-flex items-center gap-1 text-xs font-medium text-accent hover:underline underline-offset-4">
                  Open tape <IconArrowUpRight size={14} />
                </Link>
              ) : null}
            </div>
          }
        />
        {allRecs.length > 0 ? (
          <div className="flex flex-col gap-3 border-b border-border px-5 py-3">
            <div className="flex flex-wrap items-center gap-2">
              <input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Search ticker, name, sector"
                aria-label="Search the book"
                className="h-8 w-full max-w-xs rounded-lg border border-border-strong bg-surface px-3 text-xs text-fg placeholder:text-muted-2 focus:border-accent md:w-56"
              />
              <select
                value={sortBy}
                onChange={(e) => setSortBy(e.target.value as typeof sortBy)}
                aria-label="Sort the book"
                className="h-8 rounded-lg border border-border-strong bg-surface px-2 text-xs text-fg"
              >
                <option value="rank">Sort · rank</option>
                <option value="conviction">Sort · conviction</option>
                <option value="change">Sort · 30d</option>
                <option value="name">Sort · name</option>
              </select>
              {signedIn && watched.size > 0 ? (
                <Chip active={watchOnly} onClick={() => setWatchOnly((v) => !v)}>
                  {watchOnly ? <IconStarFilled size={12} /> : <IconStar size={12} />}
                  Watchlist only
                </Chip>
              ) : null}
            </div>
            <div className="flex flex-wrap items-center gap-1.5">
              {(["all", "accumulate", "watch", "reduce", "avoid"] as const).map((rating) => (
                <Chip key={rating} active={ratingFilter === rating} onClick={() => setRatingFilter(rating)}>
                  {rating === "all" ? "All ratings" : rating}
                </Chip>
              ))}
              {sectors.map((sector) => (
                <Chip
                  key={sector}
                  active={sectorFilter === sector}
                  onClick={() => setSectorFilter((current) => (current === sector ? "all" : sector))}
                >
                  {sector}
                </Chip>
              ))}
            </div>
          </div>
        ) : null}
        <div className="overflow-x-auto">
          {isLoading ? (
            <TableSkeleton />
          ) : allRecs.length === 0 ? (
            <EmptyState
              icon={<IconSpark size={22} />}
              title="The book is empty"
              description={
                isAdmin
                  ? "Run the desk to build a ranked list of sourced ideas for this venue."
                  : "No desk run has completed for this venue yet. Check back after the next scheduled run."
              }
              action={
                isAdmin ? (
                  <Button onClick={() => void runDesk()} loading={busy} disabled={busy}>
                    {!busy ? <IconPlay size={14} /> : null}
                    Run desk
                  </Button>
                ) : null
              }
            />
          ) : recs.length === 0 ? (
            <EmptyState
              icon={<IconStar size={22} />}
              title={filtersOn ? "No names match these filters" : "None of your watchlist is in this book"}
              description={
                filtersOn
                  ? "Clear search, rating, or sector chips to see the rest of the book."
                  : "Starred names that are not in the analyzed universe show up as coverage requests for the desk admins."
              }
              action={
                <Button
                  variant="secondary"
                  onClick={() => {
                    setWatchOnly(false);
                    setQuery("");
                    setRatingFilter("all");
                    setSectorFilter("all");
                  }}
                >
                  Show the whole book
                </Button>
              }
            />
          ) : (
            <>
              <ul className="divide-y divide-border md:hidden">
                {recs.map((row, index) => {
                  const intel = intelByTicker.get(row.ticker);
                  const up = row.quote.change_pct >= 0;
                  const starred = watched.has(row.ticker);
                  const notesOpen = openNotes === row.ticker;
                  return (
                    <li key={row.ticker} className="px-4 py-4">
                      <div className="flex items-start justify-between gap-3">
                        <Link href={ideaHref(row.ticker)} className="min-w-0">
                          <span className="mono text-[11px] text-muted">{index + 1}</span>
                          <span className="mono ml-2 text-sm font-semibold text-fg">{row.ticker}</span>
                          <div className="truncate text-xs text-muted">{row.name}</div>
                        </Link>
                        <ActionPill action={row.action} />
                      </div>
                      <div className="mt-2 flex items-center justify-between gap-3 text-xs">
                        <span className="mono tabular font-medium">{money(row.quote.price, row.quote.currency)}</span>
                        <span className={cx("mono tabular", up ? "text-success" : "text-danger")}>{pct(row.quote.change_pct)}</span>
                        <span className="text-muted">{horizonLabel(row.horizon)}</span>
                      </div>
                      <p className="mt-2 line-clamp-2 text-[13px] leading-relaxed text-fg-2">{row.thesis}</p>
                      <div className="mt-2 flex items-center justify-between">
                        <Sparkline values={intel?.candle?.closes ?? []} />
                        {signedIn ? (
                          <button
                            type="button"
                            onClick={() => void toggleWatch(row.ticker)}
                            aria-pressed={starred}
                            aria-label={starred ? `Remove ${row.ticker} from watchlist` : `Add ${row.ticker} to watchlist`}
                            className={cx("flex h-8 w-8 items-center justify-center rounded-lg", starred ? "text-warning" : "text-muted")}
                          >
                            {starred ? <IconStarFilled size={15} /> : <IconStar size={15} />}
                          </button>
                        ) : null}
                      </div>
                      {row.policy_notes.length ? (
                        <button
                          type="button"
                          className="mt-2 text-[11px] text-accent"
                          aria-expanded={notesOpen}
                          onClick={() => setOpenNotes(notesOpen ? null : row.ticker)}
                        >
                          {notesOpen ? "Hide policy notes" : `${row.policy_notes.length} policy note${row.policy_notes.length === 1 ? "" : "s"}`}
                        </button>
                      ) : null}
                      {notesOpen ? (
                        <ul className="mt-1 space-y-1 text-[11px] text-muted">
                          {row.policy_notes.map((note) => (
                            <li key={note}>— {note}</li>
                          ))}
                        </ul>
                      ) : null}
                    </li>
                  );
                })}
              </ul>
              <table className="hidden min-w-full text-left text-sm md:table">
                <thead>
                  <tr className="border-b border-border text-[11px] uppercase tracking-wider text-muted">
                    {signedIn ? <th className="w-10 px-3 py-3" aria-label="Watch" /> : null}
                    <th className="px-5 py-3 font-medium">Name</th>
                    <th className="px-3 py-3 font-medium">Rating</th>
                    <th className="px-3 py-3 font-medium">Last</th>
                    <th className="px-3 py-3 font-medium">30d</th>
                    <th className="px-3 py-3 font-medium">Conviction</th>
                    <th className="px-3 py-3 font-medium">Horizon</th>
                    <th className="px-5 py-3 font-medium">Thesis</th>
                  </tr>
                </thead>
                <tbody>
                  {recs.map((row, index) => {
                    const intel = intelByTicker.get(row.ticker);
                    const up = row.quote.change_pct >= 0;
                    const starred = watched.has(row.ticker);
                    const notesOpen = openNotes === row.ticker;
                    return (
                      <tr key={row.ticker} className="row-hover border-b border-border last:border-0">
                        {signedIn ? (
                          <td className="px-3 py-3.5">
                            <button
                              type="button"
                              onClick={() => void toggleWatch(row.ticker)}
                              aria-pressed={starred}
                              aria-label={starred ? `Remove ${row.ticker} from watchlist` : `Add ${row.ticker} to watchlist`}
                              className={cx(
                                "flex h-7 w-7 items-center justify-center rounded-lg transition",
                                starred ? "text-warning hover:bg-warning-soft" : "text-muted-2 hover:bg-surface-2 hover:text-fg-2",
                              )}
                            >
                              {starred ? <IconStarFilled size={15} /> : <IconStar size={15} />}
                            </button>
                          </td>
                        ) : null}
                        <td className="px-5 py-3.5">
                          <Link href={ideaHref(row.ticker)} className="group flex items-center gap-3">
                            <span className="mono tabular flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-surface-2 text-[11px] text-muted">
                              {index + 1}
                            </span>
                            <span className="min-w-0">
                              <span className="mono block text-[13px] font-semibold text-fg group-hover:text-accent">
                                {row.ticker}
                              </span>
                              <span className="block truncate text-xs text-muted">{row.name}</span>
                              <span className="block truncate text-[11px] text-muted-2">{row.sector}</span>
                            </span>
                          </Link>
                        </td>
                        <td className="px-3 py-3.5">
                          <ActionPill action={row.action} />
                        </td>
                        <td className="px-3 py-3.5">
                          <div className="mono tabular text-[13px] font-medium text-fg">{money(row.quote.price, row.quote.currency)}</div>
                          <div className={cx("mono tabular text-xs", up ? "text-success" : "text-danger")}>{pct(row.quote.change_pct)}</div>
                          <div className="text-[11px] text-muted-2">{compactCap(row.quote.market_cap, row.quote.currency)}</div>
                        </td>
                        <td className="px-3 py-3.5">
                          <Sparkline values={intel?.candle?.closes ?? []} />
                        </td>
                        <td className="px-3 py-3.5">
                          <Conviction value={row.conviction} />
                        </td>
                        <td className="px-3 py-3.5 text-xs text-muted">{horizonLabel(row.horizon)}</td>
                        <td className="max-w-md px-5 py-3.5 text-[13px] leading-relaxed text-fg-2">
                          <span className="line-clamp-2">{row.thesis}</span>
                          {row.policy_notes.length ? (
                            <button
                              type="button"
                              className="mt-1 block text-[11px] text-accent hover:underline"
                              aria-expanded={notesOpen}
                              onClick={() => setOpenNotes(notesOpen ? null : row.ticker)}
                            >
                              {notesOpen ? "Hide policy notes" : `${row.policy_notes.length} policy note${row.policy_notes.length === 1 ? "" : "s"}`}
                            </button>
                          ) : null}
                          {notesOpen ? (
                            <ul className="mt-1 space-y-0.5 text-[11px] text-muted">
                              {row.policy_notes.map((note) => (
                                <li key={note}>— {note}</li>
                              ))}
                            </ul>
                          ) : null}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </>
          )}
        </div>
      </Card>

      {/* Desk note + leaders */}
      {run?.summary ? (
        <section className="fade-up grid gap-4 lg:grid-cols-[1.25fr_0.75fr]">
          <Card>
            <CardHeader title="Desk note" description="What the chief analyst and policy layer concluded" />
            <div className="px-5 py-4">
              <p className="text-sm leading-relaxed text-fg-2">{run.summary.body}</p>
              <ul className="mt-4 space-y-2">
                {run.summary.caveats.map((caveat) => (
                  <li key={caveat} className="flex gap-2 text-xs leading-relaxed text-muted">
                    <span className="mt-[7px] h-1 w-1 shrink-0 rounded-full bg-muted-2" />
                    {caveat}
                  </li>
                ))}
              </ul>
            </div>
          </Card>
          <Card>
            <CardHeader title="Lead scorecards" description="Top three names after policy" />
            <div className="divide-y divide-border">
              {leaders.map((row) => (
                <Link key={row.ticker} href={ideaHref(row.ticker)} className="row-hover block px-5 py-4">
                  <div className="mb-3 flex items-center justify-between">
                    <div className="min-w-0">
                      <span className="mono text-[13px] font-semibold text-fg">{row.ticker}</span>
                      <span className="ml-2 truncate text-xs text-muted">{row.name}</span>
                    </div>
                    <ActionPill action={row.action} />
                  </div>
                  <div className="grid gap-2.5">
                    <ScoreBar label="Quality" value={row.scores.fundamental_quality} compact />
                    <ScoreBar label="Valuation" value={row.scores.valuation_attractiveness} compact />
                    <ScoreBar label="Risk" value={row.scores.risk} invert compact />
                  </div>
                </Link>
              ))}
            </div>
          </Card>
        </section>
      ) : null}
    </div>
  );
}

function Conviction({ value }: { value: number }) {
  const percent = Math.round(value * 100);
  const size = 36;
  const stroke = 3.5;
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  const color = value >= 0.7 ? "var(--success)" : value >= 0.5 ? "var(--accent)" : "var(--warning)";
  return (
    <div className="flex items-center gap-2.5">
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} aria-hidden="true" className="-rotate-90">
        <circle cx={size / 2} cy={size / 2} r={r} stroke="var(--surface-2)" strokeWidth={stroke} fill="none" />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          stroke={color}
          strokeWidth={stroke}
          fill="none"
          strokeLinecap="round"
          strokeDasharray={c}
          strokeDashoffset={c * (1 - value)}
          className="transition-[stroke-dashoffset] duration-700 ease-out"
        />
      </svg>
      <span className="mono tabular text-[13px] font-medium text-fg">{percent}</span>
    </div>
  );
}

function TableSkeleton() {
  return (
    <div className="divide-y divide-border">
      {Array.from({ length: 6 }).map((_, i) => (
        <div key={i} className="flex items-center gap-4 px-5 py-4">
          <Skeleton className="h-8 w-8 rounded-lg" />
          <div className="flex-1 space-y-2">
            <Skeleton className="h-3.5 w-24" />
            <Skeleton className="h-3 w-40" />
          </div>
          <Skeleton className="h-5 w-20 rounded-full" />
          <Skeleton className="hidden h-8 w-24 md:block" />
          <Skeleton className="hidden h-3 w-1/3 lg:block" />
        </div>
      ))}
    </div>
  );
}

function Chip({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: ReactNode;
}) {
  return (
    <button
      type="button"
      aria-pressed={active}
      onClick={onClick}
      className={cx(
        "inline-flex h-7 items-center gap-1.5 rounded-full border px-2.5 text-[11px] font-medium capitalize transition",
        active
          ? "border-transparent bg-accent-soft text-accent"
          : "border-border bg-surface text-fg-2 hover:bg-surface-hover",
      )}
    >
      {children}
    </button>
  );
}
