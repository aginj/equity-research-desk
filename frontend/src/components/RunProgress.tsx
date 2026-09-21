"use client";

import { IconCheck, IconLoader } from "@/components/icons";
import { Card, cx } from "@/components/ui";
import type { RunEvent } from "@/lib/types";

const STAGES: { id: string; label: string }[] = [
  { id: "ingest", label: "Ingest" },
  { id: "news_analyst", label: "News" },
  { id: "filings_analyst", label: "Filings" },
  { id: "fundamentals_analyst", label: "Scoring" },
  { id: "risk_analyst", label: "Risk" },
  { id: "chief_analyst", label: "Chief" },
  { id: "policy", label: "Policy" },
];

export function RunProgress({ event }: { event: RunEvent }) {
  const currentIndex = STAGES.findIndex((s) => s.id === event.stage);
  const pct = Math.round(Math.max(0.02, Math.min(1, event.progress)) * 100);

  return (
    <Card className="fade-up overflow-hidden">
      <div className="flex flex-col gap-4 px-5 py-4 md:flex-row md:items-center md:justify-between">
        <div className="flex min-w-0 items-center gap-3">
          <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-accent-soft text-accent">
            <IconLoader size={16} />
          </span>
          <div className="min-w-0">
            <div className="text-sm font-medium text-fg">{event.message}</div>
            <div className="mono mt-0.5 text-[11px] uppercase tracking-wider text-muted">
              {event.stage.replaceAll("_", " ")} {event.run_id ? `· ${event.run_id}` : ""}
            </div>
          </div>
        </div>
        <div className="mono tabular text-2xl font-semibold text-fg">{pct}%</div>
      </div>

      <div className="h-1 w-full bg-surface-2">
        <div
          className="h-full rounded-r-full bg-gradient-to-r from-accent to-accent-2 transition-[width] duration-500 ease-out"
          style={{ width: `${pct}%` }}
        />
      </div>

      <ol className="grid grid-cols-4 gap-2 px-5 py-4 sm:grid-cols-7">
        {STAGES.map((stage, i) => {
          const done = currentIndex > i || event.stage === "completed";
          const active = currentIndex === i;
          return (
            <li key={stage.id} className="flex items-center gap-2 text-xs">
              <span
                className={cx(
                  "flex h-5 w-5 shrink-0 items-center justify-center rounded-full border text-[10px] transition-colors",
                  done && "border-transparent bg-success text-white",
                  active && "border-accent bg-accent-soft text-accent",
                  !done && !active && "border-border text-muted-2",
                )}
              >
                {done ? <IconCheck size={12} strokeWidth={2.6} /> : i + 1}
              </span>
              <span className={cx("truncate", active ? "font-medium text-fg" : done ? "text-fg-2" : "text-muted-2")}>
                {stage.label}
              </span>
            </li>
          );
        })}
      </ol>
    </Card>
  );
}
