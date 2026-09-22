import type {
  AnalysisResult,
  AuditEntry,
  Book,
  BookChanges,
  CoverageRequest,
  DeskNotification,
  DeskSchedule,
  DeskUser,
  Health,
  Market,
  MarketCatalog,
  Me,
  Preferences,
  RatingPoint,
  Recommendation,
  RiskAppetite,
  RunEvent,
  RunStatus,
  TickerIntel,
  TrackRecord,
  UniversePreset,
  UniverseTicker,
  WatchlistItem,
} from "./types";

/**
 * Base URL for the research API. Empty (the production default) means same-origin: the
 * browser calls `/api/v1/...` and the reverse proxy routes it to FastAPI. Local development
 * points at the uvicorn port directly.
 */
export const API_URL = (
  process.env.NEXT_PUBLIC_API_URL ?? (process.env.NODE_ENV === "development" ? "http://127.0.0.1:8810" : "")
).replace(/\/+$/, "");

/**
 * Bearer token minted by Auth.js after sign-in. Set by the workspace provider whenever the
 * session changes; `null` means anonymous. Read-only endpoints work without it.
 */
let apiToken: string | null = null;

export function setApiToken(token: string | null | undefined): void {
  apiToken = token ?? null;
}

export function hasApiToken(): boolean {
  return apiToken !== null;
}

const DEFAULT_TIMEOUT_MS = 20_000;

export class ApiError extends Error {
  readonly status: number;
  readonly detail: unknown;
  readonly requestId: string | null;

  constructor(status: number, message: string, detail: unknown, requestId: string | null) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
    this.requestId = requestId;
  }
}

function describeDetail(detail: unknown, fallback: string): string {
  if (typeof detail === "string") return detail;
  if (detail && typeof detail === "object") {
    if ("message" in detail && typeof (detail as { message: unknown }).message === "string") {
      return (detail as { message: string }).message;
    }
    if (Array.isArray(detail)) {
      const first = detail[0] as { msg?: string; loc?: unknown[] } | undefined;
      if (first?.msg) {
        const where = Array.isArray(first.loc) ? first.loc.slice(1).join(".") : "";
        return where ? `${where}: ${first.msg}` : first.msg;
      }
    }
  }
  return fallback;
}

async function toApiError(response: Response): Promise<ApiError> {
  const requestId = response.headers.get("x-request-id");
  let detail: unknown = null;
  try {
    const body = (await response.json()) as { detail?: unknown };
    detail = body?.detail ?? body;
  } catch {
    detail = await response.text().catch(() => "");
  }
  const message = describeDetail(detail, `${response.status} ${response.statusText || "request failed"}`);
  return new ApiError(response.status, message, detail, requestId);
}

async function request<T>(path: string, init?: RequestInit & { timeoutMs?: number }): Promise<T> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), init?.timeoutMs ?? DEFAULT_TIMEOUT_MS);
  try {
    const response = await fetch(`${API_URL}${path}`, {
      ...init,
      signal: controller.signal,
      headers: {
        Accept: "application/json",
        ...(init?.body ? { "Content-Type": "application/json" } : {}),
        ...(apiToken ? { Authorization: `Bearer ${apiToken}` } : {}),
        ...(init?.headers ?? {}),
      },
      cache: "no-store",
    });
    if (!response.ok) throw await toApiError(response);
    if (response.status === 204) return undefined as T;
    return (await response.json()) as T;
  } catch (err) {
    if (err instanceof ApiError) throw err;
    if (err instanceof DOMException && err.name === "AbortError") {
      throw new ApiError(0, "The research API did not respond in time.", null, null);
    }
    throw new ApiError(0, "Unable to reach the research API.", err, null);
  } finally {
    clearTimeout(timer);
  }
}

function qs(params: Record<string, string | number | null | undefined>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== "") search.set(key, String(value));
  }
  const encoded = search.toString();
  return encoded ? `?${encoded}` : "";
}

