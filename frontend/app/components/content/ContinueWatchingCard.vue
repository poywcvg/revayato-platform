<script setup lang="ts">
import type { Movie } from '~/types'

const props = defineProps<{ item: Movie }>()
const { trackContinueWatching } = useAnalyticsEvent()
const currentEpisode = computed(() => props.item.episodes?.find(episode => (episode.progress_percent || 0) > 0 && !episode.is_watched) || props.item.episodes?.find(episode => !episode.is_watched))
const watchLabel = computed(() => props.item.type === 'series' && currentEpisode.value
  ? `فصل ${currentEpisode.value.season_number || 1} · قسمت ${currentEpisode.value.episode_number}`
  : `${props.item.progress_percent}٪ تماشا شده`)

function continueWatching() {
  trackContinueWatching(props.item, props.item.progress_percent)
}
</script>

<template>
  <NuxtLink :to="{ path: `/watch/${item.slug}`, query: { type: item.type } }" class="performance-card group block min-w-0 overflow-hidden rounded-2xl bg-surface ring-1 ring-line transition-[transform,box-shadow] duration-200 hover:-translate-y-0.5 hover:shadow-xl hover:shadow-black/30 hover:ring-primary-500/40" @click="continueWatching">
    <div class="relative aspect-video overflow-hidden bg-slate-900">
      <NuxtImg :src="item.backdrop_url" :alt="`ادامه تماشای ${item.title}`" class="h-full w-full object-cover opacity-80 transition-transform duration-300 group-hover:scale-[1.025]" loading="lazy" decoding="async" fetchpriority="low" sizes="(max-width: 640px) 90vw, 320px" />
      <div class="absolute inset-0 bg-gradient-to-t from-night-950 via-transparent to-black/10" />
      <span class="cinema-glow absolute inset-0 m-auto grid size-12 place-items-center rounded-full bg-primary-500 text-night-950 transition group-hover:scale-110"><CinematicIcon name="resume" class="size-6" /></span>
      <span class="absolute right-3 top-3 rounded-lg bg-slate-950/85 px-2 py-1 text-[10px] font-bold text-slate-200">{{ item.type === 'series' ? 'سریال' : 'فیلم' }}</span>
      <div class="absolute inset-x-0 bottom-0 h-1.5 bg-white/15"><div class="h-full rounded-l-full bg-primary-500" :style="{ width: `${item.progress_percent}%` }" /></div>
    </div>
    <div class="flex items-center justify-between gap-3 p-4"><div class="min-w-0"><h3 class="truncate font-black text-white">{{ item.title }}</h3><p class="mt-1 text-xs text-slate-400">{{ watchLabel }}</p></div><span class="inline-flex shrink-0 items-center gap-1 text-xs font-black text-energy-300">ادامه بده<CinematicIcon name="arrow-left" class="size-4" /></span></div>
  </NuxtLink>
</template>
