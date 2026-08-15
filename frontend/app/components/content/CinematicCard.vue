<script setup lang="ts">
import type { Movie } from '~/types'
import { englishCatalogTitle } from '~/utils/displayNames'

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
const genreLabel = computed(() => props.item.genres[0]?.title || (props.item.type === 'movie' ? 'فیلم' : 'سریال'))
const cardRating = computed(() => {
  const ratings = props.item.ratings || []
  return ratings.find(entry => entry.source === 'imdb')
    || ratings.find(entry => entry.source === 'tmdb')
    || ratings.find(entry => entry.source !== 'site')
    || null
})
</script>

<template>
  <article class="cinematic-card memory-card performance-card group relative min-w-0 overflow-hidden rounded-[1.35rem]">
    <NuxtLink :to="detailPath" class="block min-w-0" :aria-label="`مشاهده جزئیات ${displayTitle}`" @click="trackRecommendationSelection">
      <CinematicImage
        :src="item.poster_url"
        :alt="`پوستر ${displayTitle}`"
        ratio="poster"
        :priority="priority"
        image-class="memory-card__poster transition-transform duration-500 ease-out group-hover:scale-[1.04]"
        :fallback-label="`پوستر ${displayTitle} در دسترس نیست`"
      >
        <div class="memory-card__veil pointer-events-none absolute inset-0" aria-hidden="true" />

        <div class="pointer-events-none absolute right-2.5 top-2.5 z-10 flex max-w-[calc(100%-3.5rem)] flex-col items-end gap-1.5">
          <span
            v-if="item.imdb_rank"
            class="rounded-md bg-[#f5c518] px-1.5 py-0.5 text-[10px] font-black tabular-nums text-night-950 shadow-sm"
            dir="ltr"
          >IMDb #{{ item.imdb_rank }}</span>
          <span class="memory-card__type">{{ item.type === 'movie' ? 'فیلم' : 'سریال' }}</span>
          <DubSubtitleBadge
            v-if="item.is_dubbed || item.has_subtitle"
            :is-dubbed="item.is_dubbed"
            :has-subtitle="item.has_subtitle"
            icons-only
            dark
          />
        </div>

        <RatingBadge
          v-if="cardRating"
          :rating="cardRating"
          compact
          class="pointer-events-none absolute bottom-3 left-2.5 z-10"
        />

        <span class="memory-card__play pointer-events-none absolute bottom-3 right-2.5 z-10 grid size-9 place-items-center rounded-full bg-primary-500 text-night-950 sm:size-10 sm:translate-y-1 sm:opacity-0 sm:transition sm:duration-300 sm:group-hover:translate-y-0 sm:group-hover:opacity-100">
          <CinematicIcon name="play" class="size-4 translate-x-px sm:size-4.5" filled />
        </span>

        <div
          v-if="summary"
          class="cinematic-card__synopsis memory-card__synopsis pointer-events-none absolute inset-x-0 bottom-0 z-10 hidden px-3.5 pb-14 pt-12 sm:block"
          aria-hidden="true"
        >
          <p class="line-clamp-3 text-[11px] font-semibold leading-5 text-[rgb(var(--palette-ink-rgb)/94%)]">{{ summary }}</p>
        </div>

        <div v-if="item.progress_percent" class="absolute inset-x-0 bottom-0 z-20 h-1 bg-line/35">
          <div class="h-full rounded-l-full bg-primary-500" :style="{ width: `${item.progress_percent}%` }" />
        </div>
      </CinematicImage>

      <div class="memory-card__body">
        <p v-if="reason" class="mb-1 line-clamp-2 text-[10px] font-bold leading-4 text-primary-300">{{ reason }}</p>
        <h3 class="memory-card__title font-latin" dir="ltr">{{ displayTitle }}</h3>
        <div class="memory-card__meta">
          <span v-if="item.year" class="tabular-nums">{{ item.year }}</span>
          <span v-if="item.year" class="memory-card__dot" aria-hidden="true" />
          <span class="truncate">{{ genreLabel }}</span>
        </div>
      </div>
    </NuxtLink>

    <WatchlistButton :id="item.id" :slug="item.slug" :content-type="item.type" dark icon-only class="absolute left-2.5 top-2.5 z-30 rounded-xl" />
  </article>
