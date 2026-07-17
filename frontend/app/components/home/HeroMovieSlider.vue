<script setup lang="ts">
import type { Movie } from '~/types'

const props = withDefaults(defineProps<{
  items: Movie[]
  autoplayInterval?: number
}>(), {
  autoplayInterval: 7000,
})

const root = useTemplateRef<HTMLElement>('root')
const thumbnailRail = useTemplateRef<HTMLElement>('thumbnailRail')
const modalOpen = ref(false)
const requestedItem = ref<Movie | null>(null)
const requestedMode = ref<'full' | 'trailer'>('full')
const manualAnnouncement = ref('')
let visibilityObserver: IntersectionObserver | null = null

const {
  currentIndex,
  isPaused,
  reducedMotion,
  goTo,
  next,
  previous,
  pause,
  resume,
} = useHeroSlider(() => props.items.length, props.autoplayInterval)

const currentItem = computed(() => props.items[currentIndex.value] || props.items[0])
const detailPath = computed(() => {
  const item = currentItem.value
  return item ? `/${item.type === 'movie' ? 'movies' : 'series'}/${item.slug}` : '/movies'
})
const badge = computed(() => {
  const item = currentItem.value
  if (!item) return { label: 'ویژه', tone: 'copper' }
  if (item.is_trending) return { label: 'ترند این هفته', tone: 'crimson' }
  if (item.is_new) return { label: 'تازه منتشر شده', tone: 'copper' }
  if (item.is_recommended) return { label: 'پیشنهاد ویژه', tone: 'copper' }
  return { label: item.type === 'series' ? 'سریال منتخب' : 'فیلم منتخب', tone: 'crimson' }
})
const genreLabel = computed(() => currentItem.value?.genres.slice(0, 2).map(genre => genre.title).join(' · ') || '')

function watchPath(item: Movie, mode: 'full' | 'trailer', confirmed = false) {
  return {
    path: `/watch/${item.slug}`,
    query: {
      mode,
      type: item.type,
      ...(confirmed ? { confirmed: '1' } : {}),
    },
  }
}

function requestPlay(mode: 'full' | 'trailer') {
  const item = currentItem.value
  if (!item) return
  requestedItem.value = item
  requestedMode.value = mode
  if (item.age_rating === '18+') {
    pause('adult-modal')
    modalOpen.value = true
    return
  }
  void navigateTo(watchPath(item, mode))
}

function closeAdultModal() {
  modalOpen.value = false
  requestedItem.value = null
  resume('adult-modal')
}

function confirmPlay() {
  const item = requestedItem.value
  if (!item) return closeAdultModal()
  modalOpen.value = false
  resume('adult-modal')
  void navigateTo(watchPath(item, requestedMode.value, true))
}

function announceSelection() {
  const item = currentItem.value
  if (item) manualAnnouncement.value = `اسلاید ${currentIndex.value + 1} از ${props.items.length}: ${item.title}`
}

function selectSlide(index: number) {
  goTo(index)
  announceSelection()
}

function showNext() {
  next()
  announceSelection()
}

function showPrevious() {
  previous()
  announceSelection()
}

function handleKeydown(event: KeyboardEvent) {
  if (event.key === 'ArrowLeft') {
    event.preventDefault()
    showPrevious()
  } else if (event.key === 'ArrowRight') {
    event.preventDefault()
    showNext()
  }
}

function handleFocusOut(event: FocusEvent) {
  if (!root.value?.contains(event.relatedTarget as Node | null)) resume('focus')
}

watch(currentIndex, async (index) => {
  await nextTick()
  const rail = thumbnailRail.value
  const thumb = rail?.querySelector<HTMLElement>(`[data-hero-thumb="${index}"]`)
  if (!rail || !thumb) return
  const railRect = rail.getBoundingClientRect()
  const thumbRect = thumb.getBoundingClientRect()
  rail.scrollTo({
    left: Math.max(0, rail.scrollLeft + thumbRect.left - railRect.left - (railRect.width - thumbRect.width) / 2),
    behavior: reducedMotion.value ? 'auto' : 'smooth',
  })
})

