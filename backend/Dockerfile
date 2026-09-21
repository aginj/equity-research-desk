# syntax=docker/dockerfile:1.7

# ---- build stage: resolve and install dependencies into an isolated prefix -------------
FROM python:3.12-slim AS build

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /src
COPY pyproject.toml ./
COPY app ./app
RUN pip install --prefix=/install .

# ---- runtime stage: minimal image, non-root, healthcheck ---------------------------------
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    SMP_DATABASE_URL=sqlite:////app/data/desk.db \
    SMP_LOG_JSON=true \
    PORT=8000

RUN groupadd --system desk && useradd --system --gid desk --home-dir /app --shell /usr/sbin/nologin desk \
    && mkdir -p /app/data && chown -R desk:desk /app

COPY --from=build /install /usr/local
COPY --chown=desk:desk app /app/app
COPY --chown=desk:desk alembic.ini /app/alembic.ini
COPY --chown=desk:desk alembic /app/alembic

WORKDIR /app
USER desk
EXPOSE 8000
VOLUME ["/app/data"]

# Liveness/readiness: /api/v1/health also verifies the database.
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD ["python", "-c", "import sys,urllib.request;sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health', timeout=4).status==200 else 1)"]

# NOTE: exactly one worker. Desk runs and the SSE event bus are process-local; scale by
# running one container per desk, not by adding workers.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --workers 1 --proxy-headers --no-server-header --timeout-graceful-shutdown 20"]
