"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { IconAlert, IconHistory } from "@/components/icons";
import { useWorkspace } from "@/components/WorkspaceProvider";
import { Alert, Badge, Button, Card, EmptyState, PageHeader, Skeleton, type Tone } from "@/components/ui";
import { api } from "@/lib/api";
import { relativeTime, when } from "@/lib/format";
import type { AnalysisResult, RunStatus } from "@/lib/types";

const STATUS_TONE: Record<RunStatus, Tone> = {
  completed: "success",
  failed: "danger",
  running: "accent",
  queued: "neutral",
};

export default function RunsPage() {
  const { market, loading: workspaceLoading } = useWorkspace();
  const [rows, setRows] = useState<AnalysisResult[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const marketId = market?.id;
  useEffect(() => {
    if (workspaceLoading || !marketId) return;
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
  }, [marketId, workspaceLoading]);

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Audit"
        title="Run history"
        description={`Every desk cycle for ${market?.label ?? "this venue"} is persisted with recommendations, sources, and the policy that was in force.`}
        actions={rows.length ? <Badge tone="neutral">{rows.length} runs</Badge> : null}
      />

      {error ? (
        <Alert tone="danger" icon={<IconAlert size={16} />}>
          {error}
        </Alert>
      ) : null}

      <Card className="fade-up overflow-hidden">
        {loading || workspaceLoading ? (
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
              <Link href="/">
                <Button>Go to desk</Button>
              </Link>
            }
          />
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full text-left text-sm">
              <thead>
                <tr className="border-b border-border text-[11px] uppercase tracking-wider text-muted">
                  <th className="px-5 py-3 font-medium">Run</th>
                  <th className="px-3 py-3 font-medium">Status</th>
                  <th className="px-3 py-3 font-medium">Venue</th>
                  <th className="px-3 py-3 font-medium">Started</th>
                  <th className="px-3 py-3 font-medium">Duration</th>
                  <th className="px-3 py-3 font-medium">Names</th>
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
                        <Link href="/" className="mono text-xs font-semibold text-accent hover:underline underline-offset-4">
                          {row.run_id}
                        </Link>
                      </td>
                      <td className="px-3 py-3.5">
                        <Badge tone={STATUS_TONE[row.status]} dot pulse={row.status === "running"} className="capitalize">
                          {row.status}
                        </Badge>
                      </td>
                      <td className="px-3 py-3.5 text-xs text-muted">{row.summary?.market_label ?? row.market_id ?? "—"}</td>
                      <td className="px-3 py-3.5">
                        <div className="text-xs text-fg-2">{relativeTime(row.started_at)}</div>
                        <div className="text-[11px] text-muted-2">{when(row.started_at)}</div>
                      </td>
                      <td className="mono tabular px-3 py-3.5 text-xs text-fg-2">{duration}</td>
                      <td className="mono tabular px-3 py-3.5 text-xs text-fg-2">{row.summary?.tickers_analyzed ?? "—"}</td>
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
        )}
      </Card>
    </div>
  );
}
