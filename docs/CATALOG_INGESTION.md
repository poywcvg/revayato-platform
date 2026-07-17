# Automated catalog ingestion

The production stack can keep the catalog current without publishing
unverified content. The pipeline is deliberately split into two stages:

1. `catalog-worker` calls the configured metadata provider and creates or
   updates movies as drafts.
2. A licensed media workflow writes relative object keys to the media manifest.
   Only entries with `rights_verified=true`, a ready HLS key, a poster, and a
   description can be auto-published.

The sync implementation uses TMDB's official `discover/movie` endpoint for the
release window and `movie/{movie_id}` with credits/external IDs for details.
See the [TMDB discover documentation](https://developer.themoviedb.org/reference/discover-movie)
and [movie details documentation](https://developer.themoviedb.org/reference/movie-details).

## Configuration

Set these values in `.env.production`:

```env
TMDB_API_TOKEN=replace-with-your-provider-token
TMDB_API_BASE_URL=https://api.themoviedb.org/3
TMDB_LANGUAGE=fa-IR
TMDB_REGION=
CATALOG_MEDIA_MANIFEST=/run/catalog-media-manifest.json
CATALOG_SYNC_ENABLED=False
CATALOG_SYNC_INTERVAL_HOURS=6
CATALOG_PUBLISH_INTERVAL_SECONDS=300
CATALOG_AUTO_PUBLISH=False
```

`TMDB_API_KEY` is also accepted for providers that issue a v3 key. Keep both
credentials private. Enable `CATALOG_SYNC_ENABLED` only after a successful
manual dry run. `CATALOG_AUTO_PUBLISH` should remain `False` until the licensed
media and rights workflow has been tested.

## Media manifest

The manifest contains keys, never full URLs. Copy
`backend/catalog-media-manifest.example.json` to a private deployment file and
mount it at the configured path:

```json
{
  "movies": {
    "12345": {
      "hls_key": "movies/12345/hls/master.m3u8",
      "poster_key": "movies/12345/images/poster.webp",
      "backdrop_key": "movies/12345/images/backdrop.webp",
      "subtitles": [
        {
          "language": "fa",
          "label": "فارسی",
          "key": "movies/12345/subtitles/fa.vtt",
          "default": true
        }
      ],
      "rights_verified": true,
      "auto_publish": true
    }
  }
}
```

The HLS segments, images, and subtitles must already exist in the configured
storage/CDN. This service does not scrape or download copyrighted video from
unlicensed sources. A future provider adapter can populate the same manifest
after it completes an authorized upload/transcode job.

## Manual operations

```bash
# Import metadata and keep all changes as drafts.
docker compose --env-file .env.production -f compose.production.yaml exec backend \
  python manage.py sync_catalog --no-publish

# Preview a sync without saving anything.
docker compose --env-file .env.production -f compose.production.yaml exec backend \
  python manage.py sync_catalog --dry-run

# Publish only entries that pass rights/media checks.
docker compose --env-file .env.production -f compose.production.yaml exec backend \
  python manage.py publish_ready_catalog
```

The `catalog-worker` and `catalog-beat` services run these operations on their
configured schedule. Every run is visible in Django Admin under **Catalog sync
runs**, including counts and per-title errors. Newly discovered titles remain
drafts when the metadata provider is unavailable, the manifest is missing, or
rights have not been verified.
