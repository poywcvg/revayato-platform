#!/bin/sh
set -eu

ENV_FILE="${1:-.env.production}"
COMPOSE_FILE="compose.production.yaml"
BACKUP_DIR="${BACKUP_DIR:-./backups}"
TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
TARGET="$BACKUP_DIR/revayato-$TIMESTAMP.dump"
TEMP_TARGET="$TARGET.partial"
MEDIA_TARGET="$BACKUP_DIR/revayato-media-$TIMESTAMP.tar.gz"
MEDIA_TEMP_TARGET="$MEDIA_TARGET.partial"

if [ ! -f "$ENV_FILE" ]; then
  echo "Missing $ENV_FILE." >&2
  exit 1
fi

mkdir -p "$BACKUP_DIR"
umask 077

docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" exec -T postgres \
  sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --format=custom --no-owner --no-acl' \
  > "$TEMP_TARGET"

mv "$TEMP_TARGET" "$TARGET"

docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" exec -T backend \
  sh -c 'tar -C /app/media -czf - .' \
  > "$MEDIA_TEMP_TARGET"
mv "$MEDIA_TEMP_TARGET" "$MEDIA_TARGET"

printf '%s\n%s\n' "$TARGET" "$MEDIA_TARGET"
