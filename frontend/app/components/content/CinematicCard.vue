<script setup lang="ts">
import type { Movie } from '~/types'
import { englishCatalogTitle } from '~/utils/displayNames'

/**
 * The catalog's one title card: a framed poster with subtitle / dub / play
 * marks stacked in its corner, then the year, the English title and the
 * IMDb + Revayato ratings under it. On hover the poster turns over to the
 * synopsis and genres.
 */
const props = withDefaults(defineProps<{
  item: Movie
  priority?: boolean
  reason?: string
}>(), {
  priority: false,
  reason: '',
})

const detailPath = computed(() => `/${props.item.type === 'movie' ? 'movies' : 'series'}/${props.item.slug}`)
const { trackRecommendationClick } = useAnalyticsEvent()

function trackRecommendationSelection() {
  if (props.reason) trackRecommendationClick(props.item)
}

const summary = computed(() => (props.item.description || '').replace(/\s+/g, ' ').trim())
const displayTitle = computed(() => englishCatalogTitle(props.item))
const genres = computed(() => (props.item.genres || []).slice(0, 3).map(genre => genre.title).filter(Boolean))
const kindLabel = computed(() => (props.item.type === 'movie' ? 'فیلم' : 'سریال'))

const externalRating = computed(() => {
  const ratings = props.item.ratings || []
  return ratings.find(entry => entry.source === 'imdb')
    || ratings.find(entry => entry.source === 'tmdb')
    || ratings.find(entry => entry.source !== 'site')
    || null
})
const externalLabel = computed(() => {
  const source = externalRating.value?.source
  return source === 'imdb' ? 'IMDb' : source === 'tmdb' ? 'TMDB' : (source || '').toUpperCase()
})

const communityRating = computed(() => {
  if (props.item.site_rating && (props.item.site_rating_count ?? 0) > 0) {
    return Number(props.item.site_rating).toFixed(1).replace(/\.0$/, '')
  }
  return siteRating(props.item.ratings || [])?.displayValue || ''
})

// Downloadable titles also stream through the player (directly or via the gateway).
const playable = computed(() => Boolean(props.item.has_downloads || props.item.hls_url))
</script>

<template>
  <article class="cc-card group">
    <NuxtLink :to="detailPath" class="cc-card__link" :aria-label="`مشاهده جزئیات ${displayTitle}`" @click="trackRecommendationSelection">
      <div class="cc-card__poster">
        <CinematicImage
          :src="item.poster_url"
          :alt="`پوستر ${displayTitle}`"
          ratio="poster"
          :priority="priority"
          image-class="cc-card__img"
          :fallback-label="`پوستر ${displayTitle} در دسترس نیست`"
        >
          <span v-if="item.imdb_rank" class="cc-card__rank tabular-nums" dir="ltr">IMDb #{{ item.imdb_rank }}</span>

          <span v-if="item.has_subtitle || item.is_dubbed || playable" class="cc-card__marks">
            <span v-if="item.has_subtitle" class="cc-card__mark" title="زیرنویس فارسی">
              <CinematicIcon name="captions" class="size-3.5" />
              <span class="sr-only">زیرنویس فارسی</span>
            </span>
            <span v-if="item.is_dubbed" class="cc-card__mark" title="دوبله فارسی">
              <CinematicIcon name="audio" class="size-3.5" />
              <span class="sr-only">دوبله فارسی</span>
            </span>
            <span v-if="playable" class="cc-card__mark" title="پخش آنلاین">
              <CinematicIcon name="play" class="size-3.5" />
              <span class="sr-only">پخش آنلاین</span>
            </span>
          </span>

          <div class="cc-card__overlay" aria-hidden="true">
            <p v-if="summary" class="cc-card__summary">{{ summary }}</p>
            <p class="cc-card__genres">
              <span>{{ kindLabel }}</span>
              <span v-for="genre in genres" :key="genre">{{ genre }}</span>
            </p>
          </div>

          <div v-if="item.progress_percent" class="cc-card__progress">
            <div :style="{ width: `${item.progress_percent}%` }" />
          </div>
        </CinematicImage>
      </div>

      <div class="cc-card__info">
        <p v-if="reason" class="cc-card__reason" :title="reason">{{ reason }}</p>
        <!-- Every row always renders (empty when there is no data) so every card in a
             grid or rail has exactly the same height. -->
        <div dir="ltr" class="cc-card__text">
          <span class="cc-card__year tabular-nums">{{ item.year ? `(${item.year})` : '\u00A0' }}</span>
          <h3 class="cc-card__title font-latin" :title="displayTitle">{{ displayTitle }}</h3>
          <p class="cc-card__ratings tabular-nums">
            <span v-if="externalRating" class="cc-card__rating">
              <span class="cc-card__source" :class="`is-${externalRating.source}`">{{ externalLabel }}</span>{{ externalRating.displayValue }}<small>/10</small>
            </span>
            <span v-if="communityRating" class="cc-card__rating" title="امتیاز کاربران روایتو">
              <img src="/favicon.svg?v=2" alt="روایتو" class="cc-card__brand" width="14" height="14" loading="lazy">{{ communityRating }}<small>/10</small>
            </span>
          </p>
        </div>
      </div>
    </NuxtLink>

    <WatchlistButton :id="item.id" :slug="item.slug" :content-type="item.type" icon-only class="cc-card__save" />
  </article>
