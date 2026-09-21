from app.agents.scoring import clamp, quality_score
from app.domain import Fundamentals


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
