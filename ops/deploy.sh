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

# Stage the latest built APK into ./downloads so the one-shot downloads-seed
# service can copy it into the downloads_data volume Caddy serves at /downloads.
# APKs are gitignored, so we never commit them — they come from a local build
# (android-app/dist/) or, if GITHUB_REPO is set, the latest GitHub Release asset.
ROOT_DIR=$(cd "$(dirname "$0")/.." && pwd)
STAGE_DIR="$ROOT_DIR/downloads"
mkdir -p "$STAGE_DIR"
staged=0
# 1) Newest locally-built APK (primary — no network/keys required).
newest=$(ls -1t "$ROOT_DIR"/android-app/dist/*.apk 2>/dev/null | head -n1)
if [ -n "$newest" ]; then
  cp -f "$newest" "$STAGE_DIR/"
  echo "Staged local APK: $(basename "$newest")"
  staged=1
# 2) Fall back to the frontend public copy if the dist build is missing.
elif [ -d "$ROOT_DIR/frontend/public/downloads" ]; then
  for f in "$ROOT_DIR"/frontend/public/downloads/*.apk; do
    [ -e "$f" ] || continue
    cp -f "$f" "$STAGE_DIR/"
    echo "Staged frontend APK: $(basename "$f")"
    staged=1
  done
fi
# 3) Optional GitHub Release fetch (only if explicitly configured).
if [ "$staged" -eq 0 ] && [ -n "${GITHUB_REPO:-}" ]; then
  asset_url=$(curl -fsSL "https://api.github.com/repos/$GITHUB_REPO/releases/latest" \
    | grep -m1 '"browser_download_url".*\.apk"' | sed -E 's/.*"browser_download_url": *"([^"]+)".*/\1/')
  if [ -n "$asset_url" ]; then
    curl -fsSL -o "$STAGE_DIR/$(basename "$asset_url")" "$asset_url"
    echo "Staged GitHub release APK: $(basename "$asset_url")"
    staged=1
  fi
fi
if [ "$staged" -eq 0 ]; then
  echo "WARNING: no APK found to stage (checked android-app/dist, frontend/public/downloads, GITHUB_REPO). The /app download link will 404 until one is provided." >&2
fi

# Copy staged APKs into the downloads_data volume Caddy serves.
docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" run --rm downloads-seed

docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" ps
