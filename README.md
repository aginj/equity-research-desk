# Equity Research Desk

An **agentic equity research desk**. It collects licensed market news, official SEC filings, and prices, then ranks a coverage universe with sourced theses.

This is a research instrument. It is **not** a broker, not a registered adviser, and not a trade-execution system.

## What you get

- Multi-agent pipeline: ingest → news analyst → filings analyst → fundamentals/risk scores → chief analyst → **deterministic policy**
- Licensed data adapters (Finnhub, NewsAPI, Alpha Vantage) plus **SEC EDGAR** (no publisher-site scraping)
- Works with **zero API keys** via a complete demo book, then upgrades as keys are added
- LLM synthesis when OpenAI, Anthropic, Cursor, or an OpenAI-compatible gateway is configured; otherwise transparent heuristics
- Research-desk UI: ranked book, tape, idea pages with bull/bear/invalidation and citations — light/dark themes, live run pipeline, responsive layout
- **Public website with optional sign-in**: anyone can read the book; signing in (Google, GitHub, or email link) unlocks a personal workspace — your venue, your risk appetite (the shared book is re-ranked for you, no extra cost), and a watchlist. Only admins can run the desk or edit the analyzed universe.
- Audit trail of every run — SQLite locally, Postgres in production, schema managed by Alembic

## Architecture

```
Watchlist
    │
    ▼
Data hub ── Finnhub / NewsAPI / Alpha Vantage / SEC EDGAR / demo fixtures
    │
    ▼
News analyst ── event extraction, sentiment, materiality
Filings analyst ── 8-K / 10-Q / 10-K notes
Scoring ── quality, valuation, momentum, risk, source quality
Chief analyst ── thesis, catalysts, invalidation (LLM or heuristic)
    │
    ▼
Desk policy ── conviction floors, sector caps, min sources, min price
    │
    ▼
Ranked book (accumulate / watch / reduce / avoid)
```

Agents **propose**. Policy **disposes**. The language model cannot override liquidity, sector, or evidence floors.

## Quick start

### 1. Backend

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
copy ..\.env.example ..\.env
uvicorn app.main:app --reload --port 8810
```

API: [http://127.0.0.1:8810](http://127.0.0.1:8810) · docs: [http://127.0.0.1:8810/docs](http://127.0.0.1:8810/docs)

### 2. Frontend

```powershell
cd frontend
npm install
npm run dev
```

Desk: [http://localhost:3810](http://localhost:3810)

### 3. Run the desk

Open the Desk page and click **Run desk**. With no keys, the book is built from bundled research fixtures. Add keys to `.env` and restart to blend live news, quotes, and filings.

Locally, with no `SMP_AUTH_JWT_SECRET` or `SMP_API_KEY` set, admin actions are open and the API logs a warning at startup. To try sign-in locally, set `AUTH_SECRET`, `SMP_AUTH_JWT_SECRET` (same value in both `.env` and the frontend environment), `SMP_ADMIN_EMAILS`, and one OAuth provider (`AUTH_GITHUB_ID`/`AUTH_GITHUB_SECRET` with callback `http://localhost:3810/api/auth/callback/github` is the quickest). Email magic links additionally need Postgres (`DATABASE_URL`).

## Configuration

Copy `.env.example` to `.env` in the repo root. Setting names keep an `SMP_` prefix so existing env files stay valid.

| Variable | Purpose |
|---|---|
| `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` / `CURSOR_API_KEY` | Qualitative write-ups |
| `SMP_CURSOR_MODEL` / `SMP_CURSOR_BASE_URL` | Cursor model (default `composer-2.5`); optional OpenAI-compatible proxy. With only the key set, the desk uses a no-repo Cloud Agent |
| `SMP_LLM_BASE_URL` + `SMP_LLM_API_KEY` | Groq, OpenRouter, Ollama, Azure-compatible gateways |
| `FINNHUB_API_KEY` | Quotes, company news, fundamentals, candles |
| `NEWSAPI_KEY` | Broader headline coverage |
| `ALPHAVANTAGE_API_KEY` | Quote fallback |
| `SMP_SEC_USER_AGENT` | Required identity for EDGAR |
| `SMP_FORCE_DEMO_DATA=true` | Fixtures only (demos / CI) |
| `SMP_RISK_APPETITE` | `conservative` \| `balanced` \| `aggressive` |
| `SMP_SCHEDULER_HOURS` | Optional unattended refresh |
| `SMP_ENVIRONMENT` | `development` \| `staging` \| `production` (production rejects `SMP_CORS_ORIGINS=*` and requires auth) |
| `SMP_DATABASE_URL` | `sqlite:///./data/desk.db` (dev) or `postgresql+psycopg://user:pass@host/db` (prod) |
| `SMP_AUTH_JWT_SECRET` | Shared with the web app; the API verifies the bearer tokens Auth.js mints after sign-in (≥ 32 chars) |
| `SMP_ADMIN_EMAILS` | Comma-separated emails granted the admin role (run desk, edit universe, desk defaults) |
| `SMP_API_KEY` | Optional machine credential; admin endpoints also accept it as `X-API-Key` (cron, scripts) |
| `SMP_RATE_LIMIT_DEFAULT` / `_RUNS` / `_WRITES` | Per-IP (anonymous) or per-user limits, e.g. `120/minute`, `5/minute`, `60/minute` |
| `SMP_LOG_JSON=true` | Structured one-line JSON logs with request ids |
| `SMP_MAX_UNIVERSE_SIZE` | Hard cap on tickers per universe/run (default 60) |
| `SMP_INGEST_CONCURRENCY` | Parallel tickers during ingest (default 4) |
| `SMP_HTTP_TIMEOUT` / `SMP_LLM_TIMEOUT` | Per-request timeouts in seconds |
| `SMP_RUN_HISTORY_LIMIT` | Oldest runs beyond this count are pruned (default 200) |

