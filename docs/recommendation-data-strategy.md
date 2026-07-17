# Recommendation data boundary

The recommendation architecture uses two deliberately separate signal groups:

1. Consented first-party events from inside Revayato.
2. Aggregate site-demand signals without user or session identifiers.

The frontend defaults to `NUXT_PUBLIC_ANALYTICS_TRANSPORT=local` and does not
send events automatically. Personalization is opt-in. Disabling it clears the
local behavior queue and the anonymous session identifier.

`POST /api/events/` accepts the allow-listed event contract only when the
request includes `X-Personalization-Consent: granted`. The server derives the
authenticated user from its own authentication context and never trusts a
client-provided user ID. This endpoint intentionally leaves IP address,
user-agent and device fields empty.

Google Search Console data may only enter the aggregate demand-signal pipeline
for this site's verified property. It must be aggregated by query and period
and must never be joined to a personal profile, anonymous session, browser
history, external search history or fingerprint.

Current mock aggregate records are defined in
`frontend/app/data/mockDemandSignals.ts`. They contain only source, aggregate
query, genre tags, score, optional impression/click counts and reporting period.

## Hybrid ranking pipeline

`frontend/app/utils/recommendationScoring.ts` ranks the mock/API catalog on the
device when personalization is enabled. Its inputs are limited to explicit
preferences, consented first-party events and aggregate site-demand signals.

The prototype considers favorite/disliked genres, selected countries and
languages, playback preference, age-rating preference and content-sensitivity
preference. `reduced` sensitivity only lowers the rank of 18+, uncensored or
warning-heavy titles; it does not censor, delete or hide catalog entries.

Every ranked item includes a short reason suitable for UI display. The current
pipeline has four stages:

1. Collapse noisy events. Repeated views count once per title/day, mutable
   actions keep their latest state, and progress keeps only the furthest point
   per title/session.
2. Build a decayed taste profile. Signals use a 14-day half-life and contribute
   to genre, director, cast, country, language, format, content type, playback,
   duration and release-year preferences. Deep watch, completion, rating and
   explicit likes are stronger than a detail-page view.
3. Score candidates. Editorial quality and platform popularity provide the
   cold-start baseline. Explicit preferences, behavior confidence, recent-title
   similarity and privacy-safe aggregate demand then adjust it. Completed and
   explicitly disliked titles are strongly demoted without erasing the positive
   genre signal learned from a completed title.
4. Diversify the final row with a lightweight maximal-marginal-relevance pass,
   preventing near-identical titles from occupying every slot while preserving
   the highest-relevance item.

Removing a like is represented as `remove_like`; it is intentionally not an
explicit `dislike`. Recommendation-card selections use `recommendation_click`
so the system can measure useful suggestions separately from ordinary catalog
views.

The Django recommendation service mirrors the same principles for authenticated
users and consented anonymous sessions. `GET /api/recommendations/` returns a
bounded unified list with `score`, `reason`, `confidence` and `signals_used`,
while retaining the legacy `movies` and `series` arrays.

## Synchronization and privacy

Local history is retained for on-device ranking even after API synchronization.
Each event has a client-generated `event_id`; a local cursor sends only newer
events and the server treats repeated IDs idempotently. API synchronization is
enabled only when both personalization consent and
`NUXT_PUBLIC_ANALYTICS_TRANSPORT=api` are present. It uses the authenticated JWT
when available and otherwise a random session identifier. Neither path stores
IP address, user-agent, device identity, browser history or fingerprint data.

## Quality checks

The deterministic tests cover explicit preferences, sensitivity, strong
negative feedback, progress de-duplication, unlike/dislike separation, temporal
decay, recent-title similarity, aggregate demand isolation and result diversity.
Production evaluation should additionally monitor recommendation click-through,
watch-start rate, 30/70/100-percent completion, explicit dislike rate, catalog
coverage and diversity. Compare algorithms with consented randomized cohorts;
do not optimize only for clicks, because click-only ranking tends to amplify
misleading artwork and short-lived popularity.
