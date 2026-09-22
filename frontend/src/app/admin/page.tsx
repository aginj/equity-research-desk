"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useMemo, useState } from "react";

import { AdminPeople } from "@/components/AdminPeople";
import { AppetiteCards } from "@/components/AppetiteCards";
import { TrackRecordCard } from "@/components/RatingTimeline";
import { RunHistory } from "@/components/RunHistory";
import { IconAlert, IconCheck, IconGlobe, IconPlay, IconShield, IconStar } from "@/components/icons";
import { useWorkspace } from "@/components/WorkspaceProvider";
import { Alert, Badge, Button, Card, CardHeader, EmptyState, PageHeader, Skeleton, cx } from "@/components/ui";
import { ApiError, api } from "@/lib/api";
import type {
  CoverageRequest,
  DeskSchedule,
  Market,
  MarketScheduleRow,
  RiskAppetite,
  TrackRecord,
  UniversePreset,
  UniverseTicker,
} from "@/lib/types";

/**
 * Desk administration. The venue selected in the sidebar is the one being edited; the
 * "desk default" controls what anonymous visitors see first. Clock-time schedules are
 * per venue (two weekday times in that market's timezone).
 */
export default function AdminPage() {
  return (
    <Suspense fallback={<Skeleton className="h-96" />}>
      <Admin />
    </Suspense>
  );
}

