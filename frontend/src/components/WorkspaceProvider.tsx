"use client";

import { useSession } from "next-auth/react";
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";

import { ApiError, api, setApiToken } from "@/lib/api";
import type { Market, MarketCatalog, Me, RiskAppetite, Role, UserProfile, WatchlistItem } from "@/lib/types";

/**
 * The viewer's workspace: which venue they follow, which policy appetite they view the
 * book under, and their watchlist.
 *
 * - Anonymous visitors keep venue/appetite in localStorage (appetite `null` = the desk's
 *   stored policy). No watchlist.
 * - Signed-in users persist preferences and watchlist through `/api/v1/me/*`.
 */

const LS_MARKET = "desk-market";
const LS_APPETITE = "desk-appetite";
const APPETITES: readonly RiskAppetite[] = ["conservative", "balanced", "aggressive"];

type AuthState = "loading" | "anonymous" | "authenticated";

type WorkspaceValue = {
  /** Session status from Auth.js, folded to three states. */
  auth: AuthState;
  user: UserProfile | null;
  role: Role | "anonymous";
  isAdmin: boolean;
  /**
   * Whether the API requires sign-in (`null` until `/health` answers).
   * When `false`, workspace/admin are open locally without an account.
   */
  authEnabled: boolean | null;
  catalog: MarketCatalog | null;
  market: Market | null;
  /** `null` = view under the appetite the run was produced with. */
  appetite: RiskAppetite | null;
  watchlist: WatchlistItem[];
  watched: Set<string>;
  loading: boolean;
  error: string | null;
  setMarketId: (id: string) => Promise<void>;
  setAppetite: (appetite: RiskAppetite | null) => Promise<void>;
  toggleWatch: (ticker: string) => Promise<void>;
  refreshWorkspace: () => Promise<void>;
};

const WorkspaceContext = createContext<WorkspaceValue>({
  auth: "loading",
  user: null,
  role: "anonymous",
  isAdmin: false,
  authEnabled: null,
  catalog: null,
  market: null,
  appetite: null,
  watchlist: [],
  watched: new Set(),
  loading: true,
  error: null,
  setMarketId: async () => undefined,
  setAppetite: async () => undefined,
  toggleWatch: async () => undefined,
  refreshWorkspace: async () => undefined,
});

function readLocal<T extends string>(key: string, allowed?: readonly T[]): T | null {
  if (typeof window === "undefined") return null;
  try {
    const value = window.localStorage.getItem(key);
    if (!value) return null;
    if (allowed && !allowed.includes(value as T)) return null;
    return value as T;
  } catch {
    return null;
  }
}

function writeLocal(key: string, value: string | null) {
  try {
    if (value === null) window.localStorage.removeItem(key);
    else window.localStorage.setItem(key, value);
  } catch {
    // Storage disabled; state still lives for this tab.
  }
}

function findMarket(catalog: MarketCatalog | null, id: string | null): Market | null {
  if (!catalog) return null;
  if (id) {
    for (const country of catalog.countries) {
      const hit = country.markets.find((m) => m.id === id);
      if (hit) return hit;
    }
  }
  return catalog.active ?? null;
}