onMounted(() => {
  pause('viewport')
  if (!root.value || !('IntersectionObserver' in window)) {
    resume('viewport')
    return
  }
  visibilityObserver = new IntersectionObserver(([entry]) => {
    if (entry?.isIntersecting) resume('viewport')
    else pause('viewport')
  }, { threshold: 0.12 })
  visibilityObserver.observe(root.value)
})

onBeforeUnmount(() => visibilityObserver?.disconnect())
</script>

<template>
  <section
    v-if="currentItem"
    ref="root"
    class="hero-movie-slider"
    :class="isPaused && 'hero-movie-slider--paused'"
    tabindex="0"
    role="region"
    aria-roledescription="carousel"
    aria-label="اسلایدر فیلم‌های منتخب"
    @keydown="handleKeydown"
    @mouseenter="pause('hover')"
    @mouseleave="resume('hover')"
    @focusin="pause('focus')"
    @focusout="handleFocusOut"
  >
    <p class="sr-only" aria-live="polite">{{ manualAnnouncement }}</p>

    <Transition name="hero-backdrop">
      <CinematicImage
        :key="currentItem.id"
        :src="currentItem.backdrop_url"
        :alt="`نمایی از ${currentItem.title}`"
        ratio="backdrop"
        :priority="currentIndex === 0"
        class="hero-movie-slider__backdrop"
        image-class="hero-movie-slider__backdrop-image"
        :fallback-label="`تصویر پس‌زمینه ${currentItem.title} در دسترس نیست`"
      />
    </Transition>
    <div class="hero-movie-slider__overlay" aria-hidden="true" />

    <button
      v-if="items.length > 1"
      type="button"
      class="hero-movie-slider__nav hero-movie-slider__nav--previous"
      aria-label="اسلاید قبلی"
      @click="showPrevious"
    ><CinematicIcon name="chevron-left" class="size-5" /></button>
    <button
      v-if="items.length > 1"
      type="button"
      class="hero-movie-slider__nav hero-movie-slider__nav--next"
      aria-label="اسلاید بعدی"
      @click="showNext"
    ><CinematicIcon name="chevron-right" class="size-5" /></button>

    <div class="page-shell hero-movie-slider__inner">
      <Transition name="hero-content" mode="out-in">
        <div :key="currentItem.id" class="hero-movie-slider__content" dir="rtl">
          <div class="flex flex-wrap items-center gap-2">
            <span class="hero-movie-slider__badge" :class="badge.tone === 'crimson' ? 'hero-movie-slider__badge--crimson' : 'hero-movie-slider__badge--copper'">
              <span class="size-1.5 rounded-full bg-current" />{{ badge.label }}
            </span>
            <span class="rounded-full border border-white/10 bg-canvas-soft/78 px-2.5 py-1 text-[10px] font-black text-secondary">{{ currentItem.type === 'movie' ? 'فیلم سینمایی' : 'سریال' }}</span>
            <AgeRatingBadge :rating="currentItem.age_rating" />
          </div>

          <p v-if="currentItem.original_title" class="mt-4 truncate text-[10px] font-bold tracking-[.18em] text-primary-300 sm:mt-5 sm:text-xs" dir="ltr">{{ currentItem.original_title }}</p>
          <h1 class="mt-1 line-clamp-2 text-4xl font-black leading-[1.15] tracking-tight text-ink sm:text-5xl lg:text-6xl xl:text-7xl">{{ currentItem.title }}</h1>

          <div class="mt-3 flex flex-wrap items-center gap-x-3 gap-y-1.5 text-[11px] font-bold text-secondary sm:mt-4 sm:text-sm">
            <span class="inline-flex items-center gap-1.5 text-ink" dir="ltr"><CinematicIcon name="star" class="size-4 text-primary-400 sm:size-4.5" filled />IMDb {{ currentItem.rating.toFixed(1) }}</span>
            <span class="hero-movie-slider__meta-dot" />
            <span class="tabular-nums">{{ currentItem.year }}</span>
            <span class="hero-movie-slider__meta-dot" />
            <span>{{ currentItem.type === 'series' ? `${currentItem.seasons_count || 1} فصل` : `${currentItem.duration_minutes} دقیقه` }}</span>
            <span v-if="genreLabel" class="hero-movie-slider__meta-dot hidden sm:block" />
            <span v-if="genreLabel" class="hidden sm:inline">{{ genreLabel }}</span>
          </div>

          <p class="mt-3 line-clamp-2 max-w-2xl text-xs leading-6 text-secondary sm:mt-4 sm:line-clamp-3 sm:text-sm sm:leading-7 lg:text-base lg:leading-8">{{ currentItem.description }}</p>

          <div class="hero-movie-slider__actions mt-5 gap-2.5 sm:mt-6">
            <button type="button" class="hero-movie-slider__primary" :aria-label="`تماشای ${currentItem.title}`" @click="requestPlay('full')">
              <CinematicIcon name="play" class="size-5" filled />تماشا کن
            </button>
            <button type="button" class="hero-movie-slider__secondary" :aria-label="`تماشای تریلر ${currentItem.title}`" @click="requestPlay('trailer')">
              <CinematicIcon name="trailer" class="size-5 text-primary-300" />تریلر
            </button>
            <NuxtLink :to="detailPath" class="hero-movie-slider__detail" :aria-label="`جزئیات ${currentItem.title}`">
              <CinematicIcon name="info" class="size-4.5" />جزئیات
            </NuxtLink>
            <WatchlistButton :id="currentItem.id" :slug="currentItem.slug" :content-type="currentItem.type" dark compact-on-mobile />
          </div>
        </div>
      </Transition>
    </div>

    <div class="hero-movie-slider__dock">
      <div class="page-shell">
        <div class="mb-2.5 flex items-center justify-between gap-3">
          <div class="flex items-center gap-2">
            <span class="text-[10px] font-black text-primary-300">انتخاب‌های ویژه</span>
            <span class="font-latin text-[9px] font-bold tabular-nums text-muted" dir="ltr">{{ String(currentIndex + 1).padStart(2, '0') }} / {{ String(items.length).padStart(2, '0') }}</span>
          </div>
          <div v-if="items.length > 1" class="flex items-center gap-1 lg:hidden" dir="ltr">
            <button type="button" class="hero-movie-slider__dock-nav" aria-label="اسلاید قبلی" @click="showPrevious"><CinematicIcon name="chevron-left" class="size-4" /></button>
            <button type="button" class="hero-movie-slider__dock-nav" aria-label="اسلاید بعدی" @click="showNext"><CinematicIcon name="chevron-right" class="size-4" /></button>
          </div>
        </div>

        <div class="mb-2 flex gap-1" aria-hidden="true">
          <span v-for="(_, index) in items" :key="index" class="h-0.5 flex-1 rounded-full transition-colors" :class="index === currentIndex ? 'bg-primary-500' : 'bg-line/80'" />
        </div>

        <div ref="thumbnailRail" class="hero-movie-slider__thumbnails hide-scrollbar" role="group" aria-label="انتخاب فیلم اسلایدر" dir="ltr">
          <HeroMovieThumb v-for="(item, index) in items" :key="item.id" :item="item" :index="index" :active="index === currentIndex" @select="selectSlide" />
        </div>
      </div>
    </div>

    <ConfirmAdultContentModal :open="modalOpen" :title="requestedItem?.title" @close="closeAdultModal" @confirm="confirmPlay" />
  </section>
