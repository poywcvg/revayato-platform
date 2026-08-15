#!/usr/bin/env bash
set -euo pipefail
LOG=/tmp/serial-movie-softsub-loop.log
PASS=0
while true; do
  PASS=$((PASS + 1))
  echo "$(date -u +%FT%TZ) PASS=$PASS start" | tee -a "$LOG"
  docker compose --env-file .env.production -f compose.production.yaml exec -T backend \
    python /app/scripts/serial_movie_softsub.py --pause-seconds 30 --wait-circuit \
    2>&1 | tee -a "$LOG"
  DONE_LINE=$(grep 'SERIAL_MOVIE_SOFTSUB_DONE' "$LOG" | tail -n1 || true)
  echo "$(date -u +%FT%TZ) $DONE_LINE" | tee -a "$LOG"
  if echo "$DONE_LINE" | grep -Eq "blocked': 0" && echo "$DONE_LINE" | grep -Eq "attached': 0"; then
    echo "$(date -u +%FT%TZ) movie softsub exhausted — stopping" | tee -a "$LOG"
    break
  fi
  # Also stop when almost nothing left to try
  if echo "$DONE_LINE" | grep -Eq "tried': 0"; then
    echo "$(date -u +%FT%TZ) no eligible movies left — stopping" | tee -a "$LOG"
    break
  fi
  echo "$(date -u +%FT%TZ) sleeping 120s before next pass" | tee -a "$LOG"
  sleep 120
done
