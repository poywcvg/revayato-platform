#!/bin/sh
set -eu

ENV_FILE="${1:-.env.production}"
COMPOSE_FILE="compose.production.yaml"

if [ ! -f "$ENV_FILE" ]; then
  echo "Missing $ENV_FILE. Copy .env.production.example and fill in production values." >&2
  exit 1
fi

if grep -q "replace-with" "$ENV_FILE"; then
  echo "Production placeholders are still present in $ENV_FILE." >&2
  exit 1
fi

docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" config >/dev/null
docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" pull postgres redis caddy
docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" build --pull frontend backend
docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" up -d --remove-orphans
docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" ps
