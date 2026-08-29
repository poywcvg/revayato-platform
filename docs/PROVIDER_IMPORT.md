# Licensed provider import (Avasarami)

Staff-only framework for importing licensed movie/series files from authorized
providers into the private ArvanCloud archive (`MovieArchiveAsset`). The first
connector is **Avasarami**.

## Provider URLs

| Purpose | URL |
| --- | --- |
| Home | https://avasarami.top/ |
| Login | https://avasarami.top/sign-in/ |
| Movies | https://avasarami.top/movies/ |
| Series | https://avasarami.top/series/ |

## CAPTCHA limitation (critical)

Avasarami’s interactive login page uses CAPTCHA. Revayato **does not**:

- solve CAPTCHA
- bypass CAPTCHA, MFA, DRM, paywalls, or rate limits
- automate browser login when CAPTCHA is present

If only CAPTCHA login is available, validation returns
`requires_interactive_verification=true` with a message asking for an official
API, server token, IP whitelist, export feed, or authorized long-lived session.

## Preferred authorized access

Configure **one** of:

1. Official API + `AVASARAMI_API_TOKEN` (`AVASARAMI_AUTH_TYPE=bearer_token` or `api_key`)
2. Authorized long-lived cookie/session in `AVASARAMI_COOKIE` (`cookie_session`)
3. IP-whitelisted JSON/CSV/XML feed (`feed` — URLs via provider `config` when available)
4. Username/password **only** if the provider later exposes a non-CAPTCHA
   server-to-server login (interactive CAPTCHA login remains blocked)

Secrets stay in environment variables (`ProviderCredential.secret_mode=env`,
`env_prefix=AVASARAMI`). They are never stored in the database, returned by
admin APIs, logged, or exposed to Nuxt `NUXT_PUBLIC_*`.

## Environment variables

See [ENVIRONMENT.md](ENVIRONMENT.md). Load only the secrets needed for the
selected auth type.

## Admin UI

Open `/admin/provider-import` (staff). Features:

- Avasarami card with public URLs and **configured/missing** secret flags
- Validate connection
- CAPTCHA warning when interactive verification is required
- Discover movies/series, import missing files, dry-run, limit, overwrite,
  quality preference
- Job progress, cancel, items table, sanitized logs

## APIs

All under `/api/admin/…`, staff-only:

- `GET/POST /provider-sources/`
- `GET/PATCH /provider-sources/{id}/`
- `POST /provider-sources/{id}/validate/`
- `POST /provider-sources/{id}/discover/`
- `POST /provider-sources/{id}/import/`
- `GET /provider-import/jobs/`
- `GET /provider-import/jobs/{id}/`
- `POST /provider-import/jobs/{id}/cancel/`
- `GET /provider-import/jobs/{id}/items/`
- `GET /provider-import/jobs/{id}/logs/`

Responses never include credentials, cookies, tokens, provider download URLs,
Arvan credentials, or presigned URLs.

## Matching

Movies (and series when returned by the connector):

1. `tmdb_id` exact
2. `imdb_id` exact
3. normalized title + year

Fuzzy title-only matches are not auto-imported. Nothing is auto-published.
Archive overwrite requires `overwrite=true`.

## Transfer pipeline

Authorized provider stream → Celery → multipart upload to private archive →
`MovieArchiveAsset` with object key:

`archive/movies/{movie_id}/source/provider/avasarami/{uuid}/{safe_filename}`

Streaming computes SHA-256, tracks bytes, aborts multipart on failure/cancel,
retries transient storage errors with backoff, and respects
`AVASARAMI_RATE_LIMIT_PER_MINUTE`.

## Listing contract status

Until Avasarami documents a stable server-to-server listing/download API, the
connector raises `ProviderContractUnknown` for list/detail/download methods
after auth succeeds. The admin UI, jobs, matching, and transfer pipeline remain
ready for that contract.

## Troubleshooting

| Symptom | Action |
| --- | --- |
| CAPTCHA / interactive verification | Request official token/cookie/feed; do not automate login |
| Token rejected (401/403) | Rotate token; confirm auth type |
| Cookie rejected | Refresh authorized session from provider ops |
| Contract unknown on discover | Obtain official listing/download API schema |
| Archive exists skipped | Enable overwrite only when intentionally replacing |
| Job stuck | Cancel from UI; check catalog-worker Celery logs |
| Rate limit (429) | Lower `AVASARAMI_RATE_LIMIT_PER_MINUTE` |

## Film2Media discover / crawl

- Discover: `POST /api/admin/catalog/movies/{id}/provider-discover/`
- Crawl downloads: `POST /api/admin/catalog/movies/{id}/provider-crawl-downloads/`
- Approve match: `POST /api/admin/provider-import/jobs/{id}/approve-match/`
- Import/transfer: disabled (`501`) until Milestone 3

Series crawl merges Film2Media + Dornatv download links, stamps
`season_number` / `episode_number` / `quality` on each row, then builds
`Season` / `Episode` rows via `ensure_episodes_from_download_links`.

Production also runs a permanent, low-priority `catalog-crawler` loop. Each
round performs four phases and then sleeps for `MYF2M_CRAWL_INTERVAL_SECONDS`
(30 minutes in the current production environment):

1. **New-title sweep** — scans Film2Media listings with `--new-only
   --require-playback`, rejects trailer/sample media, and imports every title
   that is missing from the catalog (matched by TMDB/IMDb identity).
2. **Series refresh** (`refresh_series_new_episodes.py`) — re-crawls pages of
   existing published series so newly released episodes appear automatically.
3. **Movie refresh** (`refresh_movie_download_links.py`) — re-crawls pages of
   existing published movies so new qualities/dub/hardsub/SoftSub encodes are
   coalesced without wiping current rows.
4. **Size backfill** — bounded myf2m download-size probing.

Configure the request delay, round interval, refresh limits/year filters,
CPU cap, and size-probe concurrency with the `MYF2M_BULK_*`,
`MYF2M_CRAWL_INTERVAL_SECONDS`, `MYF2M_REFRESH_DELAY_SECONDS`,
`MYF2M_SERIES_REFRESH_*`, `MYF2M_MOVIE_REFRESH_*`, and `MYF2M_SIZE_*`
variables.