</template>

<style scoped>
.cc-card {
  --cc-warm: var(--theme-accent-primary);
  --cc-warm-ink: var(--theme-on-accent);
  position: relative;
  min-width: 0;
  height: 100%;
  border-radius: 0.9rem;
  background: color-mix(in srgb, var(--theme-bg-elevated) 82%, transparent);
  box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--theme-border) 70%, transparent);
  transition: background-color 160ms ease, box-shadow 160ms ease;
}


.cc-card__link {
  display: flex;
  height: 100%;
  min-width: 0;
  flex-direction: column;
  gap: 0.6rem;
  border-radius: inherit;
  padding: 0.55rem 0.55rem 0.7rem;
}

.cc-card__link:focus-visible {
  outline: 2px solid var(--cc-warm);
  outline-offset: 2px;
}

.cc-card__poster {
  overflow: hidden;
  border-radius: 0.6rem;
  background: var(--theme-bg-surface);
}

.cc-card__poster :deep(.cc-card__img) {
  transition: transform 240ms ease, opacity 300ms ease;
}

/* Poster chrome. No backdrop-filter on anything that repeats per card: a grid
   of them turns every scrolled frame into dozens of backdrop reads on mobile. */
.cc-card__rank {
  position: absolute;
  z-index: 10;
  inset-block-start: 0.4rem;
  inset-inline-start: 0.4rem;
  border-radius: 0.35rem;
  background: #f5c518;
  padding: 0.1rem 0.35rem;
  color: #000;
  font-family: system-ui, sans-serif;
  font-size: 0.6875rem;
  font-weight: 900;
}

.cc-card__marks {
  position: absolute;
  z-index: 10;
  inset-block-start: 0.4rem;
  inset-inline-end: 0.4rem;
  display: flex;
  flex-direction: column;
  gap: 0.3rem;
}

.cc-card__mark {
  display: grid;
  width: 1.5rem;
  height: 1.5rem;
  place-items: center;
  border-radius: 999px;
  background: rgb(0 0 0 / 66%);
  color: #fff;
}

.cc-card__overlay {
  position: absolute;
  z-index: 5;
  inset: 0;
  display: none;
  flex-direction: column;
  justify-content: flex-end;
  gap: 0.55rem;
  background: linear-gradient(to top, rgb(0 0 0 / 92%) 0%, rgb(0 0 0 / 78%) 55%, rgb(0 0 0 / 35%) 100%);
  padding: 2.5rem 0.7rem 0.75rem;
  opacity: 0;
  transition: opacity 180ms ease;
}

.cc-card__summary {
  display: -webkit-box;
  overflow: hidden;
  color: rgb(255 255 255 / 92%);
  font-size: 0.75rem;
  font-weight: 600;
  line-height: 1.75;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 5;
}

.cc-card__genres {
  display: flex;
  flex-wrap: wrap;
  gap: 0.3rem;
}

.cc-card__genres span {
  border-radius: 999px;
  background: rgb(255 255 255 / 14%);
  padding: 0.1rem 0.5rem;
  color: #fff;
  font-size: 0.6875rem;
  font-weight: 800;
}

.cc-card__genres span:first-child {
  background: var(--cc-warm);
  color: var(--cc-warm-ink);
}

