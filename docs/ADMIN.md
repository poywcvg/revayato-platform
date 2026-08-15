# Movie administration

The professional catalog panel is a Nuxt application at `/admin/movies`; it is
separate from Django Admin and uses the Revayato green palette and RTL Persian UI.
Django Admin remains available for low-level operational inspection and audits.

## Access control

Every page uses the `staff` route middleware. Every API endpoint independently
requires an authenticated `is_staff` user and has a dedicated throttle. The
backend check is authoritative; hiding navigation in Nuxt is not treated as a
security boundary.

## Staff workflow

- Search, filter, sort, paginate, and switch between table/card views
  (`/admin/movies`).
- Add from TMDB ID (`افزودن از TMDB`) or create a title manually
  (`/admin/movies/new`).
- Inspect localized metadata, cast, crew, artwork, rating, and duplicate
  warnings before import.
- Import as a draft, link a duplicate, or sync an existing movie.
- Edit movies with sectional forms, including local poster/backdrop upload or
  external image URLs.
- Archive instead of deleting. The DELETE endpoint is intentionally a safe
  archive operation and does not remove the database row or media.

Publishing is rejected server-side unless rights are verified, the media state
is ready, and a licensed HLS object key exists. TMDB import never downloads,
bypasses, or discovers video from unauthorized sources.

## Uploads

Poster and backdrop uploads accept JPEG, PNG, or WebP up to 8 MB. Django image
validation checks the content and storage filenames are generated server-side.
Video, trailer, download, and subtitle media use the existing object-key/media
manifest architecture for public/CDN delivery.

Private original MKV/MP4 masters use the staff archive APIs under
`/api/admin/archive/…`. The browser uploads parts directly to a private
S3-compatible bucket via short-lived presigned URLs; Django never receives the
movie bytes on those endpoints. Configure `ARCHIVE_*` (see
[ENVIRONMENT.md](ENVIRONMENT.md)). Keep the bucket private, expose `ETag` in
bucket CORS, and smoke-test ArvanCloud multipart behavior before production.
Archive storage is not HLS, CDN, or public playback, and is not a sole backup.

## Licensed provider import

Staff can open `/admin/provider-import` to validate Avasarami credentials,
discover titles, and import missing archive files through Celery into private
Object Storage. CAPTCHA login is never automated; configure an official API
token, authorized cookie/session, or feed. See
[PROVIDER_IMPORT.md](PROVIDER_IMPORT.md) and `AVASARAMI_*` in
[ENVIRONMENT.md](ENVIRONMENT.md).

Film2Media (myf2m) provides staff per-title discover/review and download crawl
APIs (`MYF2M_*`, see [ENVIRONMENT.md](ENVIRONMENT.md)). Media transfer is not
enabled yet.

## Safe operations

Use preview/dry-run before a first import or a forced overwrite. Keep overwrite
disabled for routine syncs. Verify the public movie page after publishing, and
use the audit log when investigating unexpected metadata changes.
