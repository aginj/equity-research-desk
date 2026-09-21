export type Action = "accumulate" | "watch" | "reduce" | "avoid";
export type Horizon = "tactical_1_3m" | "swing_3_12m" | "position_1y_plus";
export type RiskAppetite = "conservative" | "balanced" | "aggressive";
export type RunStatus = "queued" | "running" | "completed" | "failed";

export type Source = {
  id: string;
  title: string;
  publisher: string;
  url: string;
  published_at?: string | null;
  kind: "news" | "filing" | "market" | "internal";
};

export type Quote = {
  ticker: string;
  price: number;
  change_pct: number;
  previous_close?: number | null;
  high?: number | null;
  low?: number | null;
  volume?: number | null;
  market_cap?: number | null;
  pe?: number | null;
  week_52_high?: number | null;
  week_52_low?: number | null;
  as_of: string;
  source: string;
  currency?: string;
};

export type Profile = {
  ticker: string;
  name: string;
  sector: string;
  industry: string;
  description: string;
};

export type NewsItem = {
  id: string;
  ticker: string;
  headline: string;
  summary: string;
  publisher: string;
  url: string;
  published_at: string;
  source: string;
};

export type FilingItem = {
  id: string;
  ticker: string;
  form: string;
  filed_at: string;
  description: string;
  url: string;
  accession?: string | null;
};

export type Scorecard = {
  news_materiality: number;
  fundamental_quality: number;
  valuation_attractiveness: number;
  momentum: number;
  risk: number;
  source_quality: number;
  composite: number;
};

export type Recommendation = {
  ticker: string;
  name: string;
  sector: string;
  action: Action;
  conviction: number;
  horizon: Horizon;
  thesis: string;
  bull_case: string;
  bear_case: string;
  invalidation: string;
  catalysts: string[];
  risks: string[];
  scores: Scorecard;
  sources: Source[];
  quote: Quote;
  policy_notes: string[];
  synthesis_mode: "llm" | "heuristic";
};

export type TickerIntel = {
  ticker: string;
  profile: Profile;
  quote: Quote;
  news: NewsItem[];
  filings: FilingItem[];
  candle?: { ticker: string; closes: number[] } | null;
  news_bias: number;
  filing_bias: number;
  narrative: string;
  scorecard?: Scorecard | null;
};

export type DeskSummary = {
  regime: string;
  headline: string;
  body: string;
  risk_appetite: RiskAppetite;
  tickers_analyzed: number;
  news_items: number;
  filings: number;
  llm_enabled: boolean;
  live_market: boolean;
  market_id?: string;
  market_label?: string;
  country?: string;
  exchange?: string;
  currency?: string;
  caveats: string[];
};

export type AnalysisResult = {
  run_id: string;
  status: RunStatus;
  stage: string;
  started_at: string;
  finished_at?: string | null;
  error?: string | null;
  market_id?: string;
  summary?: DeskSummary | null;
  recommendations: Recommendation[];
  intel: TickerIntel[];
};

export type UniverseTicker = {
  ticker: string;
  name?: string | null;
  sector?: string | null;
  market_id?: string;
  exchange?: string | null;
  currency?: string | null;
  active: boolean;
};

export type RunEvent = {
  run_id: string;
  stage: string;
  message: string;
  at: string;
  progress: number;
};

export type Market = {
  id: string;
  country_code: string;
  country: string;
  exchange_code: string;
  exchange: string;
  currency: string;
  timezone: string;
  locale: string;
  symbol_hint: string;
  filings: "edgar" | "none";
  filings_label: string;
  min_price: number;
  label: string;
  quote_home: string;
};

export type MarketCatalog = {
  countries: { code: string; name: string; markets: Market[] }[];
  active: Market;
};

export type Health = {
  status: "ok" | "degraded";
  app: string;
  version?: string;
  environment?: string;
  database?: "ok" | "error";
  llm: boolean;
  live_market: boolean;
  force_demo: boolean;
  auth?: boolean;
  risk_appetite: RiskAppetite;
  market?: Market;
  active_run_id?: string | null;
};

/** A run viewed under a specific appetite (see `GET /api/v1/book`). */
export type Book = {
  run: AnalysisResult;
  appetite: RiskAppetite;
  repoliced: boolean;
};

export type Role = "user" | "admin";

export type UserProfile = {
  id: string;
  email?: string | null;
  name?: string | null;
  image?: string | null;
  role: Role;
};

export type Preferences = {
  market_id: string;
  risk_appetite: RiskAppetite;
};

export type WatchlistItem = {
  ticker: string;
  market_id: string;
  note?: string | null;
  added_at: string;
  covered: boolean;
  name?: string | null;
  sector?: string | null;
};

export type Me = {
  user: UserProfile;
  preferences: Preferences;
  watchlist: WatchlistItem[];
};

export type CoverageRequest = {
  market_id: string;
  ticker: string;
  requests: number;
};
