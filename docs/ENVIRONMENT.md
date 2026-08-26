# Environment variables

See also `.env.example` and `.env.production.example`. Values below are the
application settings that matter for catalog crawl, provider import, and
playback.

## Core Django / JWT

Documented in the root env examples (`DJANGO_*`, `JWT_*`, database, Redis,
email, CDN bases). `JWT_REFRESH_TOKEN_DAYS` defaults to 400 days; refresh-token
rotation renews that window for active users, so browser sessions survive
restarts until explicit logout, site-data removal, account revocation, or a
full 400 days without a visit.

## Avasarami (`AVASARAMI_*`)

Licensed archive import connector. CAPTCHA login is not automated.

| Variable | Purpose | Required |
| --- | --- | --- |
| `AVASARAMI_BASE_URL` | Provider base URL | No (default set) |
| `AVASARAMI_LOGIN_URL` | Login page URL | No |
| `AVASARAMI_MOVIES_URL` | Movies listing URL | No |
| `AVASARAMI_SERIES_URL` | Series listing URL | No |
| `AVASARAMI_AUTH_TYPE` | `bearer_token` / `api_key` / `cookie_session` / `feed` / `username_password` | Prefer explicit |
| `AVASARAMI_API_TOKEN` | Bearer or API key | For token auth |
| `AVASARAMI_COOKIE` | Authorized long-lived session cookie | For cookie auth |
| `AVASARAMI_USERNAME` / `AVASARAMI_PASSWORD` | Only if non-CAPTCHA server login exists | Usually unused |
| `AVASARAMI_TIMEOUT_SECONDS` | HTTP timeout | No |
| `AVASARAMI_RATE_LIMIT_PER_MINUTE` | Client-side request ceiling | No |
| `AVASARAMI_VERIFY_SSL` | TLS verification | No (default True) |

## Catalog download crawler (`CATALOG_LINK_PROVIDER` / `MYF2M_*`)

Default link crawlers are **Film2Media** (`https://www.myf2m.info`) and
**Dornatv** (`https://dornatv.com`) — public CDN download HTML, no VIP login.
`CATALOG_LINK_PROVIDERS` defaults to `myf2m,dornatv`.

Hollywood-only policy: Iranian titles are excluded (`CATALOG_EXCLUDE_IRANIAN`)
and titles missing from the crawler source may be deleted
(`CATALOG_DELETE_WHEN_PROVIDER_MISSING`). Reconcile with:

```bash
python manage.py reconcile_myf2m_catalog
```

| Variable | Purpose | Required |
| --- | --- | --- |
| `CATALOG_LINK_PROVIDER` | Primary crawler (`myf2m`) | No |
| `CATALOG_LINK_PROVIDERS` | Ordered merge list | No (default `myf2m,dornatv`) |
| `MYF2M_BASE_URL` | Film2Media base URL | No (default `https://www.myf2m.info`) |
| `MYF2M_TIMEOUT_SECONDS` | HTTP timeout | No |
| `MYF2M_RATE_LIMIT_PER_MINUTE` | Client rate ceiling | No |
| `MYF2M_VERIFY_SSL` | TLS verify (must be True in production) | No |
| `MYF2M_AUTO_CRAWL_ON_PUBLISH` | Auto enqueue crawl on publish | No (default True) |
| `MYF2M_CRAWL_INTERVAL_SECONDS` | Sleep between `catalog-crawler` rounds | No (default 21600) |
| `MYF2M_BULK_CRAWL_DELAY_SECONDS` | Delay between per-title detail fetches | No (default 3.0) |
| `MYF2M_REFRESH_DELAY_SECONDS` | Delay between refresh re-crawls per title | No (default 0.7) |
| `MYF2M_SERIES_REFRESH_LIMIT` | Series re-crawled per round for new episodes | No (default 150) |
| `MYF2M_SERIES_REFRESH_YEAR_MIN` | Skip series older than this year during refresh | No (default 2023, 0 = all) |
| `MYF2M_MOVIE_REFRESH_LIMIT` | Movies re-crawled per round for new qualities | No (default 200) |
| `MYF2M_MOVIE_REFRESH_ORDER` | Movie refresh selection: `stale` or `popular` | No (default `stale`) |
| `MYF2M_SIZE_WORKERS` / `MYF2M_SIZE_TIMEOUT_SECONDS` / `MYF2M_SIZE_PROBE_BATCH` / `MYF2M_SIZE_LIMIT` | Download-size backfill probes | No |
| `CATALOG_EXCLUDE_IRANIAN` | Skip/purge Iranian cinema/TV | No (default True) |
| `CATALOG_DELETE_WHEN_PROVIDER_MISSING` | Delete titles not found on crawler | No (default True) |

## Dornatv (`DORNATV_*`)

WordPress BartarTheme crawler for [`https://dornatv.com`](https://dornatv.com).
Public CDN download boxes are merged with Film2Media via `CATALOG_LINK_PROVIDERS`.

| Variable | Purpose | Required |
| --- | --- | --- |
| `DORNATV_BASE_URL` | Site base URL | No (default `https://dornatv.com`) |
| `DORNATV_TIMEOUT_SECONDS` | HTTP timeout | No |
| `DORNATV_RATE_LIMIT_PER_MINUTE` | Client rate ceiling | No |
| `DORNATV_VERIFY_SSL` | TLS verify (must be True in production) | No |
| `DORNATV_USER_AGENT` | Crawler User-Agent | No |
| `DORNATV_MAX_RESULTS_PER_LOOKUP` | Search result cap | No |
| `DORNATV_REST_PER_PAGE` | WP REST page size | No |
| `DORNATV_IMPORT_ENABLED` | Celery tick importer | No (default True) |
| `DORNATV_IMPORT_MOVIES_PER_TICK` | Movies per beat tick | No |
| `DORNATV_IMPORT_SERIES_PER_TICK` | Series per beat tick | No |
| `DORNATV_IMPORT_YEAR_START` | Year walk start | No |
| `DORNATV_IMPORT_YEAR_END` | Year walk end | No |
| `DORNATV_IMPORT_CHECKPOINT` | Checkpoint file path | No |
