<script setup lang="ts">
import type { Movie } from '~/types'

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
</script>

<template>
  <article class="cinematic-card performance-card group relative min-w-0 overflow-hidden rounded-2xl">
    <NuxtLink :to="detailPath" no-prefetch class="block" :aria-label="`مشاهده جزئیات ${item.title}`" @click="trackRecommendationSelection">
      <CinematicImage
        :src="item.poster_url"
        :alt="`پوستر ${item.title}`"
        ratio="poster"
        :priority="priority"
        image-class="transition-transform duration-300 group-hover:scale-[1.025]"
        :fallback-label="`پوستر ${item.title} در دسترس نیست`"
      >
        <div class="absolute inset-0 bg-gradient-to-t from-slate-950/95 via-slate-950/5 to-transparent opacity-90" aria-hidden="true" />

        <div class="absolute right-2 top-2 flex flex-col items-start gap-1.5">
          <span class="cinematic-glass rounded-lg px-2 py-1 text-[10px] font-black text-white">{{ item.type === 'movie' ? 'فیلم' : 'سریال' }}</span>
          <AgeRatingBadge :rating="item.age_rating" />
        </div>

        <RatingBadge :rating="item.rating" compact class="absolute bottom-2 left-2" />

        <span class="cinema-glow cinematic-card__play absolute bottom-2 right-2 grid size-11 place-items-center rounded-full bg-primary-500 text-night-950 transition sm:translate-y-2 sm:opacity-0 sm:group-hover:translate-y-0 sm:group-hover:opacity-100">
          <CinematicIcon name="play" class="size-5 translate-x-px" filled />
        </span>

        <span v-if="reason" class="cinematic-glass absolute inset-x-2 bottom-14 hidden line-clamp-2 rounded-xl px-2.5 py-2 text-[10px] font-bold leading-4 text-primary-200 ring-1 ring-primary-400/15 sm:block">
          {{ reason }}
        </span>
      </CinematicImage>

      <div class="p-3.5">
        <h3 class="truncate text-sm font-black text-slate-50 transition-colors group-hover:text-primary-300 sm:text-base">{{ item.title }}</h3>
        <p class="mt-1 flex items-center gap-2 text-xs text-slate-400">
          <span class="tabular-nums">{{ item.year }}</span>
          <span class="size-1 rounded-full bg-slate-600" />
          <span class="truncate">{{ item.genres[0]?.title }}</span>
        </p>
        <DubSubtitleBadge class="mt-2" :is-dubbed="item.is_dubbed" :has-subtitle="item.has_subtitle" compact dark />
      </div>
    </NuxtLink>

    <WatchlistButton :id="item.id" :slug="item.slug" :content-type="item.type" dark icon-only class="absolute left-2 top-2 z-20 rounded-xl" />

    <div v-if="item.progress_percent" class="absolute inset-x-0 bottom-0 h-1 bg-white/10">
      <div class="h-full rounded-l-full bg-primary-500" :style="{ width: `${item.progress_percent}%` }" />
    </div>
  </article>
</template>
