#!/usr/bin/env bash
# Keep syncing WebVTT for newly imported movies until coverage stalls.
set -euo pipefail
LOG=/tmp/sync-new-movie-subs-loop.log
PASS=0
while true; do
  PASS=$((PASS+1))
  echo "$(date -u +%FT%TZ) PASS=$PASS" | tee -a "$LOG"
  docker compose --env-file .env.production -f compose.production.yaml exec -T backend \
    env PYTHONPATH=/app python /tmp/sync_new_movies_player_subs.py --hours 18 --pause-seconds 14 --ss-timeout 40 --no-ffmpeg \
    2>&1 | tee -a "$LOG" | tee /tmp/sync-new-movie-subs.log
  DONE=$(grep 'NEW_MOVIES_PLAYER_SOFTSUB_DONE' "$LOG" | tail -n1 || true)
  echo "$(date -u +%FT%TZ) $DONE" | tee -a "$LOG"
  # Stop when a pass attaches nothing and isn't blocked
  if echo "$DONE" | grep -Eq "ss_or_ffmpeg': 0" && echo "$DONE" | grep -Eq "blocked': 0"; then
    echo "$(date -u +%FT%TZ) coverage stalled — stopping" | tee -a "$LOG"
    break
  fi
  sleep 60
done
# restore beat
docker compose --env-file .env.production -f compose.production.yaml start catalog-beat || true
