"use client";

import { IconChevronDown } from "@/components/icons";
import { useMarket } from "@/components/WorkspaceProvider";
import { Skeleton, cx } from "@/components/ui";

function Select({
  value,
  onChange,
  children,
  label,
  className,
}: {
  value: string;
  onChange: (value: string) => void;
  children: React.ReactNode;
  label: string;
  className?: string;
}) {
  return (
    <label className={cx("relative block", className)}>
      <span className="sr-only">{label}</span>
      <select
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="h-9 w-full appearance-none rounded-xl border border-border bg-surface pl-3 pr-8 text-xs font-medium text-fg outline-none transition hover:bg-surface-hover focus-visible:border-accent"
      >
        {children}
      </select>
      <IconChevronDown size={14} className="pointer-events-none absolute right-2.5 top-1/2 -translate-y-1/2 text-muted" />
    </label>
  );
}

export function MarketSwitcher({ compact = false }: { compact?: boolean }) {
  const { catalog, market, setMarketId, loading, error } = useMarket();

  if (!catalog || !market) {
    if (loading) {
      return compact ? <Skeleton className="h-9 w-40" /> : <Skeleton className="h-20 w-full" />;
    }
    if (compact) return null;
    return <p className="text-xs text-danger">{error ? `Venues unavailable: ${error}` : "Venues unavailable."}</p>;
  }

  const countries = catalog.countries;
  const activeMarket = market;
  const country = countries.find((item) => item.code === activeMarket.country_code) ?? countries[0];
  const venues = country?.markets ?? [];

  async function onCountry(code: string) {
    const next = countries.find((item) => item.code === code);
    const pick = next?.markets.find((item) => item.id === activeMarket.id) ?? next?.markets[0];
    if (pick) await setMarketId(pick.id);
  }

  return (
    <div className={compact ? "flex items-center gap-2" : "space-y-3"}>
      {!compact ? (
        <div className="grid gap-3 sm:grid-cols-2">
          <div>
            <div className="mb-1.5 text-xs font-medium text-muted">Country</div>
            <Select label="Country" value={activeMarket.country_code} onChange={onCountry}>
              {countries.map((item) => (
                <option key={item.code} value={item.code}>
                  {item.name}
                </option>
              ))}
            </Select>
          </div>
          <div>
            <div className="mb-1.5 text-xs font-medium text-muted">Exchange</div>
            <Select label="Exchange" value={activeMarket.id} onChange={(id) => void setMarketId(id)}>
              {venues.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.exchange_code} — {item.exchange}
                </option>
              ))}
            </Select>
          </div>
        </div>
      ) : (
        <>
          <Select label="Country" value={activeMarket.country_code} onChange={onCountry} className="w-36">
            {countries.map((item) => (
              <option key={item.code} value={item.code}>
                {item.name}
              </option>
            ))}
          </Select>
          <Select label="Exchange" value={activeMarket.id} onChange={(id) => void setMarketId(id)} className="w-28">
            {venues.map((item) => (
              <option key={item.id} value={item.id}>
                {item.exchange_code}
              </option>
            ))}
          </Select>
        </>
      )}
      {!compact ? (
        <p className="text-xs leading-relaxed text-muted">
          <span className="mono text-fg-2">{activeMarket.currency}</span> · {activeMarket.timezone} ·{" "}
          {activeMarket.filings_label}. {activeMarket.symbol_hint}.
        </p>
      ) : null}
      {error ? <p className="text-xs text-danger">{error}</p> : null}
    </div>
  );
}