function Admin() {
  const params = useSearchParams();
  const tab = params.get("tab") === "runs" ? "runs" : params.get("tab") === "users" ? "users" : "desk";
  const { auth, isAdmin, market, catalog, loading: workspaceLoading } = useWorkspace();
  const [rows, setRows] = useState<UniverseTicker[]>([]);
  const [draft, setDraft] = useState("");
  const [defaultAppetite, setDefaultAppetite] = useState<RiskAppetite | null>(null);
  const [defaultMarket, setDefaultMarket] = useState<Market | null>(null);
  const [requests, setRequests] = useState<CoverageRequest[] | null>(null);
  const [schedule, setSchedule] = useState<DeskSchedule | null>(null);
  const [scheduleDraft, setScheduleDraft] = useState<MarketScheduleRow[]>([]);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [savingSchedule, setSavingSchedule] = useState(false);
  const [running, setRunning] = useState(false);
  const [presets, setPresets] = useState<UniversePreset[]>([]);
  const [record, setRecord] = useState<TrackRecord | null>(null);
  const [validation, setValidation] = useState<string | null>(null);

  const marketId = market?.id;

  const load = useCallback(async () => {
    if (!marketId) return;
    setLoading(true);
    try {
      const [universe, appetite, defaults, coverage, sched, presetPayload, track] = await Promise.all([
        api.universe(marketId),
        api.appetite(),
        api.markets(),
        api.coverageRequests(),
        api.schedule(),
        api.presets(marketId).catch(() => ({ presets: [] as UniversePreset[] })),
        api.trackRecord(marketId).catch(() => null),
      ]);
      setRows(universe);
      setDraft(universe.map((row) => row.ticker).join(", "));
      setDefaultAppetite(appetite.risk_appetite);
      setDefaultMarket(defaults.active);
      setRequests(coverage.requests);
      setSchedule(sched);
      setScheduleDraft(sched.markets);
      setPresets(presetPayload.presets);
      setRecord(track);
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
  const scheduleDirty = useMemo(() => {
    if (!schedule) return false;
    return JSON.stringify(scheduleDraft) !== JSON.stringify(schedule.markets);
  }, [schedule, scheduleDraft]);

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

  async function saveSchedule() {
    setError(null);
    setMessage(null);
    setSavingSchedule(true);
    try {
      const next = await api.setSchedule(scheduleDraft);
      setSchedule(next);
      setScheduleDraft(next.markets);
      setMessage(next.clock ? "Schedule saved · weekday clock times are armed" : "Schedule cleared · no clock-time runs");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save schedule");
    } finally {
      setSavingSchedule(false);
    }
  }

  function setSlot(marketId: string, slot: "morning" | "afternoon", value: string) {
    const text = value.trim();
    const match = /^(\d{1,2}):([0-5]\d)/.exec(text);
    const stamp = !text ? null : match ? `${match[1].padStart(2, "0")}:${match[2]}` : text;
    setScheduleDraft((current) =>
      current.map((row) => (row.market_id === marketId ? { ...row, [slot]: stamp } : row)),
    );
  }

  function setEnabled(marketId: string, enabled: boolean) {
    setScheduleDraft((current) => current.map((row) => (row.market_id === marketId ? { ...row, enabled } : row)));
  }

  function setClosedDates(marketId: string, value: string) {
    const closed_dates = value
      .split(/[\s,]+/)
      .map((item) => item.trim())
      .filter(Boolean);
    setScheduleDraft((current) => current.map((row) => (row.market_id === marketId ? { ...row, closed_dates } : row)));
  }

  function loadPreset(preset: UniversePreset) {
    setDraft(preset.tickers.join(", "));
    setMessage(`Loaded ${preset.label} (${preset.tickers.length} names). Save to apply.`);
  }

  async function validateDraft() {
    setValidation(null);
    try {
      const result = await api.validateUniverse(draftTickers, marketId);
      if (!result.verified) {
        setValidation("Symbols not verified (no Finnhub key or demo mode).");
        return;
      }
      const unknown = result.tickers.filter((row) => row.status !== "ok").map((row) => row.ticker);
      setValidation(unknown.length ? `Unknown: ${unknown.join(", ")}` : `Verified ${result.tickers.length} symbols.`);
    } catch (err) {
      setValidation(err instanceof Error ? err.message : "Validate failed");
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

  if (!workspaceLoading && !isAdmin) {
    if (auth === "authenticated") {
      return (
        <EmptyState
          icon={<IconShield size={22} />}
          title="Administrators only"
          description="Your account can read everything and use the workspace, but running agents and desk configuration are limited to the admin account."
          action={
            <Link href="/" className="inline-flex h-10 items-center rounded-xl bg-accent px-4 text-sm font-medium text-accent-fg">
              Back to the desk
            </Link>
          }
        />
      );
    }
    return (
      <EmptyState
        icon={<IconShield size={22} />}
        title="Sign in as admin"
        description="Only the desk admin can run agents, edit the universe, and change defaults. The first local account created on this desk is admin."
        action={
          <Link href="/signin?callbackUrl=%2Fadmin" className="inline-flex h-10 items-center rounded-xl bg-accent px-4 text-sm font-medium text-accent-fg">
            Sign in
          </Link>
        }
      />
    );
  }

  const nextFire = schedule?.next[0];

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Administration"
        title={tab === "runs" ? "Run history" : tab === "users" ? "Users & audit" : "Universe & desk defaults"}
        description={
          tab === "runs"
            ? "Audit of desk cycles for the venue selected in the sidebar."
            : tab === "users"
              ? "Local accounts, roles, and an audit of admin mutations."
              : "The desk only ranks names on this list. Clock-time schedules run weekdays in each venue's own timezone. The API process must stay running for those jobs to fire."
        }
        actions={
          <>
            {market ? <Badge tone="accent">{market.label}</Badge> : null}
            {tab === "desk" ? (
              <Button onClick={() => void runNow()} loading={running} disabled={running || !marketId}>
                {!running ? <IconPlay size={14} /> : null}
                Run desk now
              </Button>
            ) : null}
          </>
        }
      />

      <div className="flex gap-1 rounded-xl border border-border bg-surface p-1 w-fit">
        <Link
          href="/admin"
          className={cx(
            "rounded-lg px-3 py-1.5 text-xs font-medium transition",
            tab === "desk" ? "bg-accent-soft text-fg" : "text-muted hover:text-fg",
          )}
        >
          Desk
        </Link>
        <Link
          href="/admin?tab=runs"
          className={cx(
            "rounded-lg px-3 py-1.5 text-xs font-medium transition",
            tab === "runs" ? "bg-accent-soft text-fg" : "text-muted hover:text-fg",
          )}
        >
          Run history
        </Link>
        <Link
          href="/admin?tab=users"
          className={cx(
            "rounded-lg px-3 py-1.5 text-xs font-medium transition",
            tab === "users" ? "bg-accent-soft text-fg" : "text-muted hover:text-fg",
          )}
        >
          Users
        </Link>
      </div>

      {error ? (
        <Alert tone="danger" icon={<IconAlert size={16} />}>
          {error}
        </Alert>
      ) : null}
      {message && tab === "desk" ? (
        <Alert tone="success" icon={<IconCheck size={16} />}>
          {message}
        </Alert>
      ) : null}

      {tab === "runs" ? (
        <RunHistory marketId={marketId} marketLabel={market?.label} />
      ) : tab === "users" ? (
        <AdminPeople />
      ) : (
        <>
      <div className="grid gap-4 lg:grid-cols-[0.9fr_1.1fr]">
        <Card className="fade-up">
          <CardHeader
            title="Default venue"
            description="What the desk shows to anonymous visitors first. Switch venues from the sidebar to edit another book."
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
          title="Scheduled runs"
          description="Two weekday times per venue, in that market's timezone. Leave a box empty to skip. Overlapping times run one after another."
          action={
            nextFire ? (
              <Badge tone="accent" className="max-w-[220px] truncate">
                Next · {nextFire.label} {nextFire.local_time}
              </Badge>
            ) : (
              <Badge tone="neutral">No clock jobs</Badge>
            )
          }
        />
        <div className="overflow-x-auto p-5 pt-3">
          {loading || !schedule ? (
            <Skeleton className="h-40" />
          ) : (
            <>
              <ul className="space-y-3 md:hidden">
                {scheduleDraft.map((row) => (
                  <li key={row.market_id} className="rounded-xl border border-border p-3">
                    <div className="text-xs font-medium text-fg">{row.label}</div>
                    <div className="mono text-[11px] text-muted">{row.timezone}</div>
                    <label className="mt-2 flex items-center gap-2 text-xs">
                      <input
                        type="checkbox"
                        checked={row.enabled !== false}
                        onChange={(e) => setEnabled(row.market_id, e.target.checked)}
                        aria-label={`Pause ${row.label}`}
                      />
                      Enabled
                    </label>
                    <div className="mt-2 grid grid-cols-2 gap-2">
                      <input
                        type="time"
                        step={60}
                        aria-label={`${row.label} morning`}
                        value={row.morning ?? ""}
                        onChange={(e) => setSlot(row.market_id, "morning", e.target.value)}
                        className="h-9 rounded-lg border border-border-strong bg-surface px-2 text-xs text-fg"
                      />
                      <input
                        type="time"
                        step={60}
                        aria-label={`${row.label} afternoon`}
                        value={row.afternoon ?? ""}
                        onChange={(e) => setSlot(row.market_id, "afternoon", e.target.value)}
                        className="h-9 rounded-lg border border-border-strong bg-surface px-2 text-xs text-fg"
                      />
                    </div>
                    <input
                      value={(row.closed_dates ?? []).join(", ")}
                      onChange={(e) => setClosedDates(row.market_id, e.target.value)}
                      placeholder="Closed dates YYYY-MM-DD"
                      aria-label={`${row.label} closed dates`}
                      className="mt-2 h-9 w-full rounded-lg border border-border-strong bg-surface px-2 text-xs"
                    />
                  </li>
                ))}
              </ul>
              <table className="hidden min-w-full text-left text-sm md:table">
                <thead>
                  <tr className="border-b border-border text-[11px] uppercase tracking-wider text-muted">
                    <th className="py-2 pr-3 font-medium">Venue</th>
                    <th className="py-2 pr-3 font-medium">On</th>
                    <th className="py-2 pr-3 font-medium">Timezone</th>
                    <th className="py-2 pr-3 font-medium">Morning</th>
                    <th className="py-2 pr-3 font-medium">Afternoon</th>
                    <th className="py-2 pr-3 font-medium">Closed dates</th>
                    <th className="py-2 font-medium">Last</th>
                  </tr>
                </thead>
                <tbody>
                  {scheduleDraft.map((row) => {
                    const last = row.last ?? {};
                    const latest = Object.values(last)[0];
                    return (
                      <tr key={row.market_id} className="border-b border-border last:border-0">
                        <td className="py-2.5 pr-3 text-xs font-medium text-fg">{row.label}</td>
                        <td className="py-2.5 pr-3">
                          <input
                            type="checkbox"
                            checked={row.enabled !== false}
                            onChange={(e) => setEnabled(row.market_id, e.target.checked)}
                            aria-label={`Enable ${row.label} schedule`}
                          />
                        </td>
                        <td className="mono py-2.5 pr-3 text-[11px] text-muted">{row.timezone}</td>
                        <td className="py-2.5 pr-3">
                          <input
                            type="time"
                            step={60}
                            aria-label={`${row.label} morning`}
                            value={row.morning ?? ""}
                            onChange={(e) => setSlot(row.market_id, "morning", e.target.value)}
                            className="h-9 rounded-lg border border-border-strong bg-surface px-2 text-xs text-fg"
                          />
                        </td>
                        <td className="py-2.5 pr-3">
                          <input
                            type="time"
                            step={60}
                            aria-label={`${row.label} afternoon`}
                            value={row.afternoon ?? ""}
                            onChange={(e) => setSlot(row.market_id, "afternoon", e.target.value)}
                            className="h-9 rounded-lg border border-border-strong bg-surface px-2 text-xs text-fg"
                          />
                        </td>
                        <td className="py-2.5 pr-3">
                          <input
                            value={(row.closed_dates ?? []).join(", ")}
                            onChange={(e) => setClosedDates(row.market_id, e.target.value)}
                            placeholder="2026-01-01"
                            aria-label={`${row.label} closed dates`}
                            className="h-9 w-40 rounded-lg border border-border-strong bg-surface px-2 text-xs"
                          />
                        </td>
                        <td className="py-2.5 text-[11px] text-muted">
                          {latest?.last_status ? `${latest.last_status}${latest.last_fired_at ? ` · ${latest.last_fired_at.slice(0, 16)}` : ""}` : "—"}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </>
          )}
          <div className="mt-4 flex flex-wrap items-center gap-3">
            <Button onClick={() => void saveSchedule()} loading={savingSchedule} disabled={savingSchedule || loading} data-testid="save-schedule">
              Save schedule
            </Button>
            {scheduleDirty ? <Badge tone="warning" dot>Unsaved</Badge> : null}
            {schedule && !schedule.clock && schedule.interval_hours > 0 ? (
              <span className="text-[11px] text-muted">
                Fallback interval: every {schedule.interval_hours} hour(s) on the default venue until you set clock times.
              </span>
            ) : (
              <span className="text-[11px] text-muted">The API must stay running overnight for 09:30 jobs to fire.</span>
            )}
          </div>
        </div>
      </Card>

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
            <div className="mt-3 flex flex-wrap items-center gap-2">
              {presets.map((preset) => (
                <Button key={preset.id} variant="secondary" size="sm" onClick={() => loadPreset(preset)}>
                  Load {preset.label}
                </Button>
              ))}
              <Button variant="ghost" size="sm" onClick={() => void validateDraft()} disabled={draftTickers.length === 0}>
                Validate symbols
              </Button>
            </div>
            {validation ? <p className="mt-2 text-xs text-muted">{validation}</p> : null}
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

      <TrackRecordCard record={record} />

      <Alert tone="neutral" icon={<IconShield size={16} />}>
        Agents propose; policy disposes. The language model cannot override liquidity, sector, or evidence floors set here.
      </Alert>
        </>
      )}
    </div>
  );
}