export const api = {
  health: () => request<Health>("/api/v1/health"),
  markets: () => request<MarketCatalog>("/api/v1/markets"),

  // --- admin: desk defaults and the analyzed universe -------------------------------------
  universe: (marketId?: string) => request<UniverseTicker[]>(`/api/v1/universe${qs({ market_id: marketId })}`),
  replaceUniverse: (tickers: string[], marketId?: string) =>
    request<UniverseTicker[]>(`/api/v1/universe${qs({ market_id: marketId })}`, {
      method: "PUT",
      body: JSON.stringify({ tickers }),
    }),
  appetite: () => request<{ risk_appetite: RiskAppetite }>("/api/v1/settings/appetite"),
  setAppetite: (risk_appetite: RiskAppetite) =>
    request<{ risk_appetite: RiskAppetite }>("/api/v1/settings/appetite", {
      method: "PUT",
      body: JSON.stringify({ risk_appetite }),
    }),
  setMarket: (market_id: string) =>
    request<{ market: Market }>("/api/v1/settings/market", {
      method: "PUT",
      body: JSON.stringify({ market_id }),
    }),
  coverageRequests: () => request<{ requests: CoverageRequest[] }>("/api/v1/admin/coverage-requests"),
  schedule: () => request<DeskSchedule>("/api/v1/settings/schedule"),
  setSchedule: (markets: DeskSchedule["markets"]) =>
    request<DeskSchedule>("/api/v1/settings/schedule", {
      method: "PUT",
      body: JSON.stringify({
        markets: markets.map((row) => ({
          market_id: row.market_id,
          morning: row.morning,
          afternoon: row.afternoon,
          enabled: row.enabled ?? true,
          closed_dates: row.closed_dates ?? [],
        })),
      }),
    }),

  register: (username: string, password: string) =>
    request<{ user: { id: string; role: string }; token: string; exp: number }>("/api/v1/auth/register", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    }),

  // --- the book (public) ------------------------------------------------------------------
  /** Latest completed run for a venue, re-ranked under `appetite` when given. */
  book: async (marketId?: string, appetite?: RiskAppetite | null): Promise<Book | null> => {
    try {
      return await request<Book>(`/api/v1/book${qs({ market_id: marketId, appetite })}`);
    } catch (err) {
      if (err instanceof ApiError && err.status === 404) return null;
      throw err;
    }
  },
  latest: async (marketId?: string): Promise<AnalysisResult | null> => {
    try {
      return await request<AnalysisResult>(`/api/v1/runs/latest${qs({ market_id: marketId })}`);
    } catch (err) {
      if (err instanceof ApiError && err.status === 404) return null;
      throw err;
    }
  },
  runs: (limit = 12, marketId?: string) =>
    request<AnalysisResult[]>(`/api/v1/runs${qs({ limit, market_id: marketId })}`),
  run: (id: string) => request<AnalysisResult>(`/api/v1/runs/${encodeURIComponent(id)}`),
  idea: (ticker: string, marketId?: string, appetite?: RiskAppetite | null) =>
    request<{ run_id: string; appetite: RiskAppetite; recommendation: Recommendation; intel: TickerIntel | null }>(
      `/api/v1/ideas/${encodeURIComponent(ticker)}${qs({ market_id: marketId, appetite })}`,
    ),
  ideaHistory: (ticker: string, marketId?: string) =>
    request<{ ticker: string; market_id: string; points: RatingPoint[] }>(
      `/api/v1/ideas/${encodeURIComponent(ticker)}/history${qs({ market_id: marketId })}`,
    ),
  bookChanges: async (marketId?: string, appetite?: RiskAppetite | null): Promise<BookChanges | null> => {
    try {
      return await request<BookChanges>(`/api/v1/book/changes${qs({ market_id: marketId, appetite })}`);
    } catch (err) {
      if (err instanceof ApiError && err.status === 404) return null;
      throw err;
    }
  },
  trackRecord: (marketId?: string) => request<TrackRecord>(`/api/v1/track-record${qs({ market_id: marketId })}`),
  notifications: (unread = false) =>
    request<{ unread: number; notifications: DeskNotification[] }>(
      `/api/v1/me/notifications${qs({ unread: unread ? "true" : undefined })}`,
    ),
  markNotificationsRead: (ids?: string[]) =>
    request<{ updated: number; unread: number }>("/api/v1/me/notifications/read", {
      method: "POST",
      body: JSON.stringify({ ids: ids ?? null }),
    }),
  changePassword: (current_password: string, new_password: string) =>
    request<{ ok: boolean }>("/api/v1/me/password", {
      method: "PUT",
      body: JSON.stringify({ current_password, new_password }),
    }),
  adminUsers: () => request<{ users: DeskUser[] }>("/api/v1/admin/users"),
  setUserRole: (id: string, role: "user" | "admin") =>
    request<{ id: string; role: string }>(`/api/v1/admin/users/${encodeURIComponent(id)}/role`, {
      method: "PUT",
      body: JSON.stringify({ role }),
    }),
  setUserDisabled: (id: string, disabled: boolean) =>
    request<{ id: string; disabled: boolean }>(`/api/v1/admin/users/${encodeURIComponent(id)}/disabled`, {
      method: "PUT",
      body: JSON.stringify({ disabled }),
    }),
  resetUserPassword: (id: string, password: string) =>
    request<{ ok: boolean }>(`/api/v1/admin/users/${encodeURIComponent(id)}/password`, {
      method: "PUT",
      body: JSON.stringify({ password }),
    }),
  audit: () => request<{ entries: AuditEntry[] }>("/api/v1/admin/audit"),
  presets: (marketId: string) =>
    request<{ market_id: string; presets: UniversePreset[] }>(`/api/v1/markets/${encodeURIComponent(marketId)}/presets`),
  validateUniverse: (tickers: string[], marketId?: string) =>
    request<{ verified: boolean; tickers: { ticker: string; status: string; price?: number | null }[] }>(
      `/api/v1/admin/universe/validate${qs({ market_id: marketId })}`,
      { method: "POST", body: JSON.stringify({ tickers }) },
    ),

  // --- personal workspace (requires sign-in) ----------------------------------------------
  me: () => request<Me>("/api/v1/me"),
  setPreferences: (prefs: Partial<Preferences>) =>
    request<Preferences>("/api/v1/me/preferences", { method: "PUT", body: JSON.stringify(prefs) }),
  watchlist: (marketId?: string) => request<WatchlistItem[]>(`/api/v1/me/watchlist${qs({ market_id: marketId })}`),
  watch: (ticker: string, marketId: string, note?: string) =>
    request<WatchlistItem>(`/api/v1/me/watchlist/${encodeURIComponent(ticker)}`, {
      method: "PUT",
      body: JSON.stringify({ market_id: marketId, note }),
    }),
  unwatch: (ticker: string, marketId: string) =>
    request<void>(`/api/v1/me/watchlist/${encodeURIComponent(ticker)}${qs({ market_id: marketId })}`, {
      method: "DELETE",
    }),

  /**
   * Start a desk run (admin). If one is already in progress the API answers 409 with its
   * id; we attach to that run instead of surfacing an error.
   */
  startRun: async (body?: { tickers?: string[]; risk_appetite?: RiskAppetite; market_id?: string }) => {
    try {
      const started = await request<AnalysisResult>("/api/v1/runs", {
        method: "POST",
        body: JSON.stringify(body ?? {}),
      });
      return { run: started, attached: false as const };
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        const detail = err.detail as { run_id?: string } | null;
        if (detail?.run_id) {
          const existing = await request<AnalysisResult>(`/api/v1/runs/${detail.run_id}`);
          return { run: existing, attached: true as const };
        }
      }
      throw err;
    }
  },
};