export function WorkspaceProvider({ children }: { children: React.ReactNode }) {
  const { data: session, status } = useSession();
  const auth: AuthState = status === "loading" ? "loading" : session?.user ? "authenticated" : "anonymous";
  // When the API reports auth=false, local admin/workspace are open (no sign-in needed).
  const [authEnabled, setAuthEnabled] = useState<boolean | null>(null);

  // Push the bearer token into the API client synchronously with session changes.
  setApiToken(session?.apiToken ?? null);

  useEffect(() => {
    let cancelled = false;
    api
      .health()
      .then((health) => {
        if (!cancelled) setAuthEnabled(health.auth ?? false);
      })
      .catch(() => {
        // Fail closed for page gates: treat auth as required if health is unreachable.
        if (!cancelled) setAuthEnabled(true);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const [catalog, setCatalog] = useState<MarketCatalog | null>(null);
  const [marketId, setMarketIdState] = useState<string | null>(null);
  const [appetite, setAppetiteState] = useState<RiskAppetite | null>(null);
  const [me, setMe] = useState<Me | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const mounted = useRef(true);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  // Venue catalog: public, loaded once.
  useEffect(() => {
    api
      .markets()
      .then((next) => mounted.current && setCatalog(next))
      .catch((err) => mounted.current && setError(err instanceof Error ? err.message : "Unable to load venues"));
  }, []);

  const loadMe = useCallback(async () => {
    const profile = await api.me();
    if (!mounted.current) return;
    setMe(profile);
    setMarketIdState(profile.preferences.market_id);
    setAppetiteState(profile.preferences.risk_appetite);
    setError(null);
  }, []);

  // Identity-dependent state: anonymous falls back to localStorage, signed-in to /me.
  useEffect(() => {
    if (auth === "loading") return;
    let cancelled = false;
    setLoading(true);
    if (auth === "anonymous") {
      setMe(null);
      setMarketIdState(readLocal(LS_MARKET));
      setAppetiteState(readLocal(LS_APPETITE, APPETITES));
      setLoading(false);
      return;
    }
    loadMe()
      .catch((err) => {
        if (cancelled) return;
        // A stale token is the common cause; the session refetch will mint a new one.
        setError(err instanceof ApiError && err.status === 401 ? null : err instanceof Error ? err.message : "Workspace unavailable");
      })
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [auth, session?.user?.id, session?.apiToken, loadMe]);

  const setMarketId = useCallback(
    async (id: string) => {
      setMarketIdState(id);
      if (auth === "authenticated") {
        try {
          const prefs = await api.setPreferences({ market_id: id });
          if (mounted.current) setMarketIdState(prefs.market_id);
        } catch (err) {
          if (mounted.current) setError(err instanceof Error ? err.message : "Could not save venue");
        }
      } else {
        writeLocal(LS_MARKET, id);
      }
    },
    [auth],
  );

  const setAppetite = useCallback(
    async (next: RiskAppetite | null) => {
      setAppetiteState(next);
      if (auth === "authenticated") {
        if (!next) return;
        try {
          const prefs = await api.setPreferences({ risk_appetite: next });
          if (mounted.current) setAppetiteState(prefs.risk_appetite);
        } catch (err) {
          if (mounted.current) setError(err instanceof Error ? err.message : "Could not save appetite");
        }
      } else {
        writeLocal(LS_APPETITE, next);
      }
    },
    [auth],
  );

  const market = useMemo(() => findMarket(catalog, marketId), [catalog, marketId]);
  const watchlist = useMemo(
    () => (me && market ? me.watchlist.filter((w) => w.market_id === market.id) : []),
    [me, market],
  );
  const watched = useMemo(() => new Set(watchlist.map((w) => w.ticker)), [watchlist]);

  const toggleWatch = useCallback(
    async (ticker: string) => {
      if (auth !== "authenticated" || !market || !me) return;
      const symbol = ticker.toUpperCase();
      const currently = me.watchlist.some((w) => w.market_id === market.id && w.ticker === symbol);
      // Optimistic update; reconcile from the server response.
      setMe((current) =>
        current
          ? {
              ...current,
              watchlist: currently
                ? current.watchlist.filter((w) => !(w.market_id === market.id && w.ticker === symbol))
                : [
                    { ticker: symbol, market_id: market.id, added_at: new Date().toISOString(), covered: true },
                    ...current.watchlist,
                  ],
            }
          : current,
      );
      try {
        if (currently) {
          await api.unwatch(symbol, market.id);
        } else {
          const item = await api.watch(symbol, market.id);
          setMe((current) =>
            current
              ? {
                  ...current,
                  watchlist: current.watchlist.map((w) =>
                    w.market_id === item.market_id && w.ticker === item.ticker ? item : w,
                  ),
                }
              : current,
          );
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : "Could not update watchlist");
        await loadMe().catch(() => undefined);
      }
    },
    [auth, market, me, loadMe],
  );

  const refreshWorkspace = useCallback(async () => {
    if (auth === "authenticated") await loadMe();
  }, [auth, loadMe]);

  const value = useMemo<WorkspaceValue>(
    () => ({
      auth,
      user: me?.user ?? (session?.user ? { id: session.user.id, email: session.user.email, name: session.user.name, image: session.user.image, role: session.user.role } : null),
      role: me?.user.role ?? session?.user?.role ?? "anonymous",
      isAdmin: (me?.user.role ?? session?.user?.role) === "admin" || authEnabled === false,
      authEnabled,
      catalog,
      market,
      appetite,
      watchlist,
      watched,
      loading: loading || auth === "loading" || authEnabled === null || (!catalog && !error),
      error,
      setMarketId,
      setAppetite,
      toggleWatch,
      refreshWorkspace,
    }),
    [auth, me, session, authEnabled, catalog, market, appetite, watchlist, watched, loading, error, setMarketId, setAppetite, toggleWatch, refreshWorkspace],
  );

  return <WorkspaceContext.Provider value={value}>{children}</WorkspaceContext.Provider>;
}

export function useWorkspace() {
  return useContext(WorkspaceContext);
}

/** Backwards-compatible subset used by venue-only components. */
export function useMarket() {
  const { catalog, market, setMarketId, loading, error } = useWorkspace();
  return { catalog, market, setMarketId, loading, error };
}
