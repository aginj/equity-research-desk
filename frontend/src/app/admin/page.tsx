"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";

import { AppetiteCards } from "@/components/AppetiteCards";
import { IconAlert, IconCheck, IconGlobe, IconPlay, IconShield, IconStar } from "@/components/icons";
import { useWorkspace } from "@/components/WorkspaceProvider";
import { Alert, Badge, Button, Card, CardHeader, EmptyState, PageHeader, Skeleton, cx } from "@/components/ui";
import { ApiError, api } from "@/lib/api";
import type { CoverageRequest, Market, RiskAppetite, UniverseTicker } from "@/lib/types";

/**
 * Desk administration. The venue selected in the sidebar is the one being edited; the
 * "desk default" controls what anonymous visitors see first and what the scheduler runs.
 */
export default function AdminPage() {
  const { auth, isAdmin, market, catalog, loading: workspaceLoading } = useWorkspace();
  const [rows, setRows] = useState<UniverseTicker[]>([]);
  const [draft, setDraft] = useState("");
  const [defaultAppetite, setDefaultAppetite] = useState<RiskAppetite | null>(null);
  const [defaultMarket, setDefaultMarket] = useState<Market | null>(null);
  const [requests, setRequests] = useState<CoverageRequest[] | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [running, setRunning] = useState(false);

  const marketId = market?.id;

  const load = useCallback(async () => {
    if (!marketId) return;
    setLoading(true);
    try {
      const [universe, appetite, defaults, coverage] = await Promise.all([
        api.universe(marketId),
        api.appetite(),
        api.markets(),
        api.coverageRequests(),
      ]);
      setRows(universe);
      setDraft(universe.map((row) => row.ticker).join(", "));
      setDefaultAppetite(appetite.risk_appetite);
      setDefaultMarket(defaults.active);
      setRequests(coverage.requests);
      setError(null);
    } catch (err) {
      setError(err instanceof ApiError && err.status === 403 ? "Your account is not a desk administrator." : err instanceof Error ? err.message : "Load failed");
    } finally {
      setLoading(false);
    }
  }, [marketId]);

  useEffect(() => {
    if (workspaceLoading || !isAdmin) return;
    void load();
  }, [load, workspaceLoading, isAdmin]);

  const draftTickers = useMemo(
    () =>
      Array.from(
        new Set(
          draft
            .split(/[\s,]+/)
            .map((item) => item.trim().toUpperCase())
            .filter(Boolean),
        ),
      ),
    [draft],
  );
  const dirty = useMemo(() => draftTickers.join(",") !== rows.map((r) => r.ticker).join(","), [draftTickers, rows]);
  const requestsHere = useMemo(() => (requests ?? []).filter((r) => r.market_id === marketId), [requests, marketId]);

  async function saveUniverse() {
    setError(null);
    setMessage(null);
    setSaving(true);
    try {
      const next = await api.replaceUniverse(draftTickers, marketId);
      setRows(next);
      setDraft(next.map((row) => row.ticker).join(", "));
      setMessage(`Universe saved · ${next.length} names`);
      const coverage = await api.coverageRequests();
      setRequests(coverage.requests);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Save failed");
    } finally {
      setSaving(false);
    }
  }

  async function saveDefaultAppetite(next: RiskAppetite) {
    const previous = defaultAppetite;
    setError(null);
    setDefaultAppetite(next);
    try {
      await api.setAppetite(next);
      setMessage(`Desk default appetite set to ${next}`);
    } catch (err) {
      setDefaultAppetite(previous);
      setError(err instanceof Error ? err.message : "Could not save appetite");
    }
  }

  async function makeDefaultMarket() {
    if (!marketId) return;
    setError(null);
    try {
      const result = await api.setMarket(marketId);
      setDefaultMarket(result.market);
      setMessage(`${result.market.label} is now the desk default`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not update default venue");
    }
  }

  async function runNow() {
    setRunning(true);
    setError(null);
    try {
      const { run, attached } = await api.startRun({ market_id: marketId });
      setMessage(attached ? `Attached to run ${run.run_id} already in progress.` : `Run ${run.run_id} started — follow it on the desk.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not start run");
    } finally {
      setRunning(false);
    }
  }

  function addRequested(ticker: string) {
    if (draftTickers.includes(ticker)) return;
    setDraft((current) => (current.trim() ? `${current.trim().replace(/,\s*$/, "")}, ${ticker}` : ticker));
  }

  if (!workspaceLoading && auth === "authenticated" && !isAdmin) {
    return (
      <EmptyState
        icon={<IconShield size={22} />}
        title="Administrators only"
        description="Your account can read everything and use the workspace, but desk configuration is limited to the admin allowlist."
        action={
          <Link href="/" className="inline-flex h-10 items-center rounded-xl bg-accent px-4 text-sm font-medium text-accent-fg">
            Back to the desk
          </Link>
        }
      />
    );
  }

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Administration"
        title="Universe & desk defaults"
        description="The desk only ranks names on this list, and every run costs data and model calls — which is why this page is admin-only. Defaults set what anonymous visitors see first and what the scheduler runs."
        actions={
          <>
            {market ? <Badge tone="accent">{market.label}</Badge> : null}
            <Button onClick={() => void runNow()} loading={running} disabled={running || !marketId}>
              {!running ? <IconPlay size={14} /> : null}
              Run desk now
            </Button>
          </>
        }
      />

      {error ? (
        <Alert tone="danger" icon={<IconAlert size={16} />}>
          {error}
        </Alert>
      ) : null}
      {message ? (
        <Alert tone="success" icon={<IconCheck size={16} />}>
          {message}
        </Alert>
      ) : null}

      <div className="grid gap-4 lg:grid-cols-[0.9fr_1.1fr]">
        <Card className="fade-up">
          <CardHeader
            title="Default venue"
            description="What the desk shows to anonymous visitors and refreshes on the schedule. Switch venues from the sidebar to edit another book."
          />
          <div className="px-5 py-4">
            {loading || !catalog ? (
              <Skeleton className="h-16" />
            ) : (
              <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-border bg-surface-2/60 px-4 py-3">
                <div className="min-w-0">
                  <div className="text-xs text-muted">Current default</div>
                  <div className="truncate text-sm font-semibold text-fg">{defaultMarket?.label ?? "—"}</div>
                </div>
                {market && defaultMarket?.id !== market.id ? (
                  <Button variant="secondary" size="sm" onClick={() => void makeDefaultMarket()}>
                    Make {market.exchange_code} the default
                  </Button>
                ) : (
                  <Badge tone="success" dot>
                    Editing the default venue
                  </Badge>
                )}
              </div>
            )}
          </div>
        </Card>

        <Card className="fade-up">
          <CardHeader
            title="Default risk appetite"
            description="Policy applied when the desk runs. Signed-in users can re-rank under their own appetite; this is the baseline."
          />
          <div className="p-5">
            <AppetiteCards value={loading ? null : defaultAppetite} onChange={(next) => void saveDefaultAppetite(next)} disabled={loading} />
          </div>
        </Card>
      </div>

      <Card className="fade-up">
        <CardHeader
          title="Analyzed universe"
          description={`Comma or space separated symbols for ${market?.label ?? "this venue"}. ${market?.symbol_hint ?? ""}`}
          action={
            <div className="flex items-center gap-2">
              {dirty ? <Badge tone="warning" dot>Unsaved</Badge> : null}
              <Badge tone="neutral" className="mono tabular">
                {draftTickers.length}
              </Badge>
            </div>
          }
        />
        <div className="grid gap-5 p-5 lg:grid-cols-[1fr_1fr]">
          <div>
            <textarea
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              spellCheck={false}
              rows={7}
              placeholder="AAPL, MSFT, NVDA…"
              className="mono w-full resize-y rounded-xl border border-border bg-surface-2/60 px-4 py-3 text-sm leading-relaxed text-fg outline-none transition placeholder:text-muted-2 focus:border-accent focus:bg-surface"
            />
            <div className="mt-3 flex items-center gap-3">
              <Button onClick={() => void saveUniverse()} loading={saving} disabled={saving || draftTickers.length === 0}>
                Save universe
              </Button>
              {dirty ? (
                <Button variant="ghost" size="md" onClick={() => setDraft(rows.map((r) => r.ticker).join(", "))}>
                  Reset
                </Button>
              ) : null}
            </div>
          </div>
          <div>
            <div className="mb-2 text-xs font-medium text-muted">Current coverage</div>
            {loading ? (
              <div className="grid gap-2 sm:grid-cols-2">
                {Array.from({ length: 6 }).map((_, i) => (
                  <Skeleton key={i} className="h-14" />
                ))}
              </div>
            ) : rows.length ? (
              <div className="grid max-h-[340px] gap-2 overflow-y-auto pr-1 sm:grid-cols-2">
                {rows.map((row) => (
                  <div key={row.ticker} className="flex items-center gap-3 rounded-xl border border-border bg-surface px-3 py-2.5">
                    <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-accent-soft text-accent">
                      <IconGlobe size={14} />
                    </span>
                    <span className="min-w-0">
                      <span className="mono block text-xs font-semibold text-fg">{row.ticker}</span>
                      <span className="block truncate text-[11px] text-muted">{row.name ?? "—"}</span>
                      {row.sector ? <span className="block truncate text-[10px] text-muted-2">{row.sector}</span> : null}
                    </span>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-sm text-muted">No names yet.</p>
            )}
          </div>
        </div>
      </Card>

      <Card className="fade-up">
        <CardHeader
          title="Coverage requests"
          description="Tickers users have starred that are not in the analyzed universe. Click to add them to the draft above."
          action={
            <Badge tone="neutral" className="mono tabular">
              {requestsHere.length}
            </Badge>
          }
        />
        {requests === null ? (
          <div className="p-5">
            <Skeleton className="h-10" />
          </div>
        ) : requestsHere.length === 0 ? (
          <EmptyState icon={<IconStar size={20} />} title="No requests for this venue" description="Everything users have starred here is already covered." />
        ) : (
          <ul className="flex flex-wrap gap-2 p-5">
            {requestsHere.map((item) => {
              const queued = draftTickers.includes(item.ticker);
              return (
                <li key={item.ticker}>
                  <button
                    onClick={() => addRequested(item.ticker)}
                    disabled={queued}
                    className={cx(
                      "mono inline-flex h-9 items-center gap-2 rounded-xl border px-3 text-xs font-semibold transition",
                      queued
                        ? "border-transparent bg-success-soft text-success"
                        : "border-border bg-surface text-fg hover:border-accent hover:text-accent",
                    )}
                  >
                    {item.ticker}
                    <span className="rounded-full bg-surface-2 px-1.5 text-[10px] font-medium text-muted">
                      {item.requests} {item.requests === 1 ? "user" : "users"}
                    </span>
                    {queued ? <IconCheck size={12} /> : null}
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </Card>

      <Alert tone="neutral" icon={<IconShield size={16} />}>
        Agents propose; policy disposes. The language model cannot override liquidity, sector, or evidence floors set here.
      </Alert>
    </div>
  );
}