</template>

<style scoped>
.memory-card {
  isolation: isolate;
  background:
    linear-gradient(180deg, color-mix(in srgb, var(--theme-bg-elevated) 55%, transparent), transparent 42%),
    var(--theme-bg-surface);
  border: 1px solid color-mix(in srgb, var(--theme-border) 88%, transparent);
  box-shadow: 0 10px 28px rgb(0 0 0 / 12%);
  transition:
    transform 220ms cubic-bezier(.22, 1, .36, 1),
    border-color 200ms ease,
    box-shadow 220ms ease;
}

.memory-card:focus-within {
  border-color: color-mix(in srgb, var(--theme-accent-primary) 42%, var(--theme-border));
  box-shadow: 0 18px 36px rgb(0 0 0 / 22%);
  transform: translateY(-4px);
}

.memory-card__veil {
  background:
    linear-gradient(to top, rgb(var(--palette-void-rgb) / 88%) 0%, rgb(var(--palette-void-rgb) / 18%) 42%, transparent 68%),
    linear-gradient(135deg, rgb(var(--palette-sand-rgb) / 8%), transparent 40%);
}

.memory-card__type {
  display: inline-flex;
  max-width: 100%;
  align-items: center;
  border-radius: .65rem;
  padding: .28rem .55rem;
  font-size: .625rem;
  font-weight: 900;
  letter-spacing: .02em;
  color: rgb(var(--palette-ink-rgb) / 92%);
  background: color-mix(in srgb, var(--theme-bg-main) 55%, transparent);
  -webkit-backdrop-filter: blur(8px);
  backdrop-filter: blur(8px);
  box-shadow: inset 0 0 0 1px rgb(var(--palette-ink-rgb) / 10%);
}

.memory-card__play {
  box-shadow: 0 8px 20px rgb(0 0 0 / 28%);
}

.memory-card__body {
  padding: .8rem .85rem .95rem;
}

.memory-card__title {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: .8125rem;
  font-weight: 900;
  letter-spacing: -.01em;
  color: var(--theme-text-primary);
  transition: color 160ms ease;
}

.memory-card:focus-within .memory-card__title {
  color: var(--theme-accent-primary);
}

@media (hover: hover) and (pointer: fine) {
  .memory-card:hover {
    border-color: color-mix(in srgb, var(--theme-accent-primary) 42%, var(--theme-border));
    box-shadow: 0 18px 36px rgb(0 0 0 / 22%);
    transform: translateY(-4px);
  }

  .memory-card:hover .memory-card__title {
    color: var(--theme-accent-primary);
  }
}

.memory-card__subtitle {
  display: none;
  margin-top: .2rem;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: .6875rem;
  font-weight: 700;
  color: var(--theme-text-muted);
}

.memory-card__meta {
  display: flex;
  min-width: 0;
  align-items: center;
  gap: .45rem;
  margin-top: .4rem;
  font-size: .6875rem;
  font-weight: 600;
  color: var(--theme-text-secondary);
}

.memory-card__dot {
  width: .25rem;
  height: .25rem;
  flex: none;
  border-radius: 999px;
  background: var(--theme-border);
}

@media (min-width: 640px) {
  .memory-card__body {
    padding: .95rem 1rem 1.05rem;
  }

  .memory-card__title {
    font-size: .95rem;
  }

  .memory-card__subtitle {
    display: block;
  }

  .memory-card__meta {
    font-size: .75rem;
  }
}

:global(html[data-theme="light"] .memory-card) {
  border-color: var(--theme-border);
  box-shadow: var(--theme-shadow-card);
}

:global(html[data-theme="light"] .memory-card:focus-within) {
  border-color: color-mix(in srgb, var(--theme-accent-primary) 42%, var(--theme-border));
  box-shadow: var(--theme-shadow-float);
}

@media (hover: hover) and (pointer: fine) {
  :global(html[data-theme="light"] .memory-card:hover) {
    border-color: color-mix(in srgb, var(--theme-accent-primary) 42%, var(--theme-border));
    box-shadow: var(--theme-shadow-float);
  }
}

@media (prefers-reduced-motion: reduce) {
  .memory-card,
  .memory-card__poster,
  .memory-card__play {
    transition: none;
  }
}
</style>
