"""Shared domain models. These are the contracts between ingest, agents, and the API."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

Action = Literal["accumulate", "watch", "reduce", "avoid"]
Horizon = Literal["tactical_1_3m", "swing_3_12m", "position_1y_plus"]
RiskAppetite = Literal["conservative", "balanced", "aggressive"]
RunStatus = Literal["queued", "running", "completed", "failed"]
RunStage = Literal[
    "queued",
    "ingest",
    "news_analyst",
    "filings_analyst",
    "fundamentals_analyst",
    "risk_analyst",
    "chief_analyst",
    "policy",
    "completed",
    "failed",
]


class Source(BaseModel):
    id: str
    title: str
    publisher: str
    url: str
    published_at: datetime | None = None
    kind: Literal["news", "filing", "market", "internal"] = "news"


class Quote(BaseModel):
    ticker: str
    price: float
    change_pct: float
    previous_close: float | None = None
    high: float | None = None
    low: float | None = None
    volume: int | None = None
    market_cap: float | None = None
    pe: float | None = None
    week_52_high: float | None = None
    week_52_low: float | None = None
    as_of: datetime
    source: str = "demo"
    currency: str = "USD"


class Profile(BaseModel):
    ticker: str
    name: str
    sector: str
    industry: str
    country: str = "US"
    exchange: str = "US"
    ipo: str | None = None
    description: str = ""


class NewsItem(BaseModel):
    id: str
    ticker: str
    headline: str
    summary: str
    publisher: str
    url: str
    published_at: datetime
    source: str


class FilingItem(BaseModel):
    id: str
    ticker: str
    form: str
    filed_at: datetime
    description: str
    url: str
    accession: str | None = None


class Candle(BaseModel):
    ticker: str
    closes: list[float] = Field(default_factory=list)
    timestamps: list[datetime] = Field(default_factory=list)


class Fundamentals(BaseModel):
    ticker: str
    pe: float | None = None
    forward_pe: float | None = None
    peg: float | None = None
    ps: float | None = None
    pb: float | None = None
    roe: float | None = None
    profit_margin: float | None = None
    operating_margin: float | None = None
    debt_to_equity: float | None = None
    current_ratio: float | None = None
    revenue_growth: float | None = None
    eps_growth: float | None = None
    dividend_yield: float | None = None
    beta: float | None = None
    source: str = "demo"


class Scorecard(BaseModel):
    news_materiality: float = Field(ge=0, le=1)
    fundamental_quality: float = Field(ge=0, le=1)
    valuation_attractiveness: float = Field(ge=0, le=1)
    momentum: float = Field(ge=0, le=1)
    risk: float = Field(ge=0, le=1)
    source_quality: float = Field(ge=0, le=1)
    composite: float = Field(ge=0, le=1)


class EventExtract(BaseModel):
    ticker: str
    headline: str
    event_type: str
    materiality: float = Field(ge=0, le=1)
    sentiment: float = Field(ge=-1, le=1)
    summary: str
    source_ids: list[str] = Field(default_factory=list)


class TickerIntel(BaseModel):
    ticker: str
    profile: Profile
    quote: Quote
    fundamentals: Fundamentals
    news: list[NewsItem] = Field(default_factory=list)
    filings: list[FilingItem] = Field(default_factory=list)
    candle: Candle | None = None
    events: list[EventExtract] = Field(default_factory=list)
    news_bias: float = 0.0
    filing_bias: float = 0.0
    narrative: str = ""
    scorecard: Scorecard | None = None
    next_earnings: datetime | None = None


class Recommendation(BaseModel):
    ticker: str
    name: str
    sector: str
    action: Action
    conviction: float = Field(ge=0, le=1)
    horizon: Horizon
    thesis: str
    bull_case: str
    bear_case: str
    invalidation: str
    catalysts: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    scores: Scorecard
    sources: list[Source] = Field(default_factory=list)
    quote: Quote
    policy_notes: list[str] = Field(default_factory=list)
    synthesis_mode: Literal["llm", "heuristic"] = "heuristic"

    @field_validator("thesis", "bull_case", "bear_case", "invalidation")
    @classmethod
    def not_empty(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("narrative fields must not be empty")
        return cleaned


class RunUsage(BaseModel):
    llm_calls: int = 0
    llm_tokens: int = 0
    vendor_calls: int = 0


class DeskSummary(BaseModel):
    regime: str
    headline: str
    body: str
    risk_appetite: RiskAppetite
    tickers_analyzed: int
    news_items: int
    filings: int
    llm_enabled: bool
    live_market: bool
    market_id: str = "us"
    market_label: str = "United States · US"
    country: str = "United States"
    exchange: str = "NYSE & Nasdaq"
    currency: str = "USD"
    caveats: list[str] = Field(default_factory=list)
    usage: RunUsage = Field(default_factory=RunUsage)


class RunEvent(BaseModel):
    run_id: str
    stage: RunStage
    message: str
    at: datetime
    progress: float = Field(ge=0, le=1)


class AnalysisResult(BaseModel):
    run_id: str
    status: RunStatus
    stage: RunStage
    started_at: datetime
    finished_at: datetime | None = None
    error: str | None = None
    market_id: str = "us"
    triggered_by: str | None = None
    summary: DeskSummary | None = None
    recommendations: list[Recommendation] = Field(default_factory=list)
    intel: list[TickerIntel] = Field(default_factory=list)
    # Chief-analyst output *before* desk policy. Kept so a viewer's own appetite can be
    # applied later without re-running the agents. Excluded from API responses.
    recommendations_raw: list[Recommendation] = Field(default_factory=list)

    def public(self) -> AnalysisResult:
        """Copy without the raw recommendations, for API responses."""
        return self.model_copy(update={"recommendations_raw": []})


class Book(BaseModel):
    """A run viewed under a specific policy appetite."""

    run: AnalysisResult
    appetite: RiskAppetite
    repoliced: bool


class UniverseTicker(BaseModel):
    ticker: str
    name: str | None = None
    sector: str | None = None
    market_id: str = "us"
    exchange: str | None = None
    currency: str | None = None
    active: bool = True
