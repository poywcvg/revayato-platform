# TMDB integration

TMDB access is backend-only. Nuxt calls the staff API under `/api/admin/`; the
Django TMDB client adds the credential when it contacts TMDB. No TMDB secret is
part of runtime config, page payloads, browser storage, or frontend logs.

## Metadata flow

1. Staff searches from `/admin/movies`.
2. Django requests localized search results from TMDB.
3. Preview fetches movie details with credits, videos, images, release dates,
   external IDs, and translations without saving anything.
4. Import creates a draft by default and maps the normalized metadata.
5. Sync refreshes an existing row by `tmdb_id`. Fields recorded as manually
   edited are skipped unless staff explicitly enables overwrite.

The mapper stores localized and original titles, fallback overview, release
date/year, runtime, genre and country relations, language data, certification,
IMDb/TMDB identifiers, raw and full image paths, official YouTube trailer,
top cast, selected crew, directors, writers, production companies, TMDB rating,
vote count, popularity, and SEO defaults.

## Reliability and proxy behavior

Requests use a timeout and bounded exponential backoff for transient network,
rate-limit, and 5xx failures. Error responses are normalized and never contain
credentials. `TMDB_PROXY_URL` takes precedence; standard HTTPS/HTTP proxy
variables are supported as fallbacks. Logs include only the endpoint path,
attempt, outcome, and whether a proxy was used.

## Duplicate and overwrite rules

Candidates are detected by TMDB ID, IMDb ID, generated slug, and normalized
title plus release year. A non-exact candidate returns a conflict until staff
selects the existing local movie to link. Existing manual fields—including an
intentional empty value—are protected. `overwrite_manual` is an explicit,
audited exception.

Import and sync actions are written to `MovieSyncAudit` with actor, action,
changed/skipped fields, dry-run state, and timestamp. Audit rows are read-only
in Django Admin.

## Troubleshooting

- `tmdb_not_configured`: verify the server environment and restart only the
  affected application services through the approved deployment process.
- upstream/network error: check egress, DNS, proxy reachability, and the TMDB
  service status; do not log or paste the token.
- duplicate conflict: preview the candidate and link the correct existing row.
- publish blockers: attach licensed media, verify rights, and mark media ready.

Rotate any credential that has been pasted into chat, tickets, shell history,
or logs before using the integration.
