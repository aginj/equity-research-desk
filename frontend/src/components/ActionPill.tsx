import { Badge, type Tone } from "@/components/ui";
import { actionLabel } from "@/lib/format";
import type { Action } from "@/lib/types";

const TONE: Record<Action, Tone> = {
  accumulate: "success",
  watch: "warning",
  reduce: "danger",
  avoid: "danger",
};

export function ActionPill({ action, size = "sm" }: { action: Action; size?: "sm" | "md" }) {
  return (
    <Badge tone={TONE[action]} dot className={size === "md" ? "px-3 py-1 text-xs" : undefined}>
      {actionLabel(action)}
    </Badge>
  );
}
