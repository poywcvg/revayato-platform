<script setup lang="ts">
import type { Movie } from '~/types'

const props = defineProps<{ item: Movie }>()
const modalOpen = ref(false)
const requestedMode = ref<'full' | 'trailer'>('full')
const restricted = computed(() => props.item.age_rating === '18+')

function watchPath(confirmed = false) {
  return `/watch/${props.item.slug}?mode=${requestedMode.value}&type=${props.item.type}${confirmed ? '&confirmed=1' : ''}`
}

function requestPlay(mode: 'full' | 'trailer') {
  requestedMode.value = mode
  if (restricted.value) modalOpen.value = true
  else void navigateTo(watchPath())
}
</script>

<template>
  <section class="content-section">
    <div class="relative isolate min-h-[380px] overflow-hidden rounded-3xl bg-slate-950 text-white ring-1 ring-white/10 sm:min-h-[430px] sm:rounded-[2rem]">
      <NuxtImg :src="item.backdrop_url" alt="" class="absolute inset-0 -z-30 h-full w-full object-cover" loading="lazy" decoding="async" fetchpriority="low" sizes="(max-width: 1024px) 100vw, 1100px" />
      <div class="absolute inset-0 -z-20 bg-gradient-to-l from-night-950 via-night-950/85 to-night-900/18" />
      <div class="absolute inset-0 -z-10 bg-gradient-to-t from-night-950 via-transparent to-black/20" />
      <div class="flex min-h-[380px] max-w-2xl flex-col justify-end p-5 sm:min-h-[430px] sm:p-10">
        <div class="flex flex-wrap items-center gap-2"><span class="crimson-glow rounded-full bg-crimson px-3 py-1.5 text-xs font-black text-ink">ویژه این هفته</span><AgeRatingBadge :rating="item.age_rating" /><DubSubtitleBadge :is-dubbed="item.is_dubbed" :has-subtitle="item.has_subtitle" dark /></div>
        <p class="mt-5 text-xs font-bold tracking-[.16em] text-energy-300" dir="ltr">{{ item.original_title }}</p>
        <h2 class="mt-1 text-3xl font-black sm:text-5xl">{{ item.title }}</h2>
        <p class="mt-4 line-clamp-2 text-sm leading-7 text-slate-300 sm:line-clamp-3 sm:text-base">{{ item.description }}</p>
        <div class="mt-4 flex flex-wrap items-center gap-3 text-xs text-slate-400"><span class="font-black text-white">★ {{ item.rating.toFixed(1) }}</span><span>{{ item.year }}</span><span>{{ item.duration_minutes }} دقیقه</span><span>{{ item.genres.map(genre => genre.title).join('، ') }}</span></div>
        <div class="mt-6 grid grid-cols-[minmax(0,1fr)_auto_auto] gap-2.5 sm:mt-7 sm:flex sm:flex-wrap"><button type="button" class="action-primary" @click="requestPlay('full')"><CinematicIcon name="play" class="size-5" filled />تماشا</button><button type="button" class="inline-flex min-h-12 items-center gap-2 rounded-[.875rem] bg-white/12 px-4 text-sm font-black ring-1 ring-energy-300/15 hover:bg-white/18 sm:px-5" @click="requestPlay('trailer')"><CinematicIcon name="trailer" class="size-5 text-energy-300" />تریلر</button><WatchlistButton :id="item.id" :slug="item.slug" :content-type="item.type" dark compact-on-mobile /></div>
      </div>
    </div>
  </section>
  <ConfirmAdultContentModal :open="modalOpen" :title="item.title" @close="modalOpen = false" @confirm="modalOpen = false; navigateTo(watchPath(true))" />
</template>