.cc-card__progress {
  position: absolute;
  z-index: 20;
  inset-inline: 0;
  inset-block-end: 0;
  height: 0.25rem;
  background: rgb(0 0 0 / 45%);
}

.cc-card__progress div {
  height: 100%;
  background: var(--cc-warm);
}

/* Info under the poster: read left-to-right like the English title it carries. */
.cc-card__info {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: 0.25rem;
  padding-inline: 0.15rem;
}

.cc-card__reason {
  overflow: hidden;
  color: var(--cc-warm);
  font-size: 0.6875rem;
  font-weight: 700;
  line-height: 1.6;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.cc-card__text {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: 0.2rem;
  /* Leaves room for the bookmark that sits at the row's end. */
  padding-inline-end: 2rem;
  text-align: left;
}

.cc-card__year {
  height: 1.1rem;
  color: var(--theme-text-muted);
  font-size: 0.6875rem;
  font-weight: 600;
  line-height: 1.1rem;
}

.cc-card__title {
  overflow: hidden;
  height: 1.2rem;
  color: var(--theme-text-primary);
  font-size: 0.8125rem;
  font-weight: 700;
  line-height: 1.2rem;
  text-overflow: ellipsis;
  white-space: nowrap;
  unicode-bidi: plaintext;
  transition: color 160ms ease;
}

.cc-card__ratings {
  display: flex;
  height: 1.25rem;
  overflow: hidden;
  align-items: center;
  gap: 0.6rem;
  margin-top: 0.15rem;
  color: var(--theme-text-primary);
  font-size: 0.75rem;
  font-weight: 700;
  white-space: nowrap;
}

.cc-card__rating {
  display: inline-flex;
  align-items: center;
  gap: 0.3rem;
}

.cc-card__rating small {
  margin-inline-start: -0.2rem;
  color: var(--theme-text-muted);
  font-size: 0.6875rem;
  font-weight: 700;
}

.cc-card__source {
  border-radius: 0.2rem;
  background: var(--theme-text-muted);
  padding: 0 0.2rem;
  color: var(--theme-bg-main);
  font-family: system-ui, sans-serif;
  font-size: 0.5625rem;
  font-weight: 900;
  line-height: 1.5;
}

.cc-card__source.is-imdb {
  background: #f5c518;
  color: #000;
}

.cc-card__brand {
  width: 0.9rem;
  height: 0.9rem;
}

/* Bookmark: bottom corner of the info block, across from the title. */
.cc-card__save {
  position: absolute;
  z-index: 30;
  inset-block-end: 0.6rem;
  inset-inline-start: 0.55rem;
  width: 2rem !important;
  height: 2rem !important;
  min-height: 0 !important;
  border-radius: 0.6rem !important;
}

.cc-card__save :deep(svg) {
  width: 1rem;
  height: 1rem;
}

.cc-card__save[aria-pressed="true"] {
  background: var(--cc-warm) !important;
  color: var(--cc-warm-ink) !important;
}

@media (min-width: 640px) {
  .cc-card__overlay { display: flex; }
}

@media (hover: hover) and (pointer: fine) {
  .cc-card:hover {
    background: color-mix(in srgb, var(--theme-bg-elevated) 94%, var(--cc-warm) 6%);
    box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--cc-warm) 40%, transparent);
  }

  .cc-card:hover .cc-card__poster :deep(.cc-card__img) { transform: scale(1.04); }
  .cc-card:hover .cc-card__overlay { opacity: 1; }
  .cc-card:hover .cc-card__title { color: var(--cc-warm); }

  /* The bookmark stays out of the way until the card is in focus, unless saved. */
  .cc-card__save:not([aria-pressed="true"]) { opacity: 0; transition: opacity 160ms ease; }
  .cc-card:hover .cc-card__save,
  .cc-card:focus-within .cc-card__save { opacity: 1; }
}

.cc-card:focus-within .cc-card__overlay { opacity: 1; }

@media (prefers-reduced-motion: reduce) {
  .cc-card,
  .cc-card__overlay,
  .cc-card__title,
  .cc-card__poster :deep(.cc-card__img) { transition: none; }

  .cc-card:hover .cc-card__poster :deep(.cc-card__img) { transform: none; }
}
</style>
