import { useId } from "react";

export function Sparkline({
  values,
  width = 96,
  height = 32,
  strokeWidth = 1.6,
}: {
  values: number[];
  width?: number;
  height?: number;
  strokeWidth?: number;
}) {
  const gradientId = useId();
  if (values.length < 2) return <span className="text-muted-2">—</span>;

  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const pad = strokeWidth;
  const innerH = height - pad * 2;
  const pts = values.map((value, i) => {
    const x = (i / (values.length - 1)) * width;
    const y = pad + innerH - ((value - min) / span) * innerH;
    return [x, y] as const;
  });
  const line = pts.map(([x, y]) => `${x.toFixed(2)},${y.toFixed(2)}`).join(" ");
  const area = `M0,${height} L${line.replaceAll(" ", " L")} L${width},${height} Z`;
  const up = values[values.length - 1] >= values[0];
  const color = up ? "var(--success)" : "var(--danger)";
  const [lx, ly] = pts[pts.length - 1];

  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} className="overflow-visible" aria-hidden="true">
      <defs>
        <linearGradient id={gradientId} x1="0" x2="0" y1="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.28" />
          <stop offset="100%" stopColor={color} stopOpacity="0" />
        </linearGradient>
      </defs>
      <path d={area} fill={`url(#${gradientId})`} />
      <polyline fill="none" stroke={color} strokeWidth={strokeWidth} strokeLinejoin="round" strokeLinecap="round" points={line} />
      <circle cx={lx} cy={ly} r={strokeWidth + 0.6} fill={color} />
    </svg>
  );
}
