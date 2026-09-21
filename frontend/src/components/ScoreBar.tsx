export function ScoreBar({
  label,
  value,
  invert = false,
  compact = false,
}: {
  label: string;
  value: number;
  invert?: boolean;
  compact?: boolean;
}) {
  const pct = Math.max(0, Math.min(100, Math.round(value * 100)));
  const good = invert ? value < 0.45 : value > 0.55;
  const bad = invert ? value > 0.65 : value < 0.4;
  const color = good ? "var(--success)" : bad ? "var(--danger)" : "var(--accent)";
  return (
    <div>
      <div className={`mb-1.5 flex items-center justify-between ${compact ? "text-[11px]" : "text-xs"}`}>
        <span className="text-muted">{label}</span>
        <span className="mono tabular font-medium text-fg-2">{pct}</span>
      </div>
      <div className="h-1.5 overflow-hidden rounded-full bg-surface-2" role="meter" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100} aria-label={label}>
        <div
          className="h-full rounded-full transition-[width] duration-500 ease-out"
          style={{ width: `${pct}%`, background: color }}
        />
      </div>
    </div>
  );
}
