"use client";

import { IconCheck } from "@/components/icons";
import { cx } from "@/components/ui";
import type { RiskAppetite } from "@/lib/types";

export const APPETITES: { id: RiskAppetite; title: string; blurb: string; limits: string }[] = [
  {
    id: "conservative",
    title: "Conservative",
    blurb: "Few names, tight sector caps, high evidence bar.",
    limits: "≤4 accumulate · 1 per sector · 3 sources",
  },
  {
    id: "balanced",
    title: "Balanced",
    blurb: "Default institutional book.",
    limits: "≤6 accumulate · 2 per sector · 2 sources",
  },
  {
    id: "aggressive",
    title: "Aggressive",
    blurb: "Wider book, lower conviction floor, more event risk allowed.",
    limits: "≤8 accumulate · 3 per sector · 1 source",
  },
];

/**
 * Three-way appetite selector. `value === null` renders nothing selected (used while the
 * server value is loading so the wrong card never flashes as active).
 */
export function AppetiteCards({
  value,
  onChange,
  disabled = false,
}: {
  value: RiskAppetite | null;
  onChange: (next: RiskAppetite) => void;
  disabled?: boolean;
}) {
  return (
    <div className="grid gap-3 md:grid-cols-3">
      {APPETITES.map((option) => {
        const selected = value === option.id;
        return (
          <button
            key={option.id}
            type="button"
            onClick={() => onChange(option.id)}
            aria-pressed={selected}
            disabled={disabled}
            className={cx(
              "group relative rounded-xl border p-4 text-left transition disabled:opacity-60",
              selected
                ? "border-accent bg-accent-soft shadow-[inset_0_0_0_1px_var(--accent)]"
                : "border-border bg-surface hover:border-border-strong hover:bg-surface-hover",
            )}
          >
            <div className="flex items-center justify-between">
              <span className={cx("text-sm font-semibold", selected ? "text-accent" : "text-fg")}>{option.title}</span>
              <span
                className={cx(
                  "flex h-5 w-5 items-center justify-center rounded-full border transition",
                  selected ? "border-accent bg-accent text-accent-fg" : "border-border-strong text-transparent",
                )}
              >
                <IconCheck size={12} strokeWidth={2.8} />
              </span>
            </div>
            <p className="mt-2 text-xs leading-relaxed text-muted">{option.blurb}</p>
            <p className="mono mt-3 text-[10px] uppercase tracking-wider text-muted-2">{option.limits}</p>
          </button>
        );
      })}
    </div>
  );
}