</template>

<style scoped>
.hero-movie-slider {
  position: relative;
  isolation: isolate;
  height: clamp(620px, 92svh, 680px);
  max-width: 100%;
  margin-top: -132px;
  overflow: hidden;
  background: var(--theme-bg-main);
  color: var(--theme-text-primary);
  outline: none;
}

.hero-movie-slider:focus-visible {
  box-shadow: inset 0 0 0 2px rgb(196 106 45 / 62%);
}

.hero-movie-slider__backdrop {
  position: absolute;
  inset: 0;
  z-index: -30;
  width: 100%;
  height: 100%;
}

.hero-movie-slider :deep(.hero-movie-slider__backdrop-image) {
  object-position: center;
}

.hero-movie-slider__overlay {
  position: absolute;
  inset: 0;
  z-index: -20;
  background:
    linear-gradient(90deg, rgb(6 6 7 / 97%) 0%, rgb(6 6 7 / 82%) 34%, rgb(6 6 7 / 30%) 68%, rgb(6 6 7 / 14%) 100%),
    linear-gradient(180deg, rgb(6 6 7 / 46%) 0%, rgb(6 6 7 / 16%) 42%, var(--theme-bg-main) 100%),
    radial-gradient(circle at 22% 32%, rgb(196 106 45 / 14%), transparent 32%),
    radial-gradient(circle at 80% 20%, rgb(143 29 44 / 12%), transparent 35%);
}

