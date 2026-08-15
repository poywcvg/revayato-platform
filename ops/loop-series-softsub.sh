#!/usr/bin/env bash
# Keep serial series softsub running across SubtitleStar cooldowns.
set -euo pipefail
LOG=/tmp/serial-softsub-loop.log
PASS=0
while true; do
  PASS=$((PASS + 1))
  echo "$(date -u +%FT%TZ) PASS=$PASS start" | tee -a "$LOG"
  docker compose --env-file .env.production -f compose.production.yaml exec -T backend \
    python /app/scripts/serial_series_softsub.py --episode-limit 200 --pause-seconds 45 --wait-circuit \
    2>&1 | tee -a "$LOG"
  # Stop when a full pass attached nothing and did not block (likely exhausted).
  if tail -n 5 "$LOG" | grep -q "SERIAL_SOFTSUB_DONE"; then
    DONE_LINE=$(grep 'SERIAL_SOFTSUB_DONE' "$LOG" | tail -n1)
    echo "$(date -u +%FT%TZ) $DONE_LINE" | tee -a "$LOG"
    if echo "$DONE_LINE" | grep -Eq "blocked': 0" && echo "$DONE_LINE" | grep -Eq "attached': 0"; then
      echo "$(date -u +%FT%TZ) exhausted — stopping" | tee -a "$LOG"
      break
    fi
  fi
  echo "$(date -u +%FT%TZ) PASS=$PASS sleeping 90s before next attempt" | tee -a "$LOG"
  sleep 90
done
