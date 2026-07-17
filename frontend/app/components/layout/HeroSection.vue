<script setup lang="ts">
import type { Movie } from '~/types'
const props = defineProps<{ item: Movie }>()
const modalOpen = ref(false)
const requestedMode = ref<'full' | 'trailer'>('full')
const detailPath = computed(() => `/${props.item.type === 'movie' ? 'movies' : 'series'}/${props.item.slug}`)
const watchPath = computed(() => `/watch/${props.item.slug}?mode=${requestedMode.value}&type=${props.item.type}`)
const restricted = computed(() => props.item.age_rating === '18+')
const { personalizationEnabled } = usePersonalizationState()

function requestPlay(mode: 'full' | 'trailer') {
  requestedMode.value = mode
  if (restricted.value) modalOpen.value = true
  else void navigateTo(watchPath.value)
}

function confirmPlay() {
  modalOpen.value = false
  void navigateTo(`${watchPath.value}&confirmed=1`)
}
</script>

<template>
  <section class="relative isolate min-h-[580px] overflow-hidden bg-night-950 text-white sm:min-h-[680px] lg:rounded-b-[2.5rem]">
    <CinematicImage :src="item.backdrop_url" :alt="`نمایی از ${item.title}`" ratio="backdrop" priority class="absolute inset-0 -z-30 h-full w-full" image-class="object-center" :fallback-label="`تصویر پس‌زمینه ${item.title} در دسترس نیست`" />
    <div class="cinematic-hero-overlay absolute inset-0 -z-20" aria-hidden="true" />
    <div class="page-shell flex min-h-[580px] items-center pb-24 pt-12 sm:min-h-[680px] sm:pb-32 sm:pt-16">
      <div class="max-w-3xl">
        <div class="flex flex-wrap items-center gap-2">
          <span class="crimson-glow rounded-full bg-crimson px-3 py-1.5 text-xs font-black text-ink">پیشنهاد شروع امشب</span>
          <span class="rounded-full bg-night-800/90 px-3 py-1.5 text-xs font-bold ring-1 ring-white/15">{{ item.type === 'movie' ? 'فیلم سینمایی' : 'سریال' }}</span>
          <AgeRatingBadge :rating="item.age_rating" />
          <DubSubtitleBadge :is-dubbed="item.is_dubbed" :has-subtitle="item.has_subtitle" dark />
        </div>
        <p class="mt-5 text-xs font-bold tracking-[0.16em] text-energy-300 sm:mt-8 sm:text-sm sm:tracking-[0.2em]" dir="ltr">{{ item.original_title }}</p>
        <h1 class="mt-1 max-w-3xl text-4xl font-black leading-tight tracking-tight sm:text-6xl lg:text-7xl xl:text-8xl">{{ item.title }}</h1>
        <p class="mt-4 line-clamp-3 max-w-2xl text-sm leading-7 text-slate-300 sm:mt-5 sm:text-base sm:leading-8">{{ item.description }}</p>
        <div class="mt-4 flex flex-wrap items-center gap-x-4 gap-y-2 text-xs text-slate-300 sm:mt-5 sm:gap-x-5 sm:text-sm">
          <span class="inline-flex items-center gap-1.5 font-black text-white"><CinematicIcon name="star" class="size-5 text-primary-400" filled />{{ item.rating.toFixed(1) }}</span>
          <span class="tabular-nums">{{ item.year }}</span><span>{{ item.type === 'series' ? `${item.seasons_count || 1} فصل` : `${item.duration_minutes} دقیقه` }}</span><span class="hidden sm:inline">{{ item.genres.map(genre => genre.title).join('، ') }}</span><span class="hidden md:inline">{{ item.language }}</span>
        </div>
        <p class="mt-7 hidden text-[11px] font-black text-slate-400 sm:block">از اینجا شروع کن</p>
        <div class="mt-5 grid grid-cols-[minmax(0,1fr)_auto_auto] gap-2.5 sm:mt-2 sm:flex sm:flex-wrap sm:gap-3">
          <button type="button" class="action-primary col-span-3 w-full sm:w-auto" @click="requestPlay('full')"><CinematicIcon name="play" class="size-5" filled />تماشا کن</button>
          <NuxtLink :to="detailPath" class="action-discovery"><CinematicIcon name="info" class="size-5" />مشاهده جزئیات</NuxtLink>
          <button type="button" class="inline-flex min-h-12 items-center gap-2 rounded-[.875rem] bg-night-800/90 px-4 text-sm font-black text-white ring-1 ring-white/14 transition hover:bg-night-700" @click="requestPlay('trailer')"><CinematicIcon name="trailer" class="size-5 text-energy-300" />تریلر</button>
          <WatchlistButton :id="item.id" :slug="item.slug" :content-type="item.type" dark compact-on-mobile />
        </div>
        <div class="mt-6 inline-flex max-w-full items-center gap-3 rounded-2xl bg-night-950/85 px-4 py-3 ring-1 ring-energy-300/15"><span class="grid size-9 shrink-0 place-items-center rounded-xl bg-energy-500/14 text-energy-300"><CinematicIcon name="ai" class="size-5" /></span><div class="min-w-0"><p class="text-[10px] font-bold text-slate-500">{{ personalizationEnabled ? 'دلیل پیشنهاد هوشمند' : 'انتخاب هوشمند آزمایشی' }}</p><p class="truncate text-xs font-bold text-slate-200">{{ item.recommendation_reason || 'بر اساس علاقه‌مندی‌های تو' }}</p></div></div>
      </div>
    </div>
  </section>
  <ConfirmAdultContentModal :open="modalOpen" :title="item.title" @close="modalOpen = false" @confirm="confirmPlay" />
</template>
