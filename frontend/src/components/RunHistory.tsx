"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { IconAlert, IconHistory } from "@/components/icons";
import { Alert, Badge, Button, Card, EmptyState, Skeleton, type Tone } from "@/components/ui";
import { api } from "@/lib/api";
import { relativeTime, when } from "@/lib/format";
import type { AnalysisResult, RunStatus } from "@/lib/types";

const STATUS_TONE: Record<RunStatus, Tone> = {
  completed: "success",
  failed: "danger",
  running: "accent",
  queued: "neutral",
};

function triggerLabel(value?: string | null) {
  if (!value) return "—";
  if (value.startsWith("manual:")) return "Manual";
  if (value.startsWith("schedule:")) return "Schedule";
  if (value === "interval") return "Interval";
  if (value === "api-key") return "API key";
  return value;
}

function usageLabel(row: AnalysisResult) {
  const usage = row.summary?.usage;
  if (!usage) return "—";
  return `${usage.llm_calls} LLM · ${usage.vendor_calls} vendor`;
}

export function RunHistory({ marketId, marketLabel }: { marketId?: string; marketLabel?: string }) {
  const [rows, setRows] = useState<AnalysisResult[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!marketId) return;
    let cancelled = false;
    setLoading(true);
    api
      .runs(50, marketId)
      .then((r) => !cancelled && setRows(r))
      .catch((err) => !cancelled && setError(err instanceof Error ? err.message : "Failed to load"))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [marketId]);

  return (
    <div className="space-y-4">
      <p className="text-sm text-muted">
        Every desk cycle for {marketLabel ?? "this venue"} is persisted with recommendations, sources, and the policy
        that was in force.
        {rows.length ? (
          <Badge tone="neutral" className="ml-2">
            {rows.length} runs
          </Badge>
        ) : null}
      </p>

      {error ? (
        <Alert tone="danger" icon={<IconAlert size={16} />}>
          {error}
        </Alert>
      ) : null}

      <Card className="fade-up overflow-hidden">
        {loading || !marketId ? (
          <div className="divide-y divide-border">
            {Array.from({ length: 5 }).map((_, i) => (
              <div key={i} className="flex items-center gap-4 px-5 py-4">
                <Skeleton className="h-4 w-24" />
                <Skeleton className="h-5 w-20 rounded-full" />
                <Skeleton className="h-4 flex-1" />
              </div>
            ))}
          </div>
        ) : rows.length === 0 ? (
          <EmptyState
            icon={<IconHistory size={22} />}
            title="No runs stored yet"
            description="Once you run the desk, every cycle will be listed here with its outcome."
            action={
              <Link href="/admin">
                <Button>Run the desk</Button>
              </Link>
            }
          />
        ) : (
          <>
            <ul className="divide-y divide-border md:hidden">
              {rows.map((row) => (
                <li key={row.run_id} className="px-4 py-4">
                  <div className="flex items-center justify-between gap-2">
                    <span className="mono text-xs font-semibold text-accent">{row.run_id}</span>
                    <Badge tone={STATUS_TONE[row.status]} dot className="capitalize">
                      {row.status}
                    </Badge>
                  </div>
                  <div className="mt-1 text-xs text-muted">{relativeTime(row.started_at)}</div>
                  <div className="mt-1 text-[13px] text-fg-2">{row.summary?.headline ?? row.error ?? row.stage}</div>
                  <div className="mt-2 flex flex-wrap gap-2 text-[11px] text-muted">
                    <span>{triggerLabel(row.triggered_by)}</span>
                    <span>{usageLabel(row)}</span>
                  </div>
                </li>
              ))}
            </ul>
            <div className="hidden overflow-x-auto md:block">
              <table className="min-w-full text-left text-sm">
                <thead>
                  <tr className="border-b border-border text-[11px] uppercase tracking-wider text-muted">
                    <th className="px-5 py-3 font-medium">Run</th>
                    <th className="px-3 py-3 font-medium">Status</th>
                    <th className="px-3 py-3 font-medium">Trigger</th>
                    <th className="px-3 py-3 font-medium">Venue</th>
                    <th className="px-3 py-3 font-medium">Started</th>
                    <th className="px-3 py-3 font-medium">Duration</th>
                    <th className="px-3 py-3 font-medium">Names</th>
                    <th className="px-3 py-3 font-medium">Usage</th>
                    <th className="px-5 py-3 font-medium">Outcome</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row) => {
                    const duration =
                      row.finished_at && row.started_at
                        ? `${Math.max(0, Math.round((+new Date(row.finished_at) - +new Date(row.started_at)) / 1000))}s`
                        : "—";
                    return (
                      <tr key={row.run_id} className="row-hover border-b border-border last:border-0">
                        <td className="px-5 py-3.5">
                          <Link href="/" className="mono text-xs font-semibold text-accent underline-offset-4 hover:underline">
                            {row.run_id}
                          </Link>
                        </td>
                        <td className="px-3 py-3.5">
                          <Badge tone={STATUS_TONE[row.status]} dot pulse={row.status === "running"} className="capitalize">
                            {row.status}
                          </Badge>
                        </td>
                        <td className="px-3 py-3.5 text-xs text-muted">{triggerLabel(row.triggered_by)}</td>
                        <td className="px-3 py-3.5 text-xs text-muted">{row.summary?.market_label ?? row.market_id ?? "—"}</td>
                        <td className="px-3 py-3.5">
                          <div className="text-xs text-fg-2">{relativeTime(row.started_at)}</div>
                          <div className="text-[11px] text-muted-2">{when(row.started_at)}</div>
                        </td>
                        <td className="mono tabular px-3 py-3.5 text-xs text-fg-2">{duration}</td>
                        <td className="mono tabular px-3 py-3.5 text-xs text-fg-2">{row.summary?.tickers_analyzed ?? "—"}</td>
                        <td className="px-3 py-3.5 text-[11px] text-muted">{usageLabel(row)}</td>
                        <td className="max-w-md px-5 py-3.5 text-[13px] text-fg-2">
                          <span className={row.status === "failed" ? "text-danger" : ""}>
                            {row.summary?.headline ?? row.error ?? row.stage}
                          </span>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </>
        )}
      </Card>
    </div>
  );
}