.hero-movie-slider__inner {
  display: flex;
  min-width: 0;
  max-width: 100%;
  height: 100%;
  align-items: center;
  padding-top: calc(132px + 1rem);
  padding-bottom: 10.5rem;
  overflow: hidden;
}

.hero-movie-slider__content {
  flex: 0 1 43rem;
  min-width: 0;
  width: 100%;
  max-width: min(43rem, 100%);
  margin-inline: 0;
  overflow-wrap: anywhere;
  text-align: right;
}

.hero-movie-slider__actions {
  display: grid;
  min-width: 0;
  width: 100%;
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.hero-movie-slider__actions > * {
  min-width: 0;
  max-width: 100%;
}

.hero-movie-slider__badge {
  display: inline-flex;
  min-height: 1.75rem;
  align-items: center;
  gap: .45rem;
  border-radius: 999px;
  padding: .3rem .65rem;
  font-size: .625rem;
  font-weight: 900;
  box-shadow: inset 0 1px 0 rgb(244 241 236 / 4%);
}

.hero-movie-slider__badge--copper {
  border: 1px solid rgb(196 106 45 / 34%);
  background: rgb(196 106 45 / 14%);
  color: var(--theme-accent-primary-hover);
}

.hero-movie-slider__badge--crimson {
  border: 1px solid rgb(143 29 44 / 42%);
  background: rgb(42 11 18 / 82%);
  color: var(--theme-accent-crimson-hover);
}

.hero-movie-slider__meta-dot {
  width: .25rem;
  height: .25rem;
  flex: none;
  border-radius: 999px;
  background: var(--theme-text-disabled);
}

.hero-movie-slider__primary,
.hero-movie-slider__secondary,
.hero-movie-slider__detail {
  display: inline-flex;
  min-height: 3rem;
  align-items: center;
  justify-content: center;
  gap: .5rem;
  border-radius: .875rem;
  padding: .7rem 1rem;
  font-size: .8125rem;
  font-weight: 900;
  transition: background-color 160ms ease, border-color 160ms ease, color 160ms ease, transform 160ms ease, box-shadow 160ms ease;
}

.hero-movie-slider__primary {
  background: var(--theme-accent-primary);
  color: var(--theme-bg-main);
  box-shadow: 0 12px 30px rgb(196 106 45 / 24%);
}

.hero-movie-slider__primary:hover {
  background: var(--theme-accent-primary-hover);
  box-shadow: 0 14px 34px rgb(196 106 45 / 30%);
}

.hero-movie-slider__primary:active { background: var(--theme-accent-primary-active); transform: scale(.98); }

.hero-movie-slider__secondary {
  border: 1px solid rgb(244 241 236 / 16%);
  background: rgb(20 20 23 / 72%);
  color: var(--theme-text-primary);
}

.hero-movie-slider__secondary:hover {
  border-color: var(--theme-accent-primary);
  background: var(--theme-accent-primary-soft);
}

.hero-movie-slider__detail {
  padding-inline: .75rem;
  color: var(--theme-text-secondary);
}

.hero-movie-slider__detail:hover { background: rgb(244 241 236 / 6%); color: var(--theme-text-primary); }

.hero-movie-slider__nav {
  position: absolute;
  top: 47%;
  z-index: 30;
  display: none;
  width: 3rem;
  height: 3rem;
  place-items: center;
  border: 1px solid rgb(244 241 236 / 13%);
  border-radius: 1rem;
  background: rgb(11 11 13 / 84%);
  color: var(--theme-text-secondary);
  box-shadow: 0 12px 28px rgb(0 0 0 / 30%);
  transition: color 160ms ease, border-color 160ms ease, background-color 160ms ease, transform 160ms ease;
}

.hero-movie-slider__nav:hover,
.hero-movie-slider__nav:focus-visible {
  border-color: rgb(196 106 45 / 60%);
  background: rgb(196 106 45 / 16%);
  color: var(--theme-accent-primary-hover);
}

.hero-movie-slider__nav:active { transform: scale(.94); }
.hero-movie-slider__nav--previous { left: 1.25rem; }
.hero-movie-slider__nav--next { right: 1.25rem; }

.hero-movie-slider__dock {
  position: absolute;
  inset: auto 0 0;
  z-index: 20;
  padding: 2.5rem 0 .7rem;
  background: linear-gradient(to top, var(--theme-bg-main) 0%, rgb(6 6 7 / 94%) 58%, transparent 100%);
}

.hero-movie-slider__thumbnails {
  display: flex;
  gap: .7rem;
  overflow-x: auto;
  overscroll-behavior-inline: contain;
  scroll-snap-type: x proximity;
  scroll-padding-inline: 1rem;
  padding: .35rem .25rem .1rem;
  -webkit-overflow-scrolling: touch;
}

.hero-movie-slider__dock-nav {
  display: grid;
  width: 2.75rem;
  height: 2.75rem;
  place-items: center;
  border: 1px solid var(--theme-border);
  border-radius: .7rem;
  background: var(--theme-bg-elevated);
  color: var(--theme-text-secondary);
}

.hero-movie-slider__dock-nav:hover { border-color: rgb(196 106 45 / 48%); color: var(--theme-accent-primary-hover); }

.hero-backdrop-enter-active,
.hero-backdrop-leave-active {
  transition: opacity 650ms ease, transform 1.1s ease;
}

.hero-backdrop-leave-active { position: absolute; }
.hero-backdrop-enter-from { opacity: 0; transform: scale(1.025); }
.hero-backdrop-leave-to { opacity: 0; transform: scale(1.012); }

.hero-content-enter-active,
.hero-content-leave-active { transition: opacity 260ms ease, transform 320ms ease; }
.hero-content-enter-from { opacity: 0; transform: translateY(.75rem); }
.hero-content-leave-to { opacity: 0; transform: translateY(-.35rem); }

@media (max-width: 639px) {
  .hero-movie-slider__content {
    flex-basis: 100%;
  }

  .hero-movie-slider__primary,
  .hero-movie-slider__secondary {
    min-width: 0;
    width: 100%;
    padding-inline: .65rem;
  }

  .hero-movie-slider__detail {
    border: 1px solid rgb(244 241 236 / 10%);
    background: rgb(20 20 23 / 52%);
  }
}

@media (min-width: 640px) {
  .hero-movie-slider__inner { padding-top: calc(132px + 1.5rem); padding-bottom: 11.5rem; }
  .hero-movie-slider__actions { display: flex; width: auto; flex-wrap: wrap; align-items: center; }
  .hero-movie-slider__primary,
  .hero-movie-slider__secondary,
  .hero-movie-slider__detail { padding-inline: 1.2rem; font-size: .875rem; }
  .hero-movie-slider__thumbnails { gap: .9rem; }
}

@media (min-width: 768px) {
  .hero-movie-slider { margin-top: -68px; }
  .hero-movie-slider__inner { padding-top: calc(68px + 1.5rem); }
  .hero-movie-slider__content { margin-right: auto; margin-left: 0; }
}

@media (min-width: 768px) and (max-width: 1023px) {
  .hero-movie-slider { height: clamp(680px, 86svh, 740px); }
}

@media (min-width: 1024px) {
  .hero-movie-slider { height: clamp(720px, 88svh, 820px); border-radius: 0 0 2.5rem 2.5rem; }
  .hero-movie-slider__inner { padding-bottom: 12.5rem; }
  .hero-movie-slider__nav { display: grid; }
  .hero-movie-slider__dock { padding-bottom: 1rem; }
  .hero-movie-slider__thumbnails { justify-content: center; }
}

@media (prefers-reduced-motion: reduce) {
  .hero-backdrop-enter-active,
  .hero-backdrop-leave-active,
  .hero-content-enter-active,
  .hero-content-leave-active,
  .hero-movie-slider__primary,
  .hero-movie-slider__secondary,
  .hero-movie-slider__detail,
  .hero-movie-slider__nav { transition: none; }
}
</style>
