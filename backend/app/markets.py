"""Country and exchange catalog. The desk is venue-scoped, not US-only."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class MarketSpec:
    id: str
    country_code: str
    country: str
    exchange_code: str
    exchange: str
    currency: str
    timezone: str
    locale: str
    symbol_hint: str
    filings: Literal["edgar", "none"]
    filings_label: str
    min_price: float
    quote_home: str
    default_universe: tuple[str, ...]

    @property
    def label(self) -> str:
        return f"{self.country} · {self.exchange_code}"


MARKETS: dict[str, MarketSpec] = {
    "us": MarketSpec(
        id="us",
        country_code="US",
        country="United States",
        exchange_code="US",
        exchange="NYSE & Nasdaq",
        currency="USD",
        timezone="America/New_York",
        locale="en-US",
        symbol_hint="Unprefixed US tickers, e.g. AAPL, JPM",
        filings="edgar",
        filings_label="SEC EDGAR",
        min_price=8.0,
        quote_home="https://www.sec.gov/",
        default_universe=(
            "AAPL",
            "MSFT",
            "NVDA",
            "AMZN",
            "GOOGL",
            "META",
            "AVGO",
            "LLY",
            "JPM",
            "V",
            "UNH",
            "XOM",
            "CAT",
            "HD",
            "COST",
            "WMT",
            "PG",
            "JNJ",
            "GE",
            "GS",
        ),
    ),
    "in-nse": MarketSpec(
        id="in-nse",
        country_code="IN",
        country="India",
        exchange_code="NSE",
        exchange="National Stock Exchange of India",
        currency="INR",
        timezone="Asia/Kolkata",
        locale="en-IN",
        symbol_hint="NSE suffixes, e.g. RELIANCE.NS, TCS.NS",
        filings="none",
        filings_label="NSE disclosures",
        min_price=20.0,
        quote_home="https://www.nseindia.com/",
        default_universe=(
            "RELIANCE.NS",
            "TCS.NS",
            "HDFCBANK.NS",
            "INFY.NS",
            "ICICIBANK.NS",
            "HINDUNILVR.NS",
            "SBIN.NS",
            "BHARTIARTL.NS",
            "ITC.NS",
            "LT.NS",
            "AXISBANK.NS",
            "ASIANPAINT.NS",
        ),
    ),
    "in-bse": MarketSpec(
        id="in-bse",
        country_code="IN",
        country="India",
        exchange_code="BSE",
        exchange="BSE (Bombay Stock Exchange)",
        currency="INR",
        timezone="Asia/Kolkata",
        locale="en-IN",
        symbol_hint="BSE suffixes, e.g. RELIANCE.BO, TCS.BO",
        filings="none",
        filings_label="BSE filings",
        min_price=10.0,
        quote_home="https://www.bseindia.com/",
        default_universe=(
            "RELIANCE.BO",
            "TCS.BO",
            "HDFCBANK.BO",
            "INFY.BO",
            "ICICIBANK.BO",
            "SBIN.BO",
            "ITC.BO",
            "LT.BO",
        ),
    ),
    "uk-lse": MarketSpec(
        id="uk-lse",
        country_code="GB",
        country="United Kingdom",
        exchange_code="LSE",
        exchange="London Stock Exchange",
        currency="GBP",
        timezone="Europe/London",
        locale="en-GB",
        symbol_hint="LSE suffixes, e.g. AZN.L, HSBA.L",
        filings="none",
        filings_label="Companies House / RNS",
        min_price=0.5,
        quote_home="https://www.londonstockexchange.com/",
        default_universe=("AZN.L", "SHEL.L", "HSBA.L", "ULVR.L", "BP.L", "GSK.L", "DGE.L", "RIO.L"),
    ),
    "jp-tse": MarketSpec(
        id="jp-tse",
        country_code="JP",
        country="Japan",
        exchange_code="TSE",
        exchange="Tokyo Stock Exchange",
        currency="JPY",
        timezone="Asia/Tokyo",
        locale="ja-JP",
        symbol_hint="TSE codes, e.g. 7203.T (Toyota)",
        filings="none",
        filings_label="TDnet",
        min_price=50.0,
        quote_home="https://www.jpx.co.jp/",
        default_universe=("7203.T", "6758.T", "9984.T", "8306.T", "6861.T", "4063.T"),
    ),
    "hk-hkex": MarketSpec(
        id="hk-hkex",
        country_code="HK",
        country="Hong Kong",
        exchange_code="HKEX",
        exchange="Hong Kong Exchanges",
        currency="HKD",
        timezone="Asia/Hong_Kong",
        locale="en-HK",
        symbol_hint="HKEX codes, e.g. 700.HK (Tencent)",
        filings="none",
        filings_label="HKEX filings",
        min_price=1.0,
        quote_home="https://www.hkex.com.hk/",
        default_universe=("700.HK", "9988.HK", "1299.HK", "5.HK", "939.HK", "3690.HK"),
    ),
    "de-xetr": MarketSpec(
        id="de-xetr",
        country_code="DE",
        country="Germany",
        exchange_code="XETR",
        exchange="Xetra",
        currency="EUR",
        timezone="Europe/Berlin",
        locale="de-DE",
        symbol_hint="Xetra suffixes, e.g. SAP.DE",
        filings="none",
        filings_label="Bundesanzeiger",
        min_price=1.0,
        quote_home="https://www.xetra.com/",
        default_universe=("SAP.DE", "SIE.DE", "ALV.DE", "DTE.DE", "BMW.DE", "MUV2.DE"),
    ),
    "ca-tsx": MarketSpec(
        id="ca-tsx",
        country_code="CA",
        country="Canada",
        exchange_code="TSX",
        exchange="Toronto Stock Exchange",
        currency="CAD",
        timezone="America/Toronto",
        locale="en-CA",
        symbol_hint="TSX suffixes, e.g. RY.TO",
        filings="none",
        filings_label="SEDAR+",
        min_price=1.0,
        quote_home="https://www.tsx.com/",
        default_universe=("RY.TO", "TD.TO", "SHOP.TO", "ENB.TO", "CNQ.TO", "BMO.TO"),
    ),
    "au-asx": MarketSpec(
        id="au-asx",
        country_code="AU",
        country="Australia",
        exchange_code="ASX",
        exchange="Australian Securities Exchange",
        currency="AUD",
        timezone="Australia/Sydney",
        locale="en-AU",
        symbol_hint="ASX suffixes, e.g. BHP.AX",
        filings="none",
        filings_label="ASX announcements",
        min_price=0.5,
        quote_home="https://www.asx.com.au/",
        default_universe=("BHP.AX", "CBA.AX", "CSL.AX", "NAB.AX", "WES.AX", "WOW.AX"),
    ),
    "fr-epa": MarketSpec(
        id="fr-epa",
        country_code="FR",
        country="France",
        exchange_code="EPA",
        exchange="Euronext Paris",
        currency="EUR",
        timezone="Europe/Paris",
        locale="fr-FR",
        symbol_hint="Paris suffixes, e.g. MC.PA",
        filings="none",
        filings_label="AMF filings",
        min_price=1.0,
        quote_home="https://www.euronext.com/",
        default_universe=("MC.PA", "OR.PA", "TTE.PA", "SAN.PA", "AIR.PA", "BN.PA"),
    ),
    "nl-ams": MarketSpec(
        id="nl-ams",
        country_code="NL",
        country="Netherlands",
        exchange_code="AMS",
        exchange="Euronext Amsterdam",
        currency="EUR",
        timezone="Europe/Amsterdam",
        locale="nl-NL",
        symbol_hint="Amsterdam suffixes, e.g. ASML.AS",
        filings="none",
        filings_label="AFM filings",
        min_price=1.0,
        quote_home="https://www.euronext.com/",
        default_universe=("ASML.AS", "INGA.AS", "AD.AS", "PHIA.AS"),
    ),
    "kr-krx": MarketSpec(
        id="kr-krx",
        country_code="KR",
        country="South Korea",
        exchange_code="KRX",
        exchange="Korea Exchange",
        currency="KRW",
        timezone="Asia/Seoul",
        locale="ko-KR",
        symbol_hint="KRX codes, e.g. 005930.KS (Samsung)",
        filings="none",
        filings_label="DART",
        min_price=500.0,
        quote_home="https://www.krx.co.kr/",
        default_universe=("005930.KS", "000660.KS", "035420.KS", "005380.KS"),
    ),
    "br-b3": MarketSpec(
        id="br-b3",
        country_code="BR",
        country="Brazil",
        exchange_code="B3",
        exchange="B3 (Brasil Bolsa Balcão)",
        currency="BRL",
        timezone="America/Sao_Paulo",
        locale="pt-BR",
        symbol_hint="B3 suffixes, e.g. PETR4.SA",
        filings="none",
        filings_label="CVM filings",
        min_price=1.0,
        quote_home="https://www.b3.com.br/",
        default_universe=("PETR4.SA", "VALE3.SA", "ITUB4.SA", "BBDC4.SA"),
    ),
    "sg-sgx": MarketSpec(
        id="sg-sgx",
        country_code="SG",
        country="Singapore",
        exchange_code="SGX",
        exchange="Singapore Exchange",
        currency="SGD",
        timezone="Asia/Singapore",
        locale="en-SG",
        symbol_hint="SGX suffixes, e.g. D05.SI (DBS)",
        filings="none",
        filings_label="SGXNet",
        min_price=0.2,
        quote_home="https://www.sgx.com/",
        default_universe=("D05.SI", "O39.SI", "Z74.SI", "U11.SI"),
    ),
    "tw-twse": MarketSpec(
        id="tw-twse",
        country_code="TW",
        country="Taiwan",
        exchange_code="TWSE",
        exchange="Taiwan Stock Exchange",
        currency="TWD",
        timezone="Asia/Taipei",
        locale="zh-TW",
        symbol_hint="TWSE codes, e.g. 2330.TW (TSMC)",
        filings="none",
        filings_label="TWSE MOPS",
        min_price=10.0,
        quote_home="https://www.twse.com.tw/",
        default_universe=("2330.TW", "2317.TW", "2454.TW"),
    ),
    "cn-sse": MarketSpec(
        id="cn-sse",
        country_code="CN",
        country="China",
        exchange_code="SSE",
        exchange="Shanghai Stock Exchange",
        currency="CNY",
        timezone="Asia/Shanghai",
        locale="zh-CN",
        symbol_hint="SSE codes, e.g. 600519.SS",
        filings="none",
        filings_label="SSE filings",
        min_price=2.0,
        quote_home="https://www.sse.com.cn/",
        default_universe=("600519.SS", "601318.SS", "600036.SS"),
    ),
    "ch-six": MarketSpec(
        id="ch-six",
        country_code="CH",
        country="Switzerland",
        exchange_code="SIX",
        exchange="SIX Swiss Exchange",
        currency="CHF",
        timezone="Europe/Zurich",
        locale="de-CH",
        symbol_hint="SIX suffixes, e.g. NESN.SW",
        filings="none",
        filings_label="SIX filings",
        min_price=1.0,
        quote_home="https://www.six-group.com/",
        default_universe=("NESN.SW", "ROG.SW", "NOVN.SW", "UBSG.SW"),
    ),
}

DEFAULT_MARKET_ID = "us"
_PINNED_COUNTRIES = ("US", "IN")


def get_market(market_id: str | None) -> MarketSpec:
    if market_id and market_id in MARKETS:
        return MARKETS[market_id]
    return MARKETS[DEFAULT_MARKET_ID]


def normalize_ticker(raw: str) -> str:
    return raw.strip().upper()


def market_payload(spec: MarketSpec) -> dict:
    return {
        "id": spec.id,
        "country_code": spec.country_code,
        "country": spec.country,
        "exchange_code": spec.exchange_code,
        "exchange": spec.exchange,
        "currency": spec.currency,
        "timezone": spec.timezone,
        "locale": spec.locale,
        "symbol_hint": spec.symbol_hint,
        "filings": spec.filings,
        "filings_label": spec.filings_label,
        "min_price": spec.min_price,
        "label": spec.label,
        "quote_home": spec.quote_home,
    }


def catalog_payload() -> dict:
    countries: dict[str, dict] = {}
    for spec in MARKETS.values():
        bucket = countries.setdefault(
            spec.country_code,
            {"code": spec.country_code, "name": spec.country, "markets": []},
        )
        bucket["markets"].append(market_payload(spec))

    def sort_key(item: dict) -> tuple:
        code = item["code"]
        pin = _PINNED_COUNTRIES.index(code) if code in _PINNED_COUNTRIES else 99
        return (pin, item["name"])

    return {"countries": sorted(countries.values(), key=sort_key)}
