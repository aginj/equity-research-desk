"use client";

import Link from "next/link";

import { ActionPill } from "@/components/ActionPill";
import { IconSpark } from "@/components/icons";
import { Card, CardHeader, EmptyState } from "@/components/ui";
import { horizonLabel, ideaHref } from "@/lib/format";
import type { Recommendation } from "@/lib/types";

export function TopIdeas({ rows }: { rows: Recommendation[] }) {
  return (
    <Card className="fade-up">
      <CardHeader
        title="Top ideas"
        description="Names that cleared desk policy under the current appetite. Research ratings, not buy orders."
      />
      {rows.length === 0 ? (
        <EmptyState
          icon={<IconSpark size={20} />}
          title="No accumulate ratings this run"
          description="Policy did not clear any names. Open the ranked book below for watches and reduces."
        />
      ) : (
        <div className="grid gap-3 p-5 sm:grid-cols-2 xl:grid-cols-3">
          {rows.map((row) => (
            <Link
              key={row.ticker}
              href={ideaHref(row.ticker)}
              className="rounded-xl border border-border bg-surface p-4 transition hover:border-accent"
            >
              <div className="flex items-center justify-between gap-2">
                <span className="mono text-sm font-semibold text-fg">{row.ticker}</span>
                <ActionPill action={row.action} />
              </div>
              <div className="mt-1 truncate text-xs text-muted">{row.name}</div>
              <div className="mt-3 flex items-center justify-between text-[11px] text-muted">
                <span>Conviction {Math.round(row.conviction * 100)}</span>
                <span>{horizonLabel(row.horizon)}</span>
              </div>
              <p className="mt-2 line-clamp-2 text-[13px] leading-relaxed text-fg-2">{row.thesis}</p>
            </Link>
          ))}
        </div>
      )}
    </Card>
  );
}