Blank values (`KEY=`) are treated as unset. Invalid values (unknown log level, appetite, out-of-range numbers) fail fast at startup.

Get keys from [Finnhub](https://finnhub.io/), [NewsAPI](https://newsapi.org/), [OpenAI](https://platform.openai.com/), [Anthropic](https://console.anthropic.com/), or [Cursor](https://cursor.com/dashboard).

## Tests and linting

```powershell
cd backend
ruff check . ; ruff format --check .
pytest

cd ..\frontend
npm run typecheck
npm run build
```

The same checks run in CI (`.github/workflows/ci.yml`) on Python 3.11 and 3.12, plus a Docker image build.

## Docker

```powershell
copy .env.example .env
docker compose up --build
```

Desk: [http://localhost:3810](http://localhost:3810) · API: [http://localhost:8810](http://localhost:8810). Both images are multi-stage, run as non-root users, and expose Docker health checks. The web container waits for the API to report healthy.

## Deploying as a public site

The production stack runs on one VPS behind Caddy with automatic TLS:

```
Browser ──HTTPS──▶ Caddy ──▶ /api/v1/*            ──▶ FastAPI (api:8000)
                         ──▶ everything else       ──▶ Next.js (web:3000), incl. Auth.js /api/auth/*
                                                        │            │
                                                     Postgres ◀──────┘   nightly pg_dump → volume
```

One origin, so there is no CORS and no API key in the browser. Auth.js owns identity and the session cookie; after sign-in it mints a one-hour HS256 token (`aud=desk-api`) that the browser sends as `Authorization: Bearer`, and FastAPI verifies it with the shared `SMP_AUTH_JWT_SECRET`. No header means anonymous, read-only access.

### Access model

| Who | Can |
|---|---|
| Anonymous | Read the book, tape, idea pages, run history for any venue. Rate-limited per IP. |
| Signed in | Everything above, plus a personal workspace: preferred venue, risk appetite (the shared run is re-ranked with `apply_policy` from the chief analyst's raw output — no new agents or vendor calls), watchlist with coverage requests. |
| Admin (`SMP_ADMIN_EMAILS`) | Trigger runs, edit the analyzed universe per venue, set desk defaults, see coverage requests. `X-API-Key` remains a machine credential for cron and scripts. |

Users get a personal **watchlist**, not a personal analyzed universe, so run cost stays under admin control. Watchlisted tickers outside coverage surface on `/admin` as demand.

### First deploy

1. Point a DNS `A`/`AAAA` record at the VPS and open ports 80 and 443. Install Docker with the compose plugin.
2. Clone the repo, then `cp deploy/.env.production.example deploy/.env.production` and fill it in. Generate `AUTH_SECRET`, `SMP_AUTH_JWT_SECRET`, and `POSTGRES_PASSWORD` with `openssl rand -base64 48`. Put your own email in `SMP_ADMIN_EMAILS`.
3. Register OAuth apps and paste the client ids/secrets:
   - Google: redirect URI `https://DOMAIN/api/auth/callback/google`. The consent screen asks for privacy and terms URLs — use `https://DOMAIN/privacy` and `https://DOMAIN/terms`, which ship with the app.
   - GitHub: callback URL `https://DOMAIN/api/auth/callback/github`.
   - Email links: a [Resend](https://resend.com) API key and a verified sender in `AUTH_RESEND_FROM`.
4. `./deploy/deploy.sh` — builds the images, runs `alembic upgrade head` against Postgres, starts Caddy/web/api/backup, and waits for health checks.
5. Open `https://DOMAIN`, sign in with an admin email, go to **Admin**, set the universe, and press **Run desk now**. Set `SMP_SCHEDULER_HOURS` for unattended refreshes.

Subsequent deploys are `git pull && ./deploy/deploy.sh` (or enable `.github/workflows/deploy.yml`, which SSHes in and runs the script after CI passes; it needs the `DEPLOY_HOST`, `DEPLOY_USER`, `DEPLOY_SSH_KEY`, and `DEPLOY_PATH` secrets).

### Operations

- **One uvicorn worker.** Desk runs, the SSE event bus, and the rate-limiter store are process-local. Scale by running one API container per desk.
- **Migrations** live in `backend/alembic/`. The API also runs `alembic upgrade head` on boot, so a SQLite desk created before Alembic is adopted in place. To add a column: edit `app/db.py`, run `python -m alembic revision -m "…"` inside `backend/`, and fill in the migration.
- **Backups.** The `backup` container writes a compressed `pg_dump` to the `pg-backups` volume daily and keeps `BACKUP_KEEP_DAYS` (14). Restore with `gunzip -c desk-….dump.gz | docker compose -f docker-compose.prod.yml exec -T postgres pg_restore -U desk -d desk --clean`.
- **Logs.** Caddy writes JSON access logs to the `caddy-logs` volume; the API emits one JSON object per line with `request_id`; every response carries `X-Request-ID`.
- **Health.** `/api/v1/health` verifies the database and reports `active_run_id`, `auth` (token verification configured), LLM/live-data status, and the build version.
- **Rate limits** answer `429` with `Retry-After`. Health and the SSE stream are exempt.
- **Security posture.** Production refuses to boot without `SMP_AUTH_JWT_SECRET` or `SMP_API_KEY`; the admin role is decided server-side from the email allowlist, never from token claims; cookies are `HttpOnly`/`Secure`/`SameSite=Lax`; Postgres and the app containers are not published; secrets live only in `deploy/.env.production` (git-ignored).

Operational behaviour to know:

- `POST /api/v1/runs` returns **202** with the run stub and **409** (with the active `run_id`) if a run is already executing — the UI attaches to it automatically, including for anonymous viewers.
- Runs interrupted by a restart are marked `failed` on the next boot; nothing stays `running` forever.
- `GET /api/v1/book?market_id=&appetite=` always returns the latest **completed** book for the venue; a failed run never blanks the desk. Older runs stored before raw recommendations were kept are served as-is (no re-ranking).

## Markets

The desk is **venue-scoped**. Pick a country and exchange in the header (saved to your account when signed in, to your browser otherwise). Admins edit each venue's universe on **Admin** and choose the default venue anonymous visitors see first.

India is a first-class example: **NSE** (`RELIANCE.NS`) and **BSE** (`RELIANCE.BO`) are separate books, priced in INR, with clocks on `Asia/Kolkata`. US filings still come from SEC EDGAR; other venues lean on licensed news plus exchange disclosures.

Default market: `SMP_DEFAULT_MARKET=us` (or `in-nse`, `in-bse`, `uk-lse`, …).

- **No scraping of Bloomberg, Reuters, Yahoo, etc.** Those terms of service forbid it. Use licensed APIs and EDGAR.
- **Recommendations are research ratings**, not buy/sell tickets. Invalidation conditions are required.
- **News is lagged.** By the time a headline is public it is often in the price. The product is a briefing book, not an alpha engine.
- **Heuristic fallback is first-class**, so the desk never depends on a model vendor to function.

## Project layout

```
backend/app
  main.py            FastAPI app factory, middleware, error handlers, lifespan
  api.py             HTTP routes: public book, admin mutations, /me workspace, SSE
  auth.py            Bearer-token verification; optional_user / require_user / require_admin
  ratelimit.py       Per-IP / per-user rate limits as FastAPI dependencies
  config.py          Typed settings (pydantic-settings); fails fast on bad config
  observability.py   Logging setup, request-id middleware, access log
  db.py              SQLModel tables (universe, runs, settings, users, preferences, watchlist)
  store.py           Engine, Alembic bootstrap, settings rows, workspace helpers
  ingest.py          Data hub with retrying HTTP helper and demo fallback
  policy.py          Deterministic desk policy
  agents/            Orchestrator (keeps raw recs for re-policy), LLM adapter, analysts, scoring
  data/              Bundled fixtures (US + international)
backend/alembic      Migrations (0001 desk baseline, 0002 users + Auth.js tables)
frontend/src
  auth.config.ts     Auth.js providers, JWT/session callbacks, API-token minting (edge-safe)
  auth.ts            Auth.js instance with the Postgres adapter
  middleware.ts      Redirects /workspace and /admin for anonymous / non-admin visitors
  components/        WorkspaceProvider (venue, appetite, watchlist), UserMenu, DeskBoard, …
  app/               Desk, research, runs, idea, workspace, admin, signin, privacy, terms
deploy/              Caddyfile, .env.production.example, deploy.sh
docker-compose.prod.yml  Caddy + web + api + Postgres + nightly backup
```

## Disclaimer

Equity Research Desk is for research and education. It does not consider your objectives, finances, or risk tolerance. Do not treat output as a recommendation to buy, sell, or hold any security. You are responsible for your own investment decisions.
