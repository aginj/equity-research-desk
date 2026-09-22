from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.agents.llm import LLMClient
from app.agents.scoring import build_scorecard
from app.domain import Horizon, Recommendation, Scorecard, Source, TickerIntel
from app.markets import MARKETS


class _ChiefDraft(BaseModel):
    action: Literal["accumulate", "watch", "reduce", "avoid"]
    conviction: float = Field(ge=0, le=1)
    horizon: Horizon
    thesis: str
    bull_case: str
    bear_case: str
    invalidation: str
    catalysts: list[str]
    risks: list[str]


def _sources(intel: TickerIntel) -> list[Source]:
    out: list[Source] = []
    for item in intel.news[:5]:
        out.append(
            Source(
                id=item.id,
                title=item.headline,
                publisher=item.publisher,
                url=item.url,
                published_at=item.published_at,
                kind="news",
            )
        )
    for item in intel.filings[:3]:
        out.append(
            Source(
                id=item.id,
                title=f"{item.form}: {item.description}",
                publisher=f"{intel.profile.exchange} filings",
                url=item.url,
                published_at=item.filed_at,
                kind="filing",
            )
        )
    out.append(
        Source(
            id=f"px-{intel.ticker}",
            title=(
                f"Last {intel.quote.source} quote {intel.quote.price:.2f} "
                f"{intel.quote.currency} ({intel.quote.change_pct:+.2f}%)"
            ),
            publisher=intel.quote.source,
            url=_quote_home(intel),
            published_at=intel.quote.as_of,
            kind="market",
        )
    )
    return out


def _quote_home(intel: TickerIntel) -> str:
    for spec in MARKETS.values():
        if spec.country_code == intel.profile.country and spec.exchange_code in {
            intel.profile.exchange,
            "US",
        }:
            return spec.quote_home
    return "https://www.sec.gov/"


def _horizon(intel: TickerIntel) -> Horizon:
    growth = intel.fundamentals.revenue_growth or 0
    if (intel.fundamentals.beta or 1) > 1.35 or abs(intel.quote.change_pct) > 2:
        return "tactical_1_3m"
    if growth > 0.12:
        return "position_1y_plus"
    return "swing_3_12m"


def _action_from_scores(card: Scorecard) -> tuple[str, float]:
    c = card.composite
    if c >= 0.64 and card.risk < 0.62:
        return "accumulate", min(0.92, 0.55 + (c - 0.5))
    if c <= 0.38 or card.risk > 0.78:
        return "avoid" if card.risk > 0.82 else "reduce", min(0.8, 0.45 + (0.5 - c))
    return "watch", 0.42 + abs(c - 0.5)


def _catalysts(intel: TickerIntel) -> list[str]:
    items = [e.headline for e in intel.events[:3]] or [n.headline for n in intel.news[:2]]
    if intel.next_earnings is not None:
        stamp = intel.next_earnings.date().isoformat()
        items = [f"Earnings {stamp}", *items]
    return items[:5]


def heuristic_recommendation(intel: TickerIntel) -> Recommendation:
    card = intel.scorecard or build_scorecard(intel)
    action, conviction = _action_from_scores(card)
    if intel.news_bias > 0:
        tone = "constructive"
    elif intel.news_bias < 0:
        tone = "defensive"
    else:
        tone = "balanced"
    thesis = (
        f"{intel.profile.name} screens {tone} on a {card.composite:.0%} composite. "
        f"Quality {card.fundamental_quality:.0%}, valuation {card.valuation_attractiveness:.0%}, "
        f"risk {card.risk:.0%}. {intel.narrative}".strip()
    )
    bull = (
        intel.news[0].headline
        if intel.news
        else "Franchise quality and existing cash-flow duration remain the bull case."
    )
    bear = (
        "Event tape and valuation leave limited room for disappointment."
        if card.risk > 0.5
        else "A growth or margin miss would compress the multiple."
    )
    return Recommendation(
        ticker=intel.ticker,
        name=intel.profile.name,
        sector=intel.profile.sector,
        action=action,  # type: ignore[arg-type]
        conviction=round(conviction, 3),
        horizon=_horizon(intel),
        thesis=thesis[:900],
        bull_case=str(bull)[:500],
        bear_case=bear[:500],
        invalidation=(
            "Thesis breaks if the next reported print contradicts the current quality/growth "
            "assumptions, or if cited event risk materializes."
        ),
        catalysts=_catalysts(intel),
        risks=[
            r
            for r in [
                "Multiple compression if growth decelerates.",
                "Policy or regulatory headlines in the news window.",
                "Factor/beta shock given realized volatility.",
            ]
        ],
        scores=card,
        sources=_sources(intel),
        quote=intel.quote,
        synthesis_mode="heuristic",
    )


class ChiefAnalyst:
    name = "chief_analyst"

    def __init__(self, llm: LLMClient) -> None:
        self.llm = llm

    async def run(self, intel: TickerIntel) -> Recommendation:
        baseline = heuristic_recommendation(intel)
        if not self.llm.enabled:
            return baseline

        evidence = {
            "ticker": intel.ticker,
            "name": intel.profile.name,
            "sector": intel.profile.sector,
            "quote": intel.quote.model_dump(mode="json"),
            "fundamentals": intel.fundamentals.model_dump(mode="json"),
            "scorecard": (intel.scorecard or baseline.scores).model_dump(),
            "news_bias": intel.news_bias,
            "filing_bias": intel.filing_bias,
            "narrative": intel.narrative,
            "events": [e.model_dump(mode="json") for e in intel.events[:6]],
            "news": [
                {"id": n.id, "headline": n.headline, "publisher": n.publisher}
                for n in intel.news[:6]
            ],
            "filings": [
                {"id": f.id, "form": f.form, "description": f.description}
                for f in intel.filings[:4]
            ],
        }
        prompt = (
            "Write a sourced research recommendation. Do not invent facts. "
            "Conviction is 0-1. Prefer watch when evidence is mixed. "
            "Invalidation must be a falsifiable condition.\n"
            f"Evidence:\n{evidence}"
        )
        draft = await self.llm.complete_json(prompt, _ChiefDraft)
        if draft is None:
            return baseline
        return baseline.model_copy(
            update={
                "action": draft.action,
                "conviction": draft.conviction,
                "horizon": draft.horizon,
                "thesis": draft.thesis,
                "bull_case": draft.bull_case,
                "bear_case": draft.bear_case,
                "invalidation": draft.invalidation,
                "catalysts": draft.catalysts[:5],
                "risks": draft.risks[:5],
                "synthesis_mode": "llm",
            }
        )