const TERMINAL: ReadonlySet<RunStatus> = new Set<RunStatus>(["completed", "failed"]);

export function isTerminal(status: RunStatus): boolean {
  return TERMINAL.has(status);
}

/** Poll a run until it reaches a terminal state or the deadline passes. */
export async function waitForRun(
  runId: string,
  opts: { intervalMs?: number; timeoutMs?: number; signal?: AbortSignal } = {},
): Promise<AnalysisResult> {
  const interval = opts.intervalMs ?? 1_500;
  const deadline = Date.now() + (opts.timeoutMs ?? 180_000);
  let last = await api.run(runId);
  while (!isTerminal(last.status)) {
    if (opts.signal?.aborted) break;
    if (Date.now() > deadline) {
      throw new ApiError(0, `Run ${runId} is still ${last.status}; check Admin → Run history later.`, null, null);
    }
    await new Promise((resolve) => setTimeout(resolve, interval));
    last = await api.run(runId);
  }
  return last;
}

/**
 * Subscribe to live stage events. The stream ends with a `done` event; on transport error we
 * stop and let the caller fall back to polling, since the server-side bus replays history.
 */
export function subscribeRun(runId: string, onEvent: (event: RunEvent) => void, onDone: () => void) {
  const source = new EventSource(`${API_URL}/api/v1/runs/${encodeURIComponent(runId)}/events`);
  let finished = false;
  const finish = () => {
    if (finished) return;
    finished = true;
    source.close();
    onDone();
  };
  source.addEventListener("stage", (event) => {
    try {
      onEvent(JSON.parse((event as MessageEvent).data) as RunEvent);
    } catch {
      // Ignore malformed frames; polling remains the source of truth.
    }
  });
  source.addEventListener("done", finish);
  source.onerror = finish;
  return finish;
}
