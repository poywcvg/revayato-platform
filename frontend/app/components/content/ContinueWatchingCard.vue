<script setup lang="ts">
import type { Movie } from '~/types'
import { englishCatalogTitle } from '~/utils/displayNames'

const props = defineProps<{ item: Movie }>()
const { trackContinueWatching } = useAnalyticsEvent()
const currentEpisode = computed(() => props.item.episodes?.find(episode => episode.id === props.item.resume_episode_id)
  || props.item.episodes?.find(episode => (episode.progress_percent || 0) > 0 && !episode.is_watched)
  || props.item.episodes?.find(episode => !episode.is_watched))
const displayTitle = computed(() => englishCatalogTitle(props.item))
const roundedProgress = computed(() => Math.min(100, Math.max(0, Math.round(props.item.progress_percent || 0))))
const remainingLabel = computed(() => {
  const duration = props.item.resume_duration_seconds || (props.item.duration_minutes || 0) * 60
  if (!duration) return `${roundedProgress.value.toLocaleString('fa-IR')}٪ تماشا شده`
  const remainingMinutes = Math.max(1, Math.ceil((duration * (100 - roundedProgress.value) / 100) / 60))
  return `${remainingMinutes.toLocaleString('fa-IR')} دقیقه مانده`
})
const watchLabel = computed(() => props.item.type === 'series' && currentEpisode.value
  ? `فصل ${(currentEpisode.value.season_number || 1).toLocaleString('fa-IR')} · قسمت ${currentEpisode.value.episode_number.toLocaleString('fa-IR')} · ${remainingLabel.value}`
  : remainingLabel.value)

function continueWatching() {
  trackContinueWatching(props.item, props.item.progress_percent)
}
</script>

<template>
  <NuxtLink :to="{ path: `/watch/${item.slug}`, query: { type: item.type, ...(item.resume_episode_id ? { episode: String(item.resume_episode_id) } : {}) } }" class="cinematic-card performance-card group block min-w-0 overflow-hidden rounded-2xl" @click="continueWatching">
    <div class="theme-media-dark relative aspect-video overflow-hidden bg-night-900">
      <CinematicImage
        :src="item.backdrop_url || item.poster_url"
        :alt="`ادامه تماشای ${displayTitle}`"
        ratio="backdrop"
        class="h-full w-full"
        image-class="opacity-80 transition-transform duration-300 group-hover:scale-[1.025]"
      />
      <div class="absolute inset-0 bg-gradient-to-t from-night-950 via-transparent to-black/10" />
      <span class="absolute inset-0 m-auto grid size-12 place-items-center rounded-full bg-primary-500 text-night-950 shadow-lg shadow-black/25 transition group-hover:scale-105"><CinematicIcon name="resume" class="size-6" /></span>
      <span class="absolute right-3 top-3 rounded-lg bg-black/65 px-2 py-1 text-[10px] font-bold text-slate-200 ring-1 ring-white/10">{{ item.type === 'series' ? 'سریال' : 'فیلم' }}</span>
      <div class="absolute inset-x-0 bottom-0 h-1.5 bg-white/15" role="progressbar" :aria-valuenow="roundedProgress" aria-valuemin="0" aria-valuemax="100" :aria-label="`پیشرفت تماشای ${displayTitle}: ${roundedProgress.toLocaleString('fa-IR')} درصد`"><div class="h-full rounded-l-full bg-primary-500 transition-[width] duration-300" :style="{ width: `${roundedProgress}%` }" /></div>
    </div>
    <div class="flex items-center justify-between gap-3 p-3.5 sm:p-4">
      <div class="min-w-0"><h3 class="truncate font-latin text-sm font-black text-ink sm:text-base" dir="ltr">{{ displayTitle }}</h3><p class="mt-1 text-[11px] text-muted sm:text-xs">{{ watchLabel }}</p></div>
      <span class="inline-flex shrink-0 items-center gap-1 text-xs font-black text-brand">ادامه بده<CinematicIcon name="arrow-left" class="size-4 transition-transform group-hover:-translate-x-0.5" /></span>
    </div>
  </NuxtLink>
</template>
