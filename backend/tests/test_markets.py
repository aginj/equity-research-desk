from datetime import UTC, datetime

from app.domain import Quote, Recommendation, Scorecard
from app.markets import MARKETS, catalog_payload, get_market, normalize_ticker, presets_for
from app.policy import apply_policy, clamp, composite_score


def test_india_venues_exist():
    assert "in-nse" in MARKETS
    assert "in-bse" in MARKETS
    nse = get_market("in-nse")
    assert nse.currency == "INR"
    assert nse.exchange_code == "NSE"
    assert "RELIANCE.NS" in nse.default_universe
    bse = get_market("in-bse")
    assert "RELIANCE.BO" in bse.default_universe


def test_catalog_pins_us_and_india():
    countries = catalog_payload()["countries"]
    assert countries[0]["code"] == "US"
    assert countries[1]["code"] == "IN"
    india = countries[1]
    codes = {m["exchange_code"] for m in india["markets"]}
    assert codes == {"NSE", "BSE"}


def test_normalize_ticker():
    assert normalize_ticker(" reliance.ns ") == "RELIANCE.NS"


def test_index_presets_cover_core_venues():
    us = presets_for("us")
    assert any(row["id"] == "default" and "S&P" in str(row["label"]) for row in us)
    assert presets_for("in-nse")[0]["label"] == "Nifty 50 core"
    assert presets_for("uk-lse")[0]["label"] == "FTSE 100 core"


def _rec(ticker: str, price: float) -> Recommendation:
    card = Scorecard(
        news_materiality=0.6,
        fundamental_quality=0.7,
        valuation_attractiveness=0.6,
        momentum=0.55,
        risk=0.3,
        source_quality=0.7,
        composite=0.6,
    )
    card.composite = clamp(composite_score(card))
    return Recommendation(
        ticker=ticker,
        name=ticker,
        sector="Energy",
        action="accumulate",
        conviction=0.9,
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
                "url": "https://www.nseindia.com/",
                "kind": "internal",
            },
            {
                "id": "s2",
                "title": "Filing",
                "publisher": "NSE",
                "url": "https://www.nseindia.com/",
                "kind": "filing",
            },
            {
                "id": "s3",
                "title": "News",
                "publisher": "Mint",
                "url": "https://www.livemint.com/",
                "kind": "news",
            },
        ],
        quote=Quote(
            ticker=ticker,
            price=price,
            change_pct=0.4,
            as_of=datetime.now(UTC),
            source="test",
            currency="INR",
        ),
    )


def test_nse_penny_threshold_uses_rupees():
    rec = _rec("JUNK.NS", 5.0)
    out = apply_policy([rec], "balanced", get_market("in-nse"))
    assert out[0].action == "avoid"
    assert any("INR" in n for n in out[0].policy_notes)
