"""Deterministic risk policy. Agents propose; this layer disposes."""

from __future__ import annotations

from dataclasses import dataclass

from app.domain import Recommendation, RiskAppetite, Scorecard
from app.markets import MarketSpec, get_market


@dataclass(frozen=True)
class PolicyProfile:
    name: RiskAppetite
    min_conviction_accumulate: float
    min_quality: float
    max_risk_for_accumulate: float
    max_accumulate: int
    max_per_sector: int
    min_price: float
    min_sources_accumulate: int
    min_source_quality: float


PROFILES: dict[RiskAppetite, PolicyProfile] = {
    "conservative": PolicyProfile(
        name="conservative",
        min_conviction_accumulate=0.72,
        min_quality=0.58,
        max_risk_for_accumulate=0.45,
        max_accumulate=4,
        max_per_sector=1,
        min_price=15.0,
        min_sources_accumulate=3,
        min_source_quality=0.55,
    ),
    "balanced": PolicyProfile(
        name="balanced",
        min_conviction_accumulate=0.58,
        min_quality=0.45,
        max_risk_for_accumulate=0.62,
        max_accumulate=6,
        max_per_sector=2,
        min_price=8.0,
        min_sources_accumulate=2,
        min_source_quality=0.4,
    ),
    "aggressive": PolicyProfile(
        name="aggressive",
        min_conviction_accumulate=0.48,
        min_quality=0.32,
        max_risk_for_accumulate=0.78,
        max_accumulate=8,
        max_per_sector=3,
        min_price=5.0,
        min_sources_accumulate=1,
        min_source_quality=0.28,
    ),
}


def composite_score(card: Scorecard) -> float:
    return round(
        0.22 * card.news_materiality
        + 0.22 * card.fundamental_quality
        + 0.18 * card.valuation_attractiveness
        + 0.16 * card.momentum
        + 0.12 * card.source_quality
        - 0.18 * card.risk
        + 0.18,
        4,
    )


def clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, value))


def apply_policy(
    recs: list[Recommendation],
    appetite: RiskAppetite,
    market: MarketSpec | None = None,
) -> list[Recommendation]:
    profile = PROFILES[appetite]
    venue = market or get_market("us")
    min_price = venue.min_price
    currency = venue.currency
    sector_counts: dict[str, int] = {}
    accumulate_count = 0
    adjusted: list[Recommendation] = []

    ranked = sorted(recs, key=lambda r: (r.conviction, r.scores.composite), reverse=True)

    for rec in ranked:
        notes = list(rec.policy_notes)
        action = rec.action
        conviction = rec.conviction

        if rec.quote.price < min_price:
            action = "avoid"
            notes.append(
                f"Price {rec.quote.price:.2f} {currency} below desk minimum "
                f"{min_price:.0f} {currency}."
            )

        if rec.scores.fundamental_quality < profile.min_quality and action == "accumulate":
            action = "watch"
            notes.append("Fundamental quality below appetite floor — demoted to watch.")

        if rec.scores.risk > profile.max_risk_for_accumulate and action == "accumulate":
            action = "watch"
            notes.append("Event/volatility risk above appetite ceiling — demoted to watch.")

        if rec.scores.source_quality < profile.min_source_quality and action == "accumulate":
            action = "watch"
            notes.append("Insufficient source quality for an accumulate rating.")

        source_count = len(rec.sources)
        if source_count < profile.min_sources_accumulate and action == "accumulate":
            action = "watch"
            notes.append(
                f"Only {source_count} cited source(s); {profile.min_sources_accumulate} required."
            )

        if conviction < profile.min_conviction_accumulate and action == "accumulate":
            action = "watch"
            notes.append("Conviction below appetite threshold.")

        if action == "accumulate":
            sector_key = rec.sector or "Unknown"
            used = sector_counts.get(sector_key, 0)
            if used >= profile.max_per_sector:
                action = "watch"
                notes.append(f"Sector cap reached for {sector_key}.")
            elif accumulate_count >= profile.max_accumulate:
                action = "watch"
                notes.append("Book is full for this appetite — excess names held as watch.")
            else:
                sector_counts[sector_key] = used + 1
                accumulate_count += 1

        adjusted.append(rec.model_copy(update={"action": action, "policy_notes": notes}))

    order = {"accumulate": 0, "watch": 1, "reduce": 2, "avoid": 3}
    return sorted(adjusted, key=lambda r: (order[r.action], -r.conviction, r.ticker))
