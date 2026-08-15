<script setup lang="ts">
import type { Movie } from '~/types'
import { primaryCardRating } from '~/utils/mediaRatings'

const props = defineProps<{ item: Movie }>()
const modalOpen = ref(false)
const requestedMode = ref<'full' | 'trailer'>('full')
const restricted = computed(() => props.item.age_rating === '18+')
const detailPath = computed(() => `/${props.item.type === 'movie' ? 'movies' : 'series'}/${props.item.slug}`)
const cardRating = computed(() => primaryCardRating(props.item.ratings || []))

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
    <div class="theme-media-dark relative isolate min-h-[clamp(23.75rem,58svh,30rem)] overflow-hidden rounded-3xl border border-white/10 bg-night-950 text-white sm:rounded-[2rem]">
      <CinematicImage
        :src="item.backdrop_url || item.poster_url"
        alt=""
        ratio="backdrop"
        class="absolute inset-0 -z-30 h-full w-full"
        image-class="object-cover"
        fallback-label="تصویر پس‌زمینه در دسترس نیست"
      />
      <div class="absolute inset-0 -z-20 bg-gradient-to-l from-night-950 via-night-950/85 to-night-900/18" />
      <div class="absolute inset-0 -z-10 bg-gradient-to-t from-night-950 via-transparent to-black/20" />
      <div class="flex min-h-[clamp(23.75rem,58svh,30rem)] max-w-2xl flex-col justify-end p-[clamp(1.25rem,4vw,2.5rem)]">
        <div class="flex flex-wrap items-center gap-2"><span class="rounded-full bg-primary-500 px-3 py-1.5 text-xs font-black text-night-950">ویژه این هفته</span><AgeRatingBadge :rating="item.age_rating" /><DubSubtitleBadge :is-dubbed="item.is_dubbed" :has-subtitle="item.has_subtitle" dark /></div>
        <h2 class="mt-2 text-[clamp(1.75rem,5vw,3rem)] font-black" dir="auto"><NuxtLink :to="detailPath" class="transition hover:text-primary-300">{{ item.title }}</NuxtLink></h2>
        <p v-if="item.secondary_title" class="mt-2 text-sm font-bold text-primary-300/90" dir="rtl">{{ item.secondary_title }}</p>
        <p class="mt-4 line-clamp-2 text-sm leading-7 text-slate-300 sm:line-clamp-3 sm:text-base">{{ item.description }}</p>
        <div class="mt-4 flex flex-wrap items-center gap-3 text-xs text-slate-400">
          <RatingBadge v-if="cardRating" :rating="cardRating" compact />
          <span v-if="item.year">{{ item.year }}</span>
          <span v-if="item.duration_minutes">{{ item.duration_minutes }} دقیقه</span>
          <span>{{ item.genres.map(genre => genre.title).join('، ') }}</span>
        </div>
        <div class="mt-6 grid grid-cols-[minmax(0,1fr)_auto_auto] gap-2.5 sm:mt-7 sm:flex sm:flex-wrap"><button type="button" class="action-primary" @click="requestPlay('full')"><CinematicIcon name="play" class="size-5" filled />تماشا</button><button type="button" class="inline-flex min-h-12 items-center gap-2 rounded-[.875rem] bg-white/10 px-4 text-sm font-black ring-1 ring-white/15 hover:bg-white/15 sm:px-5" @click="requestPlay('trailer')"><CinematicIcon name="trailer" class="size-5 text-primary-300" />تریلر</button><WatchlistButton :id="item.id" :slug="item.slug" :content-type="item.type" dark compact-on-mobile /></div>
      </div>
    </div>
  </section>
  <ConfirmAdultContentModal :open="modalOpen" :title="item.title" @close="modalOpen = false" @confirm="modalOpen = false; navigateTo(watchPath(true))" />
</template>
