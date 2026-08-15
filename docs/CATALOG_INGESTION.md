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

Configure the server-only variables described in [ENVIRONMENT.md](ENVIRONMENT.md),
especially `TMDB_READ_ACCESS_TOKEN`, `TMDB_BASE_URL`, the primary/fallback
languages, region, and optional proxy. Keep credentials private. Enable
`CATALOG_SYNC_ENABLED` only after a successful manual dry run.
`CATALOG_AUTO_PUBLISH` should remain disabled until the licensed media and
rights workflow has been tested.

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

## Staff TMDB APIs

Staff JWT (or session) required. Credentials never leave the backend.

```http
GET  /api/admin/tmdb/search/?query=
GET  /api/admin/tmdb/movie/{tmdb_id}/preview/
POST /api/admin/tmdb/movie/{tmdb_id}/import/          # body: { dry_run?, overwrite_manual? }
POST /api/admin/movies/{id}/sync-tmdb/                # body: { dry_run?, overwrite_manual? }
GET  /api/admin/movies/
POST /api/admin/movies/
GET|PATCH|DELETE /api/admin/movies/{id}/
```

Django Admin also exposes bulk “Sync from TMDB” actions on movies.

The `catalog-worker` and `catalog-beat` services run these operations on their
configured schedule. Every run is visible in Django Admin under **Catalog sync
runs**, including counts and per-title errors. Newly discovered titles remain
drafts when the metadata provider is unavailable, the manifest is missing, or
rights have not been verified.

## One-click, cancellable bulk import

Staff can open `/admin/catalog-sync` and choose one of two persistent jobs:

- **Full catalog** streams TMDB's official daily movie-ID export, excludes
  adult/video records, stages IDs in the database, and imports detail records
  in bounded batches. It is intended for the initial backfill and may run for
  many hours or days.
- **Incremental** unions TMDB's movie change list with recently released,
  upcoming, and oldest cached local records. This is the appropriate recurring
  job and keeps the cache inside the configured refresh window.

Only one TMDB job can be active. Each ID is unique within the run and each
movie is upserted by `tmdb_id`, so retries are idempotent. Progress and the
current ID are persisted. Cancel marks the run cooperatively; the worker checks
the flag between titles and stops without killing an in-flight database write.
Transient upstream errors receive bounded retries and one malformed title does
not stop the remaining catalog.
Candidate rows are working-state only and are removed after a terminal outcome;
the compact run counters and capped error summary remain as the audit record.
Late acknowledgements make batches safe to redeliver after a worker crash. A
five-minute watchdog finalizes abandoned cancellations and requeues jobs whose
persisted heartbeat is stale.
Production uses a dedicated AOF-backed, `noeviction` Redis service for Celery;
the disposable application cache cannot evict catalog tasks or checkpoints.

```http
GET  /api/admin/catalog-sync/runs/
POST /api/admin/catalog-sync/runs/                    # { mode: "incremental" }
POST /api/admin/catalog-sync/runs/                    # { mode: "full", confirm_full: true }
GET  /api/admin/catalog-sync/runs/{id}/
POST /api/admin/catalog-sync/runs/{id}/cancel/
```

TMDB supplies metadata, artwork paths, trailers, and identifiers—not movie
files or unrestricted streaming rights. Metadata is draft-first. Automatic
publication still requires a licensed manifest entry, `rights_verified=true`,
a ready HLS object key, poster, and description.

The full ID file is not a full metadata export; the worker calls the official
movie details endpoint for each staged ID. Keep the incremental schedule
enabled so cached data stays current, and review TMDB's current attribution,
cache-retention, rate-limit, and commercial-use terms before production use.

## Persian subtitles (two providers)

Canonical contract and player wiring: [SUBTITLES.md](./SUBTITLES.md).

These roles stay separate:

| Source | Role |
|--------|------|
| [Film2Media / myf2m](https://www.myf2m.info) | Movie and series **video** download / stream links (dub, hardsub, SoftSub encodes). |
| [Dornatv](https://dornatv.com) | Public CDN mirrors (SoftSub, Dubbed, HardSub, NoSub) + page IMDb / plot / poster fallbacks. |
| [SubtitleStar](https://subtitlestar.com/) | **Persian subtitle files only**, usually as ZIP season/movie packs — never the video itself. |

Crawl merges (`coalesce_download_links`) keep every uncovered quality / dub /
hardsub / SoftSub encode across providers and re-crawls. Matching CDN paths
refresh signed URLs; other rows are never wiped by a partial crawl.

`CATALOG_LINK_PROVIDERS=myf2m,dornatv` (default) crawls **both** sites and
merges all qualities. Dornatv labels prefer CDN filenames so `1080p 10bit
x265` stays distinct from plain `1080p`. TMDB (via IMDb) remains the primary
metadata source; Dornatv fills empty description / poster / year / original
title when TMDB left them blank.

### Movies

Playback first tries an embedded SoftSub track from a Film2Media SoftSub
encode (ffmpeg → WebVTT). If that does not yield a usable track, the worker
queries SubtitleStar for a ZIP/SRT match:

- a catalog IMDb id must appear verbatim on the SubtitleStar detail page;
- the release name/source/FPS is matched against the Film2Media playback URL;
- direct SRT/VTT/ASS/SSA files and bounded ZIP archives are accepted;
- archive traversal, encrypted entries, executable files, oversized responses,
  unsupported download hosts, and non-Persian subtitle bodies are rejected;
- Windows-1256 subtitles are normalized to UTF-8 and stored as WebVTT;
- each stored track is bound to its compatible `source_url` (the Film2Media
  encode), so it is not silently shown over a different encode;
- requests are throttled, misses are cached for 24 hours, and HTTP
  403/429/browser challenges open a six-hour circuit breaker.

```bash
python manage.py extract_softsub_tracks \
  --movies-only --missing-only --movie-limit 30 --queue
```

### Series

Film2Media supplies per-episode video URLs. SubtitleStar supplies ZIP packs
that are split onto those episodes for online playback:

- series IMDb id must match the SubtitleStar detail page;
- ZIP members are matched by `S01E01` / `1x01` / فصل‌قسمت markers;
- each episode WebVTT is bound to that episode's Film2Media playable URL;
- if a Film2Media SoftSub encode already yields a track, SubtitleStar is skipped
  for that episode; otherwise the ZIP sidecar fills the gap.

```bash
python manage.py extract_softsub_tracks \
  --series-only --missing-only --series-limit 20 --episode-limit 40 --queue
```

Use `SUBTITLESTAR_ENABLED=False` for an immediate kill switch. The optional
`SUBTITLESTAR_COOKIE` is only for a session the site owner has authorized; the
crawler does not automate Cloudflare challenges or CAPTCHAs. Confirm that
production use and redistribution comply with the provider's current terms
and the subtitle rights applicable to the service.

When a SoftSub encode and SubtitleStar pack disagree on source tags
(BluRay vs WEB-DL), the worker still attaches the best Persian member and binds
it to every playable URL so the online player can show toggleable cues. The
player exposes a ±10s subtitle sync control for residual timing drift. Opening a
movie/series detail or watch page also queues SoftSub extraction when tracks are
missing; the watch player polls `?softsub_poll=1` (no-store) until cues appear.
