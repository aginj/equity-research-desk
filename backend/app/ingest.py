"""Data hub: fan-in licensed APIs, then fill gaps from the demo book so the desk never goes blank.

Every upstream call goes through :meth:`DataHub._get_json`, which applies a bounded retry with
exponential backoff for transient failures (429 / 5xx / transport errors) and logs the outcome.
Upstream failures degrade to ``None``/``[]`` so a single vendor outage cannot fail a desk run.
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from app.config import Settings, get_settings
from app.data import demo
from app.domain import Candle, FilingItem, Fundamentals, NewsItem, Profile, Quote, TickerIntel
from app.markets import MarketSpec, get_market

logger = logging.getLogger(__name__)

_RETRY_STATUSES = {429, 500, 502, 503, 504}
_CIK_CACHE_TTL_SECONDS = 6 * 60 * 60
_CIK_FAILURE_RETRY_SECONDS = 10 * 60
_SEC_WANTED_FORMS = frozenset({"8-K", "10-Q", "10-K", "6-K", "20-F"})


class DataHub:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._cik_map: dict[str, str] | None = None
        self._cik_loaded_at: float = 0.0
        self._cik_lock = asyncio.Lock()

    # ------------------------------------------------------------------ public

    async def load_universe(
        self, tickers: list[str], market: MarketSpec | None = None
    ) -> list[TickerIntel]:
        venue = market or get_market("us")
        unique = [t.upper() for t in dict.fromkeys(tickers)]
        limits = httpx.Limits(max_connections=16, max_keepalive_connections=8)
        async with httpx.AsyncClient(
            timeout=self.settings.http_timeout_seconds,
            limits=limits,
            headers={"User-Agent": self.settings.sec_user_agent},
        ) as client:
            semaphore = asyncio.Semaphore(self.settings.ingest_concurrency)

            async def bound(ticker: str) -> TickerIntel:
                async with semaphore:
                    return await self._load_one(client, ticker, venue)

            loaded = await asyncio.gather(*[bound(t) for t in unique])
        return list(loaded)

    # ---------------------------------------------------------------- internals

    async def _load_one(
        self, client: httpx.AsyncClient, ticker: str, market: MarketSpec
    ) -> TickerIntel:
        if self.settings.force_demo_data:
            return self._from_demo(ticker, market)

        profile, quote, fundamentals, news, filings, candle = await asyncio.gather(
            self._profile(client, ticker),
            self._quote(client, ticker, market),
            self._fundamentals(client, ticker),
            self._news(client, ticker),
            self._filings(client, ticker, market),
            self._candle(client, ticker),
        )
        demo_row = self._from_demo(ticker, market)
        return TickerIntel(
            ticker=ticker,
            profile=profile or demo_row.profile,
            quote=quote or demo_row.quote,
            fundamentals=fundamentals or demo_row.fundamentals,
            news=news or demo_row.news,
            filings=filings or demo_row.filings,
            candle=candle or demo_row.candle,
        )

    def _from_demo(self, ticker: str, market: MarketSpec) -> TickerIntel:
        profile = demo.PROFILES.get(ticker) or Profile(
            ticker=ticker,
            name=ticker,
            sector="Unknown",
            industry="Unknown",
            country=market.country_code,
            exchange=market.exchange_code,
            description="No profile on file. Live APIs may still enrich this name.",
        )
        quote = demo.QUOTES.get(ticker) or Quote(
            ticker=ticker,
            price=100.0,
            change_pct=0.0,
            as_of=datetime.now(UTC),
            source="demo-fallback",
            currency=market.currency,
        )
        fundamentals = demo.FUNDAMENTALS.get(ticker) or Fundamentals(ticker=ticker)
        news = [item for item in demo.NEWS if item.ticker == ticker]
        filings = [item for item in demo.FILINGS if item.ticker == ticker]
        return TickerIntel(
            ticker=ticker,
            profile=profile,
            quote=quote,
            fundamentals=fundamentals,
            news=news,
            filings=filings,
            candle=demo.candle_for(ticker),
        )

    async def _get_json(
        self,
        client: httpx.AsyncClient,
        url: str,
        *,
        label: str,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        retries: int = 2,
    ) -> Any | None:
        """GET ``url`` and decode JSON, retrying transient failures. Returns None on failure."""
        if "finnhub.io" in url and self.settings.finnhub_api_key:
            # Header auth keeps the key out of URLs, proxies, and access logs.
            headers = {**(headers or {}), "X-Finnhub-Token": self.settings.finnhub_api_key}
        delay = 0.5
        for attempt in range(retries + 1):
            try:
                response = await client.get(url, params=params, headers=headers)
                if response.status_code in _RETRY_STATUSES and attempt < retries:
                    retry_after = response.headers.get("Retry-After")
                    wait = float(retry_after) if retry_after and retry_after.isdigit() else delay
                    logger.info(
                        "%s returned %s; retrying in %.1fs", label, response.status_code, wait
                    )
                    await asyncio.sleep(wait)
                    delay *= 2
                    continue
                if response.status_code >= 400:
                    logger.warning(
                        "%s failed with HTTP %s",
                        label,
                        response.status_code,
                        extra={"url": str(response.url.copy_with(query=None))},
                    )
                    return None
                return response.json()
            except (httpx.TransportError, httpx.TimeoutException) as exc:
                if attempt < retries:
                    logger.info("%s transport error (%s); retrying", label, type(exc).__name__)
                    await asyncio.sleep(delay)
                    delay *= 2
                    continue
                logger.warning("%s failed after retries: %s", label, exc)
                return None
            except ValueError as exc:  # invalid JSON
                logger.warning("%s returned invalid JSON: %s", label, exc)
                return None
        return None

    # --------------------------------------------------------------- providers

    async def _profile(self, client: httpx.AsyncClient, ticker: str) -> Profile | None:
        key = self.settings.finnhub_api_key
        if not key:
            return None
        data = await self._get_json(
            client,
            "https://finnhub.io/api/v1/stock/profile2",
            label=f"finnhub profile {ticker}",
            params={"symbol": ticker},
        )
        if not isinstance(data, dict) or not data.get("name"):
            return None
        return Profile(
            ticker=ticker,
            name=data.get("name") or ticker,
            sector=data.get("finnhubIndustry") or "Unknown",
            industry=data.get("finnhubIndustry") or "Unknown",
            country=data.get("country") or "US",
            exchange=data.get("exchange") or "US",
            ipo=data.get("ipo"),
            description=data.get("name") or "",
        )

    async def _quote(
        self, client: httpx.AsyncClient, ticker: str, market: MarketSpec
    ) -> Quote | None:
        key = self.settings.finnhub_api_key
        if key:
            data = await self._get_json(
                client,
                "https://finnhub.io/api/v1/quote",
                label=f"finnhub quote {ticker}",
                params={"symbol": ticker},
            )
            quote = _parse_finnhub_quote(ticker, data, market) if isinstance(data, dict) else None
            if quote:
                return quote
        return await self._quote_alphavantage(client, ticker, market)

    async def _quote_alphavantage(
        self, client: httpx.AsyncClient, ticker: str, market: MarketSpec
    ) -> Quote | None:
        key = self.settings.alphavantage_api_key
        if not key:
            return None
        data = await self._get_json(
            client,
            "https://www.alphavantage.co/query",
            label=f"alphavantage quote {ticker}",
            params={"function": "GLOBAL_QUOTE", "symbol": ticker, "apikey": key},
        )
        if not isinstance(data, dict):
            return None
        q = data.get("Global Quote") or {}
        try:
            price = float(q.get("05. price") or 0)
            if price <= 0:
                return None
            return Quote(
                ticker=ticker,
                price=price,
                change_pct=float((q.get("10. change percent") or "0").replace("%", "") or 0),
                previous_close=float(q.get("08. previous close") or 0) or None,
                volume=int(float(q.get("06. volume") or 0)) or None,
                as_of=datetime.now(UTC),
                source="alphavantage",
                currency=market.currency,
            )
        except (TypeError, ValueError) as exc:
            logger.warning("alphavantage quote %s unparsable: %s", ticker, exc)
            return None

    async def _fundamentals(self, client: httpx.AsyncClient, ticker: str) -> Fundamentals | None:
        key = self.settings.finnhub_api_key
        if not key:
            return None
        data = await self._get_json(
            client,
            "https://finnhub.io/api/v1/stock/metric",
            label=f"finnhub metric {ticker}",
            params={"symbol": ticker, "metric": "all"},
        )
        if not isinstance(data, dict):
            return None
        metric = data.get("metric") or {}

        def f(name: str) -> float | None:
            value = metric.get(name)
            try:
                return float(value) if value is not None else None
            except (TypeError, ValueError):
                return None

        return Fundamentals(
            ticker=ticker,
            pe=f("peNormalizedAnnual") or f("peBasicExclExtraTTM"),
            forward_pe=f("peExclExtraAnnual"),
            ps=f("psAnnual") or f("psTTM"),
            pb=f("pbAnnual"),
            roe=f("roeRfy") or f("roeTTM"),
            profit_margin=f("netProfitMarginTTM") or f("netProfitMarginAnnual"),
            operating_margin=f("operatingMarginTTM"),
            debt_to_equity=f("totalDebt/totalEquityAnnual"),
            current_ratio=f("currentRatioAnnual"),
            revenue_growth=f("revenueGrowthTTMYoy"),
            eps_growth=f("epsGrowthTTMYoy"),
            dividend_yield=f("dividendYieldIndicatedAnnual"),
            beta=f("beta"),
            source="finnhub",
        )

    async def _news(self, client: httpx.AsyncClient, ticker: str) -> list[NewsItem]:
        items: list[NewsItem] = []
        items.extend(await self._news_finnhub(client, ticker))
        if len(items) < 3:
            items.extend(await self._news_newsapi(client, ticker))
        seen: set[str] = set()
        unique: list[NewsItem] = []
        for item in items:
            key = item.headline.strip().lower()
            if key in seen:
                continue
            seen.add(key)
            unique.append(item)
        unique.sort(key=lambda n: n.published_at, reverse=True)
        return unique[: self.settings.max_news_per_ticker]

    async def _news_finnhub(self, client: httpx.AsyncClient, ticker: str) -> list[NewsItem]:
        key = self.settings.finnhub_api_key
        if not key:
            return []
        end = datetime.now(UTC)
        start = end - timedelta(days=self.settings.news_lookback_days)
        rows = await self._get_json(
            client,
            "https://finnhub.io/api/v1/company-news",
            label=f"finnhub news {ticker}",
            params={
                "symbol": ticker,
                "from": start.date().isoformat(),
                "to": end.date().isoformat(),
            },
        )
        if not isinstance(rows, list):
            return []
        out: list[NewsItem] = []
        for i, row in enumerate(rows[:20]):
            if not isinstance(row, dict):
                continue
            ts = row.get("datetime")
            published = datetime.fromtimestamp(ts, tz=UTC) if ts else datetime.now(UTC)
            headline = (row.get("headline") or "").strip()
            if not headline:
                continue
            out.append(
                NewsItem(
                    id=f"fh-{ticker}-{i}-{ts}",
                    ticker=ticker,
                    headline=headline,
                    summary=(row.get("summary") or "")[:800],
                    publisher=row.get("source") or "Finnhub",
                    url=row.get("url") or "https://finnhub.io/",
                    published_at=published,
                    source="finnhub",
                )
            )
        return out

    async def _news_newsapi(self, client: httpx.AsyncClient, ticker: str) -> list[NewsItem]:
        key = self.settings.newsapi_key
        if not key:
            return []
        profile = demo.PROFILES.get(ticker)
        query = f'"{profile.name}" OR {ticker}' if profile else f"{ticker} stock OR shares"
        since = (datetime.now(UTC) - timedelta(days=self.settings.news_lookback_days)).date()
        data = await self._get_json(
            client,
            "https://newsapi.org/v2/everything",
            label=f"newsapi {ticker}",
            params={
                "q": query,
                "from": since.isoformat(),
                "sortBy": "publishedAt",
                "language": "en",
                "pageSize": 10,
            },
            headers={"X-Api-Key": key},
        )
        if not isinstance(data, dict):
            return []
        out: list[NewsItem] = []
        for i, row in enumerate(data.get("articles") or []):
            if not isinstance(row, dict):
                continue
            headline = (row.get("title") or "").strip()
            url = row.get("url") or ""
            if not headline or not url:
                continue
            published_raw = row.get("publishedAt") or ""
            try:
                published = datetime.fromisoformat(published_raw.replace("Z", "+00:00"))
            except ValueError:
                published = datetime.now(UTC)
            source = (row.get("source") or {}).get("name") or "NewsAPI"
            out.append(
                NewsItem(
                    id=f"na-{ticker}-{i}",
                    ticker=ticker,
                    headline=headline,
                    summary=(row.get("description") or "")[:800],
                    publisher=source,
                    url=url,
                    published_at=published,
                    source="newsapi",
                )
            )
        return out

    async def _filings(
        self, client: httpx.AsyncClient, ticker: str, market: MarketSpec
    ) -> list[FilingItem]:
        if market.filings != "edgar":
            return []
        cik = await self._cik_for(client, ticker)
        if not cik:
            return []
        padded = cik.zfill(10)
        data = await self._get_json(
            client,
            f"https://data.sec.gov/submissions/CIK{padded}.json",
            label=f"edgar submissions {ticker}",
            headers={"Accept": "application/json"},
        )
        if not isinstance(data, dict):
            return []
        recent = (data.get("filings") or {}).get("recent") or {}
        forms = recent.get("form") or []
        accessions = recent.get("accessionNumber") or []
        filed = recent.get("filingDate") or []
        primary = recent.get("primaryDocument") or []
        desc = recent.get("primaryDocDescription") or []
        out: list[FilingItem] = []
        for i, form in enumerate(forms):
            if form not in _SEC_WANTED_FORMS or i >= len(accessions) or i >= len(filed):
                continue
            accession = accessions[i]
            acc_path = accession.replace("-", "")
            doc = primary[i] if i < len(primary) else ""
            url = (
                f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc_path}/{doc}"
                if doc
                else f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={padded}"
            )
            try:
                filed_at = datetime.fromisoformat(filed[i]).replace(tzinfo=UTC)
            except ValueError:
                continue
            out.append(
                FilingItem(
                    id=f"sec-{ticker}-{accession}",
                    ticker=ticker,
                    form=form,
                    filed_at=filed_at,
                    description=desc[i] if i < len(desc) and desc[i] else form,
                    url=url,
                    accession=accession,
                )
            )
            if len(out) >= 4:
                break
        return out

    async def _cik_for(self, client: httpx.AsyncClient, ticker: str) -> str | None:
        async with self._cik_lock:
            now = time.monotonic()
            loaded_ok = self._cik_map is not None and len(self._cik_map) > 0
            ttl = _CIK_CACHE_TTL_SECONDS if loaded_ok else _CIK_FAILURE_RETRY_SECONDS
            if self._cik_map is None or now - self._cik_loaded_at > ttl:
                data = await self._get_json(
                    client,
                    "https://www.sec.gov/files/company_tickers.json",
                    label="edgar ticker map",
                )
                mapping: dict[str, str] = {}
                if isinstance(data, dict):
                    for row in data.values():
                        if isinstance(row, dict) and row.get("ticker"):
                            mapping[str(row["ticker"]).upper()] = str(row.get("cik_str"))
                if mapping or self._cik_map is None:
                    self._cik_map = mapping
                self._cik_loaded_at = now
                if not mapping:
                    logger.warning("EDGAR ticker map unavailable; filings will be skipped")
            return (self._cik_map or {}).get(ticker)

    async def _candle(self, client: httpx.AsyncClient, ticker: str) -> Candle | None:
        key = self.settings.finnhub_api_key
        if not key:
            return None
        end = int(datetime.now(UTC).timestamp())
        start = end - 60 * 60 * 24 * 45
        data = await self._get_json(
            client,
            "https://finnhub.io/api/v1/stock/candle",
            label=f"finnhub candle {ticker}",
            params={"symbol": ticker, "resolution": "D", "from": start, "to": end},
        )
        if not isinstance(data, dict) or data.get("s") != "ok":
            return None
        try:
            closes = [float(v) for v in (data.get("c") or [])]
            stamps = [datetime.fromtimestamp(ts, tz=UTC) for ts in (data.get("t") or [])]
        except (TypeError, ValueError):
            return None
        if not closes:
            return None
        return Candle(ticker=ticker, closes=closes[-32:], timestamps=stamps[-32:])


def _parse_finnhub_quote(ticker: str, data: dict[str, Any], market: MarketSpec) -> Quote | None:
    try:
        price = float(data.get("c") or 0)
        prev = float(data.get("pc") or 0)
    except (TypeError, ValueError):
        return None
    if price <= 0:
        return None
    change = ((price / prev) - 1) * 100 if prev else 0.0
    ts = data.get("t")
    return Quote(
        ticker=ticker,
        price=price,
        change_pct=round(change, 2),
        previous_close=prev or None,
        high=data.get("h") or None,
        low=data.get("l") or None,
        as_of=datetime.fromtimestamp(ts, tz=UTC) if ts else datetime.now(UTC),
        source="finnhub",
        currency=market.currency,
    )
