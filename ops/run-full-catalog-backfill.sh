#!/bin/sh
set -u
COMPOSE="docker compose --env-file /root/revayato-platform/.env.production -f /root/revayato-platform/compose.production.yaml"
LOG=/var/log/revayato-catalog-backfill.log
{
  echo "=== BACKFILL START $(date -Is) ==="
  echo "--- Phase 1: myf2m link crawl (missing links/qualities) ---"
  $COMPOSE exec -T backend python /app/scripts/crawl_all_myf2m.py --delay 0.22 --no-delete --keep-iranian
  echo "--- Phase 2: TMDB metadata + actors completion ---"
  $COMPOSE exec -T backend python manage.py complete_catalog_metadata --sleep 0.08 --include-unpublished
  echo "--- Phase 3: download box sizes ---"
  $COMPOSE exec -T backend python /app/scripts/backfill_download_sizes.py --workers 12 --timeout 20
  echo "=== BACKFILL DONE $(date -Is) ==="
} >> "$LOG" 2>&1
