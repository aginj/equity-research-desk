"""Transparent scoring when no LLM is configured, and as a numeric backbone for the LLM."""

from __future__ import annotations

import math
import re
from statistics import pstdev

from app.domain import (
    EventExtract,
    FilingItem,
    Fundamentals,
    NewsItem,
    Quote,
    Scorecard,
    TickerIntel,
)
from app.policy import clamp, composite_score

BULLISH = re.compile(
    r"\b(beat|beats|surge|accelerat|upgrade|record|buyback|expand|outperform|strong demand|"
    r"raised guidance|better than expected|capacity addition|resilient|compound)\b",
    re.I,
)
BEARISH = re.compile(
    r"\b(miss|cuts?|downgrade|probe|lawsuit|fraud|recall|layoff|weak(ness)?|slowdown|"
    r"export.?control|cost trend|guidance cut|disappoint|investigation|impairment)\b",
    re.I,
)
MATERIAL = re.compile(
    r"\b(8-k|10-q|10-k|earnings|guidance|fda|merger|acquisition|antitrust|export|"
    r"medicare|nII|outlook|downgrade|upgrade|buyback|dividend|bankruptcy)\b",
    re.I,
)


def _sentiment(text: str) -> float:
    score = 0.0
    score += 0.22 * len(BULLISH.findall(text))
    score -= 0.24 * len(BEARISH.findall(text))
    return clamp((score + 1) / 2) * 2 - 1


def _materiality(text: str) -> float:
    hits = len(MATERIAL.findall(text))
    return clamp(0.28 + 0.18 * hits)


def extract_events(intel: TickerIntel) -> list[EventExtract]:
    events: list[EventExtract] = []
    for item in intel.news:
        blob = f"{item.headline}. {item.summary}"
        events.append(
            EventExtract(
                ticker=intel.ticker,
                headline=item.headline,
                event_type="news",
                materiality=_materiality(blob),
                sentiment=_sentiment(blob),
                summary=item.summary or item.headline,
                source_ids=[item.id],
            )
        )
    for item in intel.filings:
        blob = f"{item.form} {item.description}"
        events.append(
            EventExtract(
                ticker=intel.ticker,
                headline=f"{item.form} filed",
                event_type="filing",
                materiality=0.72 if item.form in {"8-K", "10-K"} else 0.55,
                sentiment=_sentiment(blob) * 0.3,
                summary=item.description,
                source_ids=[item.id],
            )
        )
    events.sort(key=lambda e: e.materiality, reverse=True)
    return events[:8]


def news_bias(items: list[NewsItem]) -> float:
    if not items:
        return 0.0
    scores = [_sentiment(f"{n.headline}. {n.summary}") for n in items]
    return sum(scores) / len(scores)


def filing_bias(items: list[FilingItem]) -> float:
    if not items:
        return 0.0
    return sum(_sentiment(f"{f.form} {f.description}") for f in items) / len(items)


def momentum_score(intel: TickerIntel) -> float:
    closes = (intel.candle.closes if intel.candle else []) or []
    if len(closes) >= 5:
        ret = (closes[-1] / closes[0]) - 1
        log_returns = [
            math.log(max(closes[i] / closes[i - 1], 1e-6)) for i in range(1, len(closes))
        ]
        vol = pstdev(log_returns)
        raw = 0.5 + ret * 2.2 - min(vol * 8, 0.25)
        return clamp(raw)
    return clamp(0.5 + intel.quote.change_pct / 40)


def quality_score(fund: Fundamentals) -> float:
    parts: list[float] = []
    if fund.roe is not None:
        parts.append(clamp(0.35 + fund.roe * 0.6))
    if fund.profit_margin is not None:
        parts.append(clamp(0.35 + fund.profit_margin * 1.4))
    if fund.operating_margin is not None:
        parts.append(clamp(0.35 + fund.operating_margin * 1.2))
    if fund.revenue_growth is not None:
        parts.append(clamp(0.45 + fund.revenue_growth * 0.9))
    if fund.debt_to_equity is not None:
        parts.append(clamp(1.05 - min(fund.debt_to_equity, 4) / 5))
    return sum(parts) / len(parts) if parts else 0.45


def valuation_score(fund: Fundamentals, quote: Quote) -> float:
    pe = fund.forward_pe or fund.pe or quote.pe
    if pe is None or pe <= 0:
        return 0.45
    # Lower PE is more attractive, but mega-growth names should not be auto-punished to zero.
    attractive = clamp((28 - min(pe, 55)) / 28)
    growth = fund.eps_growth or fund.revenue_growth or 0.0
    return clamp(0.55 * attractive + 0.45 * clamp(0.4 + growth))


def risk_score(intel: TickerIntel) -> float:
    fund = intel.fundamentals
    beta = fund.beta or 1.0
    event_risk = 0.0
    headlines = " ".join(n.headline for n in intel.news)
    filing_text = " ".join(f.description for f in intel.filings)
    blob = f"{headlines} {filing_text}"
    if BEARISH.search(blob):
        event_risk += 0.18
    if re.search(r"lawsuit|probe|export|medicare|impairment", blob, re.I):
        event_risk += 0.16
    vol = 0.0
    closes = intel.candle.closes if intel.candle else []
    if len(closes) > 5:
        vol = min(pstdev(closes) / (sum(closes) / len(closes)), 0.12) * 3
    return clamp(0.22 + (beta - 1) * 0.18 + event_risk + vol)


def source_quality(intel: TickerIntel) -> float:
    n = len(intel.news) + len(intel.filings)
    live = sum(1 for x in intel.news if x.source != "demo") + sum(
        1 for x in intel.filings if not (x.accession or "").startswith("demo")
    )
    diversity = len({x.publisher for x in intel.news})
    return clamp(0.2 + 0.08 * min(n, 6) + 0.06 * min(diversity, 4) + 0.04 * min(live, 5))


def build_scorecard(intel: TickerIntel) -> Scorecard:
    card = Scorecard(
        news_materiality=clamp(0.5 + intel.news_bias * 0.35 + (0.08 if intel.events else 0)),
        fundamental_quality=quality_score(intel.fundamentals),
        valuation_attractiveness=valuation_score(intel.fundamentals, intel.quote),
        momentum=momentum_score(intel),
        risk=risk_score(intel),
        source_quality=source_quality(intel),
        composite=0.5,
    )
    card.composite = clamp(composite_score(card))
    return card
