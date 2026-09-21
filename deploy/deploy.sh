#!/usr/bin/env bash
# Pull, rebuild, migrate, and (re)start the production stack on the VPS.
#
#   ./deploy/deploy.sh            # deploy current branch
#   ./deploy/deploy.sh --no-pull  # rebuild what is checked out
#
# Requires: docker (compose v2), git, deploy/.env.production filled in.
set -euo pipefail

cd "$(dirname "$0")/.."

ENV_FILE="deploy/.env.production"
COMPOSE=(docker compose --env-file "$ENV_FILE" -f docker-compose.prod.yml)

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Missing $ENV_FILE — copy deploy/.env.production.example and fill it in." >&2
  exit 1
fi

if [[ "${1:-}" != "--no-pull" ]]; then
  git pull --ff-only
fi

echo "==> Building images"
"${COMPOSE[@]}" build --pull

echo "==> Starting database"
"${COMPOSE[@]}" up -d postgres
"${COMPOSE[@]}" run --rm --no-deps api python -m alembic upgrade head

echo "==> Rolling out api, web, caddy, backup"
"${COMPOSE[@]}" up -d --remove-orphans

echo "==> Waiting for health"
for _ in $(seq 1 30); do
  if "${COMPOSE[@]}" ps --format json | grep -q '"Health":"unhealthy"'; then
    echo "A service is unhealthy:" >&2
    "${COMPOSE[@]}" ps >&2
    exit 1
  fi
  if ! "${COMPOSE[@]}" ps --format json | grep -q '"Health":"starting"'; then
    break
  fi
  sleep 2
done

"${COMPOSE[@]}" ps
echo "==> Pruning dangling images"
docker image prune -f >/dev/null
echo "Deployed."
