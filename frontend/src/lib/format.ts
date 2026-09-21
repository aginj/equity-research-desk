import type { Action, Horizon } from "./types";

const ZERO_DECIMAL = new Set(["JPY", "KRW"]);

export function money(value: number | null | undefined, currency = "USD") {
  if (value == null || Number.isNaN(value)) return "—";
  const digits = ZERO_DECIMAL.has(currency) ? 0 : 2;
  try {
    return new Intl.NumberFormat(undefined, {
      style: "currency",
      currency,
      maximumFractionDigits: digits,
      minimumFractionDigits: digits,
    }).format(value);
  } catch {
    return `${value.toFixed(digits)} ${currency}`;
  }
}

export function compactCap(value: number | null | undefined, currency = "USD") {
  if (value == null) return "—";
  const abs = Math.abs(value);
  const symbol = money(0, currency).replace(/[\d.,\s]/g, "").trim() || currency;
  if (abs >= 1e12) return `${symbol}${(value / 1e12).toFixed(2)}T`;
  if (abs >= 1e9) return `${symbol}${(value / 1e9).toFixed(1)}B`;
  if (abs >= 1e6) return `${symbol}${(value / 1e6).toFixed(0)}M`;
  return money(value, currency);
}

export function pct(value: number | null | undefined, digits = 2) {
  if (value == null || Number.isNaN(value)) return "—";
  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toFixed(digits)}%`;
}

export function scorePct(value: number) {
  return `${Math.round(value * 100)}`;
}

export function when(iso: string | null | undefined) {
  if (!iso) return "—";
  const date = new Date(iso);
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

export function relativeTime(iso: string | null | undefined, now = Date.now()) {
  if (!iso) return "—";
  const diff = now - new Date(iso).getTime();
  if (!Number.isFinite(diff)) return "—";
  const abs = Math.abs(diff);
  const rtf = new Intl.RelativeTimeFormat("en", { numeric: "auto" });
  const minutes = Math.round(diff / 60_000);
  if (abs < 60_000) return "just now";
  if (abs < 3_600_000) return rtf.format(-minutes, "minute");
  const hours = Math.round(diff / 3_600_000);
  if (abs < 86_400_000) return rtf.format(-hours, "hour");
  const days = Math.round(diff / 86_400_000);
  if (abs < 30 * 86_400_000) return rtf.format(-days, "day");
  return when(iso);
}

export function actionLabel(action: Action) {
  return { accumulate: "Accumulate", watch: "Watch", reduce: "Reduce", avoid: "Avoid" }[action];
}

export function horizonLabel(horizon: Horizon) {
  return {
    tactical_1_3m: "Tactical · 1–3m",
    swing_3_12m: "Swing · 3–12m",
    position_1y_plus: "Position · 1y+",
  }[horizon];
}

export function ideaHref(ticker: string) {
  return `/idea/${encodeURIComponent(ticker)}`;
}
