"use client";

import Link from "next/link";

import { ActionPill } from "@/components/ActionPill";
import { Card, CardHeader } from "@/components/ui";
import { actionLabel, ideaHref, relativeTime } from "@/lib/format";
import type { BookChangeItem, BookChanges } from "@/lib/types";

function Column({ title, rows }: { title: string; rows: BookChangeItem[] }) {
  return (
    <div>
      <div className="text-[11px] font-semibold uppercase tracking-wider text-muted">
        {title} · {rows.length}
      </div>
      {rows.length === 0 ? (
        <p className="mt-2 text-xs text-muted-2">None</p>
      ) : (
        <ul className="mt-2 space-y-1.5">
          {rows.slice(0, 6).map((row) => (
            <li key={row.ticker}>
              <Link href={ideaHref(row.ticker)} className="flex items-center justify-between gap-2 text-xs hover:text-accent">
                <span className="mono font-semibold">{row.ticker}</span>
                <span className="flex items-center gap-1 text-muted">
                  {row.previous_action ? `${actionLabel(row.previous_action)} → ` : null}
                  <ActionPill action={row.action} />
                </span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export function WhatChanged({ changes }: { changes: BookChanges | null }) {
  if (!changes?.previous_run_id) {
    return (
      <Card className="fade-up">
        <CardHeader title="What changed" description="Needs two completed runs on this venue to compare." />
      </Card>
    );
  }
  return (
    <Card className="fade-up">
      <CardHeader
        title="What changed"
        description={
          changes.previous_at
            ? `Versus the previous completed run ${relativeTime(changes.previous_at)}.`
            : "Versus the previous completed run."
        }
      />
      <div className="grid gap-4 p-5 sm:grid-cols-2 lg:grid-cols-4">
        <Column title="New accumulate" rows={changes.new_accumulate} />
        <Column title="Upgrades" rows={changes.upgrades} />
        <Column title="Downgrades" rows={changes.downgrades} />
        <Column title="Dropped" rows={changes.dropped} />
      </div>
    </Card>
  );
}
