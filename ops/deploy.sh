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
# Workers run the exact same backend image with different commands. Building
# that Dockerfile once avoids duplicate image exports and large disk spikes on
# the small production host.
docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" build --pull backend
docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" build --pull frontend
docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" up -d --remove-orphans
docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" ps
