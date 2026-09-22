"use client";

import { Card, CardHeader } from "@/components/ui";
import { actionLabel, money, pct, when } from "@/lib/format";
import type { RatingPoint } from "@/lib/types";

export function RatingTimeline({ points }: { points: RatingPoint[] }) {
  if (!points.length) {
    return (
      <Card>
        <CardHeader title="Rating history" description="No earlier snapshots for this name yet." />
      </Card>
    );
  }
  const convictions = [...points].reverse().map((p) => p.conviction);
  const max = Math.max(...convictions, 0.01);
  return (
    <Card>
      <CardHeader title="Rating history" description={`${points.length} completed runs`} />
      <div className="flex h-16 items-end gap-1 px-5 pt-3">
        {convictions.map((value, i) => (
          <div
            key={i}
            className="flex-1 rounded-t bg-accent/70"
            style={{ height: `${Math.max(8, (value / max) * 100)}%` }}
            title={`${Math.round(value * 100)}`}
          />
        ))}
      </div>
      <ul className="divide-y divide-border">
        {points.map((point) => (
          <li key={point.run_id} className="flex items-center justify-between gap-3 px-5 py-2.5 text-xs">
            <span className="text-muted">{when(point.finished_at)}</span>
            <span className="font-medium text-fg">{actionLabel(point.action as "accumulate")}</span>
            <span className="mono tabular text-fg-2">{Math.round(point.conviction * 100)}</span>
            <span className="mono tabular text-muted">{money(point.price, point.currency)}</span>
          </li>
        ))}
      </ul>
    </Card>
  );
}

export function TrackRecordCard({
  record,
}: {
  record: {
    caveat: string;
    horizons: Record<string, { n: number; mean_return: number | null; hit_rate: number | null }>;
  } | null;
}) {
  if (!record) return null;
  const keys = ["30", "90", "180"];
  return (
    <Card className="fade-up">
      <CardHeader
        title="Desk record"
        description="Forward mark-to-snapshot of past accumulate calls. Research only, not a live book."
      />
      <div className="grid gap-3 p-5 sm:grid-cols-3">
        {keys.map((key) => {
          const bucket = record.horizons[key];
          return (
            <div key={key} className="rounded-xl border border-border bg-surface-2/60 p-3">
              <div className="text-[11px] uppercase tracking-wider text-muted">{key}d</div>
              <div className="mono mt-1 text-lg font-semibold text-fg">
                {bucket?.mean_return == null ? "—" : pct(bucket.mean_return * 100, 1)}
              </div>
              <div className="text-[11px] text-muted">
                {bucket?.n ?? 0} calls
                {bucket?.hit_rate != null ? ` · hit ${(bucket.hit_rate * 100).toFixed(0)}%` : ""}
              </div>
            </div>
          );
        })}
      </div>
      <p className="px-5 pb-4 text-[11px] leading-relaxed text-muted">{record.caveat}</p>
    </Card>
  );
}
