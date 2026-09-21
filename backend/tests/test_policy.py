from datetime import UTC, datetime

from app.domain import Quote, Recommendation, Scorecard
from app.policy import PROFILES, apply_policy, clamp, composite_score


def _rec(
    ticker: str, action: str, conviction: float, sector: str, price: float, **scores
) -> Recommendation:
    card = Scorecard(
        news_materiality=scores.get("news", 0.6),
        fundamental_quality=scores.get("quality", 0.7),
        valuation_attractiveness=scores.get("value", 0.6),
        momentum=scores.get("mom", 0.55),
        risk=scores.get("risk", 0.3),
        source_quality=scores.get("src", 0.7),
        composite=0.6,
    )
    card.composite = clamp(composite_score(card))
    return Recommendation(
        ticker=ticker,
        name=ticker,
        sector=sector,
        action=action,  # type: ignore[arg-type]
        conviction=conviction,
        horizon="swing_3_12m",
        thesis="Quality compounder with sourced news support.",
        bull_case="Franchise continues to compound.",
        bear_case="Multiple compresses on a growth miss.",
        invalidation="Breaks if the next print shows deteriorating margins.",
        catalysts=["Earnings"],
        risks=["Valuation"],
        scores=card,
        sources=[
            {
                "id": "s1",
                "title": "Note",
                "publisher": "Desk",
                "url": "https://www.sec.gov/",
                "kind": "internal",
            },
            {
                "id": "s2",
                "title": "Filing",
                "publisher": "SEC",
                "url": "https://www.sec.gov/",
                "kind": "filing",
            },
            {
                "id": "s3",
                "title": "News",
                "publisher": "Reuters",
                "url": "https://www.reuters.com/",
                "kind": "news",
            },
        ],
        quote=Quote(
            ticker=ticker,
            price=price,
            change_pct=0.4,
            as_of=datetime.now(UTC),
            source="test",
        ),
    )


def test_conservative_caps_sector_and_count():
    recs = [
        _rec("AAPL", "accumulate", 0.9, "Information Technology", 200),
        _rec("MSFT", "accumulate", 0.88, "Information Technology", 400),
        _rec("NVDA", "accumulate", 0.86, "Information Technology", 180),
        _rec("JPM", "accumulate", 0.84, "Financials", 220),
        _rec("XOM", "accumulate", 0.83, "Energy", 110),
        _rec("UNH", "accumulate", 0.82, "Health Care", 300),
    ]
    out = apply_policy(recs, "conservative")
    acc = [r for r in out if r.action == "accumulate"]
    assert len(acc) <= PROFILES["conservative"].max_accumulate
    tech = [r for r in acc if r.sector == "Information Technology"]
    assert len(tech) <= 1


def test_penny_names_are_avoided():
    rec = _rec("JUNK", "accumulate", 0.95, "Unknown", 2.0)
    out = apply_policy([rec], "balanced")
    assert out[0].action == "avoid"
    assert any("below desk minimum" in n for n in out[0].policy_notes)


def test_low_conviction_demoted():
    rec = _rec("XYZ", "accumulate", 0.2, "Financials", 50, quality=0.8, risk=0.2, src=0.8)
    out = apply_policy([rec], "balanced")
    assert out[0].action == "watch"
