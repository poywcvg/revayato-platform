# Frontend catalog contract

The Nuxt application stays usable with typed mock data and can switch to the
Django catalog without component changes.

## Runtime mode

```env
NUXT_PUBLIC_API_BASE=/api
NUXT_PUBLIC_MEDIA_CDN_BASE_URL=
NUXT_PUBLIC_CATALOG_SOURCE=mock
```

Set `NUXT_PUBLIC_CATALOG_SOURCE=api` to request the live read-only catalog.
If the API is unreachable or has no published content, Nuxt keeps the mock
catalog visible and offers an explicit retry action. Relative poster, HLS,
subtitle, and media keys are resolved against
`NUXT_PUBLIC_MEDIA_CDN_BASE_URL` (or the same-origin `/media/` fallback).

## Public endpoints

- `GET /api/movies/`
- `GET /api/movies/{slug}/`
- `GET /api/series/`
- `GET /api/series/{slug}/`
- `GET /api/genres/`
- `GET /api/search/?q=`
- `GET /api/trending/?type=all&limit=20`

Movie and series lists accept `q`, `year`, `genre`, `country`, `language`,
`age` (or `age_rating`), `min_rating`, `content_format`, `availability`, `sort`,
`limit` and `offset`. Supported
sort values are `newest`, `rating`, `popular` and `trending`.

Only published movies and series are public. Series detail responses also
exclude draft seasons and draft episodes.

## Frontend normalization

`frontend/app/data/catalogAdapter.ts` converts movie and series responses into
the shared `Movie` type. Missing presentation-only fields receive conservative
fallbacks so UI components do not depend on Django model details. Detail pages
fetch their matching detail endpoint in API mode, including playable episode
URLs when available.

Dubbed, subtitle, uncensored and content-warning metadata remain optional until
the backend schema explicitly stores those values. The adapter does not infer
sensitive metadata from language, country or user behavior.
