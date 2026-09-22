from datetime import UTC, datetime, timedelta

from app.agents.scoring import clamp, quality_score, risk_score
from app.domain import Fundamentals, Profile, Quote, TickerIntel


def test_quality_prefers_high_roe_and_margins():
    strong = Fundamentals(
        ticker="AAA",
        roe=0.4,
        profit_margin=0.3,
        operating_margin=0.35,
        revenue_growth=0.2,
        debt_to_equity=0.3,
    )
    weak = Fundamentals(
        ticker="BBB",
        roe=0.02,
        profit_margin=0.01,
        operating_margin=0.02,
        revenue_growth=-0.1,
        debt_to_equity=3.5,
    )
    assert quality_score(strong) > quality_score(weak)
    assert 0 <= quality_score(strong) <= 1


def test_clamp():
    assert clamp(-2) == 0
    assert clamp(2) == 1
    assert clamp(0.4) == 0.4


def test_near_earnings_raises_event_risk():
    def intel(next_earnings: datetime | None) -> TickerIntel:
        return TickerIntel(
            ticker="AAPL",
            profile=Profile(ticker="AAPL", name="Apple", sector="Technology", industry="Hardware"),
            quote=Quote(
                ticker="AAPL",
                price=100.0,
                change_pct=0.0,
                as_of=datetime.now(UTC),
                source="test",
            ),
            fundamentals=Fundamentals(ticker="AAPL", beta=1.0),
            next_earnings=next_earnings,
        )

    base = risk_score(intel(None))
    near = risk_score(intel(datetime.now(UTC) + timedelta(days=4)))
    far = risk_score(intel(datetime.now(UTC) + timedelta(days=40)))
    assert near > base
    assert far == base
