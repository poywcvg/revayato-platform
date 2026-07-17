<script setup lang="ts">
import type { Episode, Movie } from '~/types'

const props = defineProps<{ item: Movie }>()
const { trackContinueWatching } = useAnalyticsEvent()
const orderedEpisodes = computed(() => [...(props.item.episodes || [])].sort((a, b) => (a.season_number || 1) - (b.season_number || 1) || a.episode_number - b.episode_number))
const activeEpisode = computed(() => orderedEpisodes.value.find(episode => (episode.progress_percent || 0) > 0 && !episode.is_watched)
  || [...orderedEpisodes.value].reverse().find(episode => episode.is_watched))
const selectedSeason = ref(activeEpisode.value?.season_number || 1)
const seasonNumbers = computed(() => Array.from({ length: props.item.seasons_count || 1 }, (_, index) => index + 1))
const seasonOptions = computed(() => seasonNumbers.value.map(season => ({ value: season, label: `فصل ${season}` })))
const episodes = computed(() => orderedEpisodes.value.filter(episode => (episode.season_number || 1) === selectedSeason.value))
const nextEpisode = computed(() => {
  const activeIndex = orderedEpisodes.value.findIndex(episode => episode.id === activeEpisode.value?.id)
  return activeIndex >= 0 ? orderedEpisodes.value[activeIndex + 1] : orderedEpisodes.value[0]
})
const nextActionLabel = computed(() => activeEpisode.value ? `قسمت بعدی: ${nextEpisode.value?.episode_number}` : `شروع سریال: قسمت ${nextEpisode.value?.episode_number}`)

function watchLink(episode: Episode) {
  return { path: `/watch/${props.item.slug}`, query: { type: 'series', episode: episode.id } }
}

function selectEpisode(episode: Episode) {
  if (episode.progress_percent && !episode.is_watched) trackContinueWatching(props.item, episode.progress_percent)
}
</script>

<template>
  <section id="episodes" class="scroll-mt-40" aria-labelledby="episodes-title">
    <div class="mb-5 flex flex-wrap items-end justify-between gap-3">
      <div>
        <p class="text-xs font-black text-primary-400">تماشای سریال</p>
        <h2 id="episodes-title" class="mt-1 text-2xl font-black text-white">فصل‌ها و قسمت‌ها</h2>
        <p class="mt-2 text-xs leading-6 text-slate-400">{{ item.seasons_count || 1 }} فصل · {{ orderedEpisodes.length }} قسمت در دسترس</p>
      </div>
      <div class="flex flex-wrap items-center gap-2">
        <NuxtLink v-if="nextEpisode" :to="watchLink(nextEpisode)" no-prefetch class="inline-flex min-h-11 items-center gap-2 rounded-xl bg-primary-500 px-3.5 text-xs font-black text-night-950 transition hover:bg-primary-400">
          <CinematicIcon name="fast-forward" class="size-4" />
          {{ nextActionLabel }}
        </NuxtLink>
        <div class="flex min-w-40 items-center gap-2 text-xs font-bold text-slate-400">
          <span>انتخاب فصل</span>
          <UiSelect v-model="selectedSeason" :options="seasonOptions" label="انتخاب فصل" icon="layers" compact class="min-w-28" />
        </div>
      </div>
    </div>

    <div v-if="episodes.length" class="grid gap-3">
      <article v-for="episode in episodes" :key="episode.id" class="group grid gap-4 overflow-hidden rounded-2xl bg-white/[.045] p-3 ring-1 ring-white/10 transition duration-200 hover:bg-white/[.07] hover:ring-primary-400/45 sm:grid-cols-[190px_minmax(0,1fr)_auto] sm:items-center">
        <div class="relative aspect-video overflow-hidden rounded-xl bg-slate-900">
          <NuxtImg :src="episode.thumbnail_url || item.backdrop_url" :alt="`تصویر قسمت ${episode.episode_number}`" class="h-full w-full object-cover opacity-80 transition-transform duration-300 group-hover:scale-[1.03]" loading="lazy" decoding="async" fetchpriority="low" />
          <span class="cinema-glow absolute inset-0 m-auto grid size-10 place-items-center rounded-full bg-primary-500 text-night-950"><CinematicIcon name="play" class="size-5" filled /></span>
          <span v-if="episode.is_watched" class="absolute right-2 top-2 inline-flex items-center gap-1 rounded-lg bg-success px-2 py-1 text-[9px] font-black text-canvas"><CinematicIcon name="check" class="size-3" />دیده شده</span>
          <span v-else-if="nextEpisode?.id === episode.id" class="absolute right-2 top-2 rounded-lg bg-primary-500 px-2 py-1 text-[9px] font-black text-night-950">قسمت بعدی</span>
          <div v-if="episode.progress_percent" class="absolute inset-x-0 bottom-0 h-1.5 bg-white/20"><div class="h-full bg-primary-500" :style="{ width: `${episode.progress_percent}%` }" /></div>
        </div>
        <div class="min-w-0">
          <p class="text-[11px] font-black text-primary-400">فصل {{ episode.season_number || 1 }} · قسمت {{ episode.episode_number }}</p>
          <h3 class="mt-1 font-black text-white">{{ episode.title }}</h3>
          <p class="mt-1 line-clamp-2 text-xs leading-6 text-slate-400">{{ episode.description }}</p>
          <p class="mt-2 text-[11px] text-slate-500">{{ episode.duration_minutes }} دقیقه<span v-if="episode.progress_percent && !episode.is_watched"> · {{ episode.progress_percent }}٪ دیده شده</span></p>
        </div>
        <NuxtLink :to="watchLink(episode)" no-prefetch class="inline-flex min-h-11 shrink-0 items-center justify-center gap-1.5 rounded-xl px-4 text-xs font-black transition" :class="episode.progress_percent && !episode.is_watched ? 'bg-primary-500 text-night-950 hover:bg-primary-400' : 'bg-white/5 text-slate-200 ring-1 ring-white/10 hover:bg-white/10 hover:text-white'" @click="selectEpisode(episode)">
          <CinematicIcon :name="episode.progress_percent && !episode.is_watched ? 'resume' : 'play'" class="size-4" :filled="!episode.progress_percent || episode.is_watched" />{{ episode.progress_percent && !episode.is_watched ? 'ادامه بده' : 'پخش قسمت' }}
        </NuxtLink>
      </article>
    </div>
    <EmptyState v-else title="قسمت‌های این فصل به‌زودی" description="هنوز قسمتی برای این فصل قرار نگرفته است. بعداً دوباره سر بزن." dark />
  </section>
</template>
