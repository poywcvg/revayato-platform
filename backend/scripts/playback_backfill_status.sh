#!/bin/bash
# Progress of the one-off full playback backfill (six sharded containers).
# Usage: bash backend/scripts/playback_backfill_status.sh
cd "$(dirname "$0")/../.." || exit 1
DC="docker compose --env-file .env.production -f compose.production.yaml"

echo "== shards still running =="
docker ps --format '{{.Names}}\t{{.Status}}' | grep '^backfill-' || echo "  (none — the backfill has finished)"

echo
echo "== summary line from each shard =="
for c in $(docker ps -a --format '{{.Names}}' | grep '^backfill-' | sort); do
  line=$(docker logs "$c" 2>&1 | grep 'playback verify:' | tail -1)
  printf '  %-22s %s\n' "$c" "${line:-still running}"
done

echo
echo "== catalog coverage =="
$DC exec -T postgres psql -U revayato -d revayato -c "
SELECT 'movies' AS kind, playback_mode, count(*),
       count(*) FILTER (WHERE video_url = '') AS no_link
  FROM catalog_movie WHERE is_published GROUP BY 1,2
UNION ALL
SELECT 'episodes', playback_mode, count(*),
       count(*) FILTER (WHERE video_url = '')
  FROM catalog_episode WHERE is_published GROUP BY 1,2
ORDER BY 1,3 DESC;"

echo "== repair queue =="
$DC exec -T postgres psql -U revayato -d revayato -c "
SELECT reason, status, count(*) FROM catalog_playbacksourcegap
 GROUP BY 1,2 ORDER BY 3 DESC LIMIT 12;"
