# Subtitle pipeline (movies & series)

Revayato keeps **video** and **toggleable Persian text** on separate paths so the
online player can always show something readable while SoftSub WebVTT is prepared.

## Sources (ordered)

| Priority | Source | What it provides | Player behaviour |
| ---: | --- | --- | --- |
| 1 | Soft CDN / current playable file ffmpeg demux | WebVTT extracted from the embedded Persian track | Exact-source, highest sync confidence |
| 2 | SubtitleStar ZIP/SRT (IMDb + release match) | Toggleable Persian WebVTT | First fallback when the file has no usable track |
| 3 | Subzone.ir / Subf2m ZIP/SRT | Toggleable Persian WebVTT | Next release-matched fallback |
| 4 | Film2Media HardSub encode | Persian burned into the picture | Version with `burnedInSubtitles` |
| 5 | Film2Media Dub | Persian audio | Version `dub`; sidecar VTT when paired |

Online playback reports send the exact current `source_url` to the urgent queue. The
worker tries the embedded Persian stream first and validates that the result contains
valid WebVTT cues and Persian text. This is both the fastest trustworthy result and the
most accurately timed because cues and video come from the same container. If demux
fails or no embedded text stream exists, the worker falls back to **SubtitleStar**, then
**Subzone**. Remote ffmpeg does not block the HTTP request, so the player keeps playing
and polls until the track lands. HardSub-only titles go directly to provider sidecars.

## Stored track shape (`Movie.subtitle_tracks` / `Episode.subtitle_tracks`)

Only relative storage keys are persisted (never CDN URLs in `key`):

```json
{
  "id": "fa-subtitlestar-1",
  "label": "فارسی",
  "language": "fa",
  "key": "catalog/subtitles/tmdb-123-fa-subtitlestar.vtt",
  "default": true,
  "source_url": "https://…/Soft/….mkv",
  "provider": "subtitlestar",
  "source_priority": 2,
  "sync_confidence": "release-match",
  "imdb_id": "tt0000000",
  "season_number": 1,
  "episode_number": 3
}
```

| Field | Required | Notes |
| --- | --- | --- |
| `id` | yes | Stable id for the player menu |
| `label` | yes | UI label (Persian) |
| `language` | yes | BCP-47-ish; `fa` preferred |
| `key` | yes | Object key under media storage |
| `default` | no | Default on when version has cues |
| `source_url` | recommended | Exact/family Soft encode this VTT was timed against |
| `provider` | no | `softsub-ffmpeg`, `subtitlestar`, or `subzone` |
| `source_priority` | no | `1` embedded, `2` SubtitleStar, `3` next provider |
| `sync_confidence` | no | `exact-source`, `release-match`, or `title-fallback` |
| `season_number` / `episode_number` | series | Required for episode binding |

## Public API track shape

Serializers rewrite `key` → absolute `src` via `media_url()` and drop `key`:

```json
{
  "id": "fa-subtitlestar-1",
  "label": "فارسی",
  "language": "fa",
  "src": "https://revayato.com/media/catalog/subtitles/….vtt",
  "default": true,
  "source_url": "https://…/Soft/….mkv",
  "provider": "subtitlestar"
}
```

## Player wiring

1. `watch/[slug].vue` builds `activeSubtitleSourceTracks` (episode VTT → sidecar URL → movie tracks).
2. `buildPlaybackVersions()` pairs tracks to Soft/Hard/Dub encodes (`source_url` / Soft fingerprint).
3. Default version preference: SoftSub+cues → SoftSub/HardSub burned → Dub.
4. `VideoPlayer` loads WebVTT cues from `src`, defaults Persian track **on**, and polls SoftSub until cues appear.

## Backfill jobs

- Import: `scripts/import_missing_myf2m_batch.py` (prefer dub/sub encodes).
- Movies: Celery `extract_movie_softsub_task` / `scripts/serial_movie_softsub.py` (embedded-first).
- Series: `extract_series_softsub_task` / `scripts/serial_series_softsub.py`.
- Circuit breaker `catalog:subtitlestar:circuit-open` pauses lookups after 403/429.

## Availability flags

`has_subtitle` is true when download links imply Soft/HardSub **or** a WebVTT track exists.
`is_dubbed` follows dub encodes. Public badges must not claim SoftSub cues until `subtitle_tracks` has a usable `key`.
