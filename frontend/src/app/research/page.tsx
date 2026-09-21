"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { IconAlert, IconFile, IconNews } from "@/components/icons";
import { useWorkspace } from "@/components/WorkspaceProvider";
import { Alert, Badge, Button, Card, CardHeader, EmptyState, PageHeader, Skeleton, cx } from "@/components/ui";
import { api } from "@/lib/api";
import { ideaHref, relativeTime } from "@/lib/format";
import type { AnalysisResult } from "@/lib/types";

type Tab = "news" | "filings";

export default function ResearchPage() {
  const { market, loading: workspaceLoading } = useWorkspace();
  const [run, setRun] = useState<AnalysisResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState<Tab>("news");

  const marketId = market?.id;
  useEffect(() => {
    if (workspaceLoading || !marketId) return;
    let cancelled = false;
    setLoading(true);
    api
      .latest(marketId)
      .then((r) => !cancelled && setRun(r))
      .catch((err) => !cancelled && setError(err instanceof Error ? err.message : "Failed to load"))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [marketId, workspaceLoading]);

  const news = useMemo(() => {
    const items = run?.intel.flatMap((item) => item.news.map((n) => ({ ...n, sector: item.profile.sector }))) ?? [];
    return items.sort((a, b) => +new Date(b.published_at) - +new Date(a.published_at));
  }, [run]);

  const filings = useMemo(() => {
    const items = run?.intel.flatMap((item) => item.filings) ?? [];
    return items.sort((a, b) => +new Date(b.filed_at) - +new Date(a.filed_at));
  }, [run]);

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Wire"
        title="Research tape"
        description="Headlines and regulatory filings attached to the latest desk run. Every item is stored with publisher, timestamp, and URL."
        actions={
          run ? (
            <Badge tone="neutral" className="mono">
              Run {run.run_id} · {relativeTime(run.finished_at ?? run.started_at)}
            </Badge>
          ) : null
        }
      />

      {error ? (
        <Alert tone="danger" icon={<IconAlert size={16} />}>
          {error}
        </Alert>
      ) : null}

      {loading || workspaceLoading ? (
        <div className="grid gap-4 lg:grid-cols-2">
          <Skeleton className="h-96" />
          <Skeleton className="h-96" />
        </div>
      ) : !run ? (
        <Card>
          <EmptyState
            icon={<IconNews size={22} />}
            title="No run on file"
            description="Return to the desk and run analysis first. The tape is built from what the agents actually read."
            action={
              <Link href="/">
                <Button>Go to desk</Button>
              </Link>
            }
          />
        </Card>
      ) : (
        <>
          {/* Mobile tabs */}
          <div className="flex gap-1 rounded-xl border border-border bg-surface p-1 lg:hidden">
            {(["news", "filings"] as Tab[]).map((t) => (
              <button
                key={t}
                onClick={() => setTab(t)}
                className={cx(
                  "flex-1 rounded-lg px-3 py-1.5 text-xs font-medium capitalize transition",
                  tab === t ? "bg-accent-soft text-accent" : "text-muted hover:text-fg",
                )}
              >
                {t} <span className="mono tabular ml-1 text-[10px] opacity-70">{t === "news" ? news.length : filings.length}</span>
              </button>
            ))}
          </div>

          <div className="grid gap-4 lg:grid-cols-2">
            <Card className={cx("fade-up", tab !== "news" && "hidden lg:block")}>
              <CardHeader title="News window" description={`${news.length} headlines across ${run.intel.length} names`} />
              {news.length ? (
                <ul className="divide-y divide-border">
                  {news.map((item) => (
                    <li key={item.id} className="row-hover px-5 py-4">
                      <div className="flex items-center justify-between gap-3">
                        <Link href={ideaHref(item.ticker)} className="mono text-xs font-semibold text-accent hover:underline underline-offset-4">
                          {item.ticker}
                        </Link>
                        <span className="text-[11px] text-muted">{relativeTime(item.published_at)}</span>
                      </div>
                      <a href={item.url} target="_blank" rel="noreferrer" className="mt-1.5 block text-sm font-medium leading-snug text-fg hover:text-accent">
                        {item.headline}
                      </a>
                      {item.summary ? <p className="mt-1.5 line-clamp-3 text-xs leading-relaxed text-muted">{item.summary}</p> : null}
                      <div className="mt-2 flex flex-wrap items-center gap-1.5">
                        <Badge tone="neutral" className="px-2 py-0 text-[10px]">
                          {item.publisher}
                        </Badge>
                        <Badge tone={item.source === "demo" ? "warning" : "success"} className="px-2 py-0 text-[10px]">
                          {item.source}
                        </Badge>
                        <span className="text-[11px] text-muted-2">{item.sector}</span>
                      </div>
                    </li>
                  ))}
                </ul>
              ) : (
                <EmptyState icon={<IconNews size={20} />} title="No headlines" />
              )}
            </Card>

            <Card className={cx("fade-up", tab !== "filings" && "hidden lg:block")}>
              <CardHeader title="Filings" description={`${filings.length} regulatory forms`} />
              {filings.length ? (
                <ul className="divide-y divide-border">
                  {filings.map((item) => (
                    <li key={item.id} className="row-hover px-5 py-4">
                      <div className="flex items-center justify-between gap-3">
                        <div className="flex items-center gap-2">
                          <Link href={ideaHref(item.ticker)} className="mono text-xs font-semibold text-accent hover:underline underline-offset-4">
                            {item.ticker}
                          </Link>
                          <span className="mono rounded-md bg-surface-2 px-1.5 py-0.5 text-[10px] font-semibold text-fg-2">{item.form}</span>
                        </div>
                        <span className="text-[11px] text-muted">{relativeTime(item.filed_at)}</span>
                      </div>
                      <a href={item.url} target="_blank" rel="noreferrer" className="mt-1.5 block text-sm font-medium leading-snug text-fg hover:text-accent">
                        {item.description}
                      </a>
                    </li>
                  ))}
                </ul>
              ) : (
                <EmptyState icon={<IconFile size={20} />} title="No filings" description="This venue has no regulator feed in this build." />
              )}
            </Card>
          </div>
        </>
      )}
    </div>
  );
}
