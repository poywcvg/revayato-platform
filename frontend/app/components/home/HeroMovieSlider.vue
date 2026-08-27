<script setup lang="ts">
import type { Movie } from '~/types'
import type { MorphItem } from '~/utils/morphEngine'
import { isMostlyLatin } from '~/utils/displayNames'

const props = withDefaults(defineProps<{
  items: Movie[]
  autoplayInterval?: number
  loading?: boolean
}>(), {
  autoplayInterval: 6000,
  loading: false,
})

const root = useTemplateRef<HTMLElement>('root')
const media = useTemplateRef<HTMLElement>('media')
const morphReady = ref(false)

const morphSlider = useTemplateRef<{
  beginDrag: () => boolean
  drag: (ndx: number) => void
  endDrag: () => void
  setPointer: (x: number, y: number) => void
  pause: () => void
  resume: () => void
  dispose: () => void
}>('morphSlider')
const thumbnailRail = useTemplateRef<HTMLElement>('thumbnailRail')
const manualAnnouncement = ref('')
let visibilityObserver: IntersectionObserver | null = null
let suppressHitClick = false
let suppressHitClickTimer: ReturnType<typeof setTimeout> | null = null
let dragActive = false
let dragStartX = 0
let dragWidth = 1
let dragMoved = false

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

const morphItems = computed<MorphItem[]>(() => props.items.map(item => ({
  image: item.backdrop_url || item.poster_url || '',
  caption: item.title,
})))

const morphDuration = computed(() => reducedMotion.value ? 0.4 : 1.1)

const slideTitle = computed(() => {
  const item = currentItem.value
  if (!item) return ''
  return (item.title || item.secondary_title || item.original_title || '').trim()
})

const slideSubtitle = computed(() => {
  const item = currentItem.value
  if (!item) return ''
  const secondary = (item.secondary_title || item.original_title || '').trim()
  const primary = (item.title || '').trim()
  return secondary && secondary !== primary ? secondary : ''
})

const slideTitleDirection = computed(() => isMostlyLatin(slideTitle.value) ? 'ltr' : 'rtl')

const slideYear = computed(() => {
  const year = Number(currentItem.value?.year)
  if (!Number.isFinite(year) || year < 1888 || year > 2100) return null
  return Math.trunc(year)
})

const imdbRating = computed(() => {
  const item = currentItem.value
  if (!item) return ''
  const ratings = item.ratings || []
  const imdb = ratings.find(entry => entry.source === 'imdb')
  if (imdb?.displayValue) return String(imdb.displayValue)
  const legacy = Number(item.imdb_rating)
  if (Number.isFinite(legacy) && legacy > 0) return legacy.toFixed(1)
  return ''
})

const detailHref = computed(() => {
  const item = currentItem.value
  if (!item) return '/movies'
  return item.type === 'series' ? `/series/${item.slug}` : `/movies/${item.slug}`
})

const router = useRouter()

function announceSelection() {
  const item = currentItem.value
  if (!item) return
  manualAnnouncement.value = `اسلاید ${currentIndex.value + 1} از ${props.items.length}: ${slideTitle.value || item.title}`
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

function onMorphIndex(index: number) {
  if (index === currentIndex.value) return
  goTo(index)
  announceSelection()
}

function handlePointerDown(event: PointerEvent) {
  if (!morphReady.value || props.items.length < 2 || !morphSlider.value) return
  const target = event.target as HTMLElement | null
  if (target?.closest('a, button, [role="tab"], [data-morph-ignore], input, textarea, select')) return

  const el = media.value
  if (!el) return
  const rect = el.getBoundingClientRect()
  dragWidth = rect.width || 1
  dragStartX = event.clientX
  dragMoved = false
  morphSlider.value.setPointer(
    (event.clientX - rect.left) / rect.width,
    1 - (event.clientY - rect.top) / rect.height,
  )
  dragActive = morphSlider.value.beginDrag()
  if (!dragActive) return
  onMorphDragStart()
  try {
    el.setPointerCapture(event.pointerId)
  }
  catch {
    // Pointer capture can fail on some browsers / detached nodes.
  }
}

function handlePointerMove(event: PointerEvent) {
  if (!dragActive || !morphSlider.value) return
  const ndx = (event.clientX - dragStartX) / dragWidth
  if (Math.abs(ndx) > 0.02) dragMoved = true
  // RTL hero: finger moving right advances (same as ArrowLeft → next).
  morphSlider.value.drag(-ndx)
}

function handlePointerUp() {
  if (!dragActive) return
  dragActive = false
  morphSlider.value?.endDrag()
  onMorphDragEnd()
  if (dragMoved) suppressHitClick = true
}

function onMorphDragStart() {
  pause('touch')
}

function onMorphDragEnd() {
  resume('touch')
  if (suppressHitClickTimer) clearTimeout(suppressHitClickTimer)
  suppressHitClickTimer = setTimeout(() => {
    suppressHitClick = false
    suppressHitClickTimer = null
  }, 320)
}

function handleKeydown(event: KeyboardEvent) {
  // RTL carousel: left advances forward, right goes back.
  if (event.key === 'ArrowLeft') {
    event.preventDefault()
    showNext()
  }
  else if (event.key === 'ArrowRight') {
    event.preventDefault()
    showPrevious()
  }
}

function handleHitClick(event: MouseEvent) {
  if (suppressHitClick) {
    event.preventDefault()
    event.stopPropagation()
    return
  }
  void router.push(detailHref.value)
}

function handleFocusOut(event: FocusEvent) {
  if (!root.value?.contains(event.relatedTarget as Node | null)) resume('focus')
}

watch(currentIndex, async (index) => {
  await nextTick()
  const rail = thumbnailRail.value
  const thumb = rail?.querySelector<HTMLElement>(`[data-hero-thumb="${index}"]`)
  if (!rail || !thumb) return
  // Scroll only the thumbnail rail — never the page (scrollIntoView was
  // jumping mid-home on refresh / route enter).
  const railRect = rail.getBoundingClientRect()
  const thumbRect = thumb.getBoundingClientRect()
  const delta = (thumbRect.left + thumbRect.width / 2) - (railRect.left + railRect.width / 2)
  if (Math.abs(delta) < 2) return
  rail.scrollBy({
    left: delta,
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
    if (entry?.isIntersecting) {
      resume('viewport')
      // Resume the WebGL render loop only when the hero is actually visible.
      morphSlider.value?.resume()
    }
    else {
      pause('viewport')
      // Stop the perpetual WebGL repaint once scrolled out of view.
      morphSlider.value?.pause()
    }
  }, { threshold: 0.12 })
  visibilityObserver.observe(root.value)
})

onBeforeUnmount(() => {
  visibilityObserver?.disconnect()
  if (suppressHitClickTimer) clearTimeout(suppressHitClickTimer)
})
</script>

<template>
  <section
    v-if="currentItem"
    ref="root"
    class="hero-movie-slider theme-media-dark"
    :class="isPaused && 'hero-movie-slider--paused'"
    :style="{ '--hero-autoplay-duration': `${Math.max(4000, autoplayInterval)}ms` }"
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

    <div
      ref="media"
      class="hero-movie-slider__media"
      :class="morphReady && 'hero-movie-slider__media--morph'"
      @pointerdown="handlePointerDown"
      @pointermove="handlePointerMove"
      @pointerup="handlePointerUp"
      @pointercancel="handlePointerUp"
    >
      <CinematicImage
        :src="currentItem.backdrop_url"
        :alt="`نمایی از ${currentItem.title}`"
        ratio="backdrop"
        sizes="100vw"
        :priority="currentIndex === 0"
        class="hero-movie-slider__backdrop"
        :class="morphReady && 'hero-movie-slider__backdrop--under-morph'"
        image-class="hero-movie-slider__backdrop-image"
        :fallback-label="`تصویر پس‌زمینه ${currentItem.title} در دسترس نیست`"
      />
      <ClientOnly>
        <!-- Lazy on purpose: this layer is a WebGL enhancement over the backdrop
             image above, and it drags in ogl + gsap. Loading it eagerly put both
             in the shared chunk, so every route paid for the home hero. -->
        <LazyMorphSlider
          ref="morphSlider"
          class="hero-movie-slider__morph"
          :items="morphItems"
          :index="currentIndex"
          transition="melt"
          :intensity="0.55"
          :aberration="0.35"
          :drift="0.4"
          :duration="morphDuration"
          ease="power2.inOut"
          :scale="2.4"
          overlay-color="#05060a"
          :loop="true"
          :radius="0"
          :autoplay="false"
          :show-captions="false"
          :show-controls="false"
          :show-indicators="false"
          @update:index="onMorphIndex"
          @ready="morphReady = true"
          @error="morphReady = false"
        />
      </ClientOnly>
      <button
        v-if="items.length > 1"
        type="button"
        class="hero-movie-slider__nav hero-movie-slider__nav--next"
        aria-label="اسلاید بعدی"
        @click="showNext"
      ><CinematicIcon name="chevron-left" /></button>
      <button
        v-if="items.length > 1"
        type="button"
        class="hero-movie-slider__nav hero-movie-slider__nav--previous"
        aria-label="اسلاید قبلی"
        @click="showPrevious"
      ><CinematicIcon name="chevron-right" /></button>

      <NuxtLink
        :to="detailHref"
        class="hero-movie-slider__play"
        :aria-label="`پخش یا مشاهده ${slideTitle}`"
        @click.stop
      >
        <CinematicIcon name="play" filled />
      </NuxtLink>

      <div class="page-shell hero-movie-slider__stage">
        <Transition name="hero-content" mode="out-in">
          <article
            :key="currentItem.id"
            class="hero-movie-slider__content"
            dir="rtl"
            role="group"
            aria-roledescription="اسلاید"
            :aria-label="`${currentIndex + 1} از ${items.length}: ${slideTitle}${slideYear ? `، ${slideYear}` : ''}`"
          >
            <span
              v-if="slideYear"
              class="hero-movie-slider__year"
            >
              <CinematicIcon name="calendar" class="hero-movie-slider__year-icon" />
              <time :datetime="String(slideYear)" dir="ltr">{{ slideYear }}</time>
            </span>

            <h1
              class="hero-movie-slider__title"
              :class="slideTitleDirection === 'rtl' && 'hero-movie-slider__title--rtl'"
              :dir="slideTitleDirection"
            >
              <NuxtLink
                :to="detailHref"
                class="hero-movie-slider__title-link"
                :aria-label="`رفتن به صفحه ${slideTitle}`"
                @click.stop
              >
                {{ slideTitle }}
              </NuxtLink>
            </h1>
            <p
              v-if="slideSubtitle"
              class="hero-movie-slider__subtitle ltr-value"
              dir="ltr"
            >
              {{ slideSubtitle }}
            </p>

            <div v-if="imdbRating" class="hero-movie-slider__imdb" dir="ltr" aria-label="امتیاز IMDb">
              <span class="hero-movie-slider__imdb-mark" aria-hidden="true">IMDb</span>
              <span class="hero-movie-slider__imdb-score">
                <strong>{{ imdbRating }}</strong><span>/10</span>
              </span>
            </div>
          </article>
        </Transition>

        <div
          class="hero-movie-slider__hit"
          role="link"
          tabindex="-1"
          :aria-label="`رفتن به صفحه ${slideTitle}`"
          @click="handleHitClick"
        />
      </div>

      <div class="hero-movie-slider__dock" data-morph-ignore>
        <div class="page-shell hero-movie-slider__dock-inner">
          <div ref="thumbnailRail" class="hero-movie-slider__thumbnails hide-scrollbar" role="group" aria-label="انتخاب فیلم اسلایدر" dir="rtl">
            <HeroMovieThumb v-for="(item, index) in items" :key="item.id" :item="item" :index="index" :active="index === currentIndex" @select="selectSlide" />
          </div>
        </div>
      </div>
    </div>
  </section>

  <section
    v-else-if="loading"
    class="hero-movie-slider hero-movie-slider--loading theme-media-dark"
    aria-label="در حال آماده‌سازی پیشنهادهای ویژه"
    aria-busy="true"
    role="status"
  >
    <span class="sr-only">در حال بارگذاری پیشنهادهای ویژه</span>
    <div class="hero-movie-slider__media">
      <div class="hero-movie-slider__loading-art" aria-hidden="true" />
      <div class="page-shell hero-movie-slider__stage">
        <div class="hero-movie-slider__loading-content" aria-hidden="true">
          <span class="hero-movie-slider__loading-line hero-movie-slider__loading-meta" />
          <span class="hero-movie-slider__loading-line hero-movie-slider__loading-title" />
          <span class="hero-movie-slider__loading-line hero-movie-slider__loading-meta" />
        </div>
      </div>
      <div class="hero-movie-slider__loading-dock" aria-hidden="true">
        <div class="page-shell hero-movie-slider__loading-posters">
          <span v-for="index in 6" :key="index" class="hero-movie-slider__loading-line" />
        </div>
      </div>
    </div>
  </section>
</template>

<style scoped>
.hero-movie-slider {
  --hero-poster-width: clamp(3.5rem, 18vw, 4.5rem);
  --hero-dock-height: calc(var(--hero-poster-width) * 1.5 + 1.25rem);
  position: relative;
  isolation: isolate;
  display: flex;
  width: 100%;
  flex-direction: column;
  margin-top: calc((var(--header-height) + env(safe-area-inset-top, 0px)) * -1);
  background: #020303;
  color: #fff;
  outline: none;
}

.hero-movie-slider:focus-visible {
  outline: 2px solid rgb(255 255 255 / 70%);
  outline-offset: -2px;
}

.hero-movie-slider__media {
  position: relative;
  isolation: isolate;
  display: flex;
  width: 100%;
  min-height: clamp(24rem, 68svh, 36rem);
  height: clamp(24rem, 68svh, 36rem);
  flex-direction: column;
  overflow: hidden;
  cursor: grab;
  touch-action: pan-y pinch-zoom;
}

.hero-movie-slider__media:active {
  cursor: grabbing;
}

.hero-movie-slider__backdrop {
  position: absolute;
  inset: 0;
  z-index: 0;
  width: 100% !important;
  height: 100% !important;
  max-width: none;
  max-height: none;
  aspect-ratio: unset !important;
}

.hero-movie-slider__morph {
  position: absolute;
  inset: 0;
  z-index: 1;
  width: 100%;
  height: 100%;
  border-radius: inherit;
  background: transparent;
  pointer-events: none;
}

.hero-movie-slider__backdrop--under-morph {
  opacity: 0;
  transition: opacity 280ms ease;
}

.hero-movie-slider__backdrop :deep(.cinematic-image-skeleton),
.hero-movie-slider :deep(.hero-movie-slider__backdrop-image) {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  max-width: none;
  max-height: none;
  object-fit: cover;
  object-position: center center;
  transform: none;
  filter: none;
}

.hero-movie-slider__play {
  position: absolute;
  left: 50%;
  top: 42%;
  z-index: 16;
  display: grid;
  width: clamp(3.25rem, 8vw, 4rem);
  aspect-ratio: 1;
  place-items: center;
  border: 2px solid #fff;
  border-radius: 50%;
  background: rgb(0 0 0 / 28%);
  color: #fff;
  transform: translate(-50%, -50%);
  transition: transform 180ms ease, background-color 180ms ease;
  -webkit-tap-highlight-color: transparent;
}

.hero-movie-slider__play :deep(svg) {
  width: 1.35rem;
  height: 1.35rem;
  margin-inline-start: .12rem;
}

.hero-movie-slider__play:focus-visible {
  outline: 2px solid #fff;
  outline-offset: 3px;
  background: rgb(0 0 0 / 45%);
}

.hero-movie-slider__stage {
  position: relative;
  z-index: 10;
  display: grid;
  min-height: 0;
  flex: 1 1 auto;
  grid-template-columns: minmax(0, 1fr);
  align-items: end;
  padding-top: calc(var(--header-height) + env(safe-area-inset-top, 0px) + clamp(.5rem, 2vw, 1.25rem));
  padding-bottom: calc(var(--hero-dock-height) + clamp(.75rem, 2vw, 1.25rem));
  overflow: hidden;
  pointer-events: none;
}

.hero-movie-slider__dock,
.hero-movie-slider__nav,
.hero-movie-slider__play,
.hero-movie-slider__content,
.hero-movie-slider__content :is(a, button) {
  cursor: auto;
}

.hero-movie-slider__hit {
  position: absolute;
  inset: 0;
  z-index: 1;
  display: block;
  width: 100%;
  height: 100%;
  cursor: inherit;
  text-decoration: none;
  pointer-events: auto;
  -webkit-tap-highlight-color: transparent;
  border: 0;
  background: transparent;
  padding: 0;
}

.hero-movie-slider__content {
  position: relative;
  z-index: 2;
  display: flex;
  width: min(92%, 36rem);
  max-width: 36rem;
  min-width: 0;
  flex-direction: column;
  align-items: flex-start;
  gap: .65rem;
  justify-self: start;
  color: #fff;
  text-align: start;
  pointer-events: none;
}

.hero-movie-slider__content :is(a, button) {
  pointer-events: auto;
}

.hero-movie-slider__year {
  display: inline-flex;
  align-items: center;
  gap: .4rem;
  color: #fff;
  font-family: var(--font-latin-ui);
  font-size: clamp(.85rem, 2.2vw, 1rem);
  font-weight: 600;
  letter-spacing: .02em;
  line-height: 1;
}

.hero-movie-slider__year time {
  color: #fff;
  font-variant-numeric: tabular-nums;
}

.hero-movie-slider__year-icon {
  width: 1.15rem;
  height: 1.15rem;
  color: #fff;
}

.hero-movie-slider__title {
  display: -webkit-box;
  margin: 0;
  min-width: 0;
  overflow: hidden;
  color: #fff;
  font-family: var(--font-latin-ui);
  font-size: clamp(1.85rem, 6.5vw, 2.75rem);
  font-weight: 900;
  line-height: 1.1;
  letter-spacing: -.02em;
  text-wrap: balance;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
}

.hero-movie-slider__title--rtl {
  font-family: var(--font-ui);
  letter-spacing: 0;
}

.hero-movie-slider__title-link {
  color: #fff;
  font: inherit;
  letter-spacing: inherit;
  text-decoration: none;
  cursor: pointer;
}

.hero-movie-slider__title-link:focus-visible {
  outline: 2px solid #fff;
  outline-offset: 4px;
  border-radius: .25rem;
}

.hero-movie-slider__imdb {
  display: inline-flex;
  align-items: center;
  gap: .55rem;
  color: #fff;
  font-family: var(--font-latin-ui);
  font-size: clamp(.9rem, 2.2vw, 1.05rem);
  line-height: 1;
}

.hero-movie-slider__imdb-mark {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 1.35rem;
  border-radius: .2rem;
  padding: .15rem .4rem;
  background: #f5c518;
  color: #000;
  font-size: .72rem;
  font-weight: 900;
  letter-spacing: .04em;
}

.hero-movie-slider__imdb-score {
  color: #fff;
  font-weight: 500;
}

.hero-movie-slider__imdb-score strong {
  color: #fff;
  font-weight: 800;
  font-variant-numeric: tabular-nums;
}

.hero-movie-slider__nav {
  position: absolute;
  top: 42%;
  z-index: 15;
  display: none;
  width: clamp(2.75rem, 3.5vw, 3.5rem);
  aspect-ratio: 1;
  place-items: center;
  border: 1px solid rgb(255 255 255 / 35%);
  border-radius: 50%;
  background: rgb(0 0 0 / 28%);
  color: #fff;
  transform: translateY(-50%);
  transition: transform 180ms ease, background-color 180ms ease, border-color 180ms ease;
}

.hero-movie-slider__nav :deep(svg) {
  width: 1.15rem;
  height: 1.15rem;
}

.hero-movie-slider__nav:focus-visible {
  border-color: #fff;
  background: rgb(0 0 0 / 45%);
  outline: none;
  transform: translateY(-50%) scale(1.06);
}

.hero-movie-slider__nav--next { left: max(1rem, calc((100vw - var(--layout-max)) / 2 + 1rem)); }
.hero-movie-slider__nav--previous { right: max(1rem, calc((100vw - var(--layout-max)) / 2 + 1rem)); }

.hero-movie-slider__dock {
  position: absolute;
  inset-inline: 0;
  bottom: 0;
  z-index: 20;
  width: 100%;
  min-height: var(--hero-dock-height);
  background: transparent;
  pointer-events: auto;
}

.hero-movie-slider__dock-inner {
  display: flex;
  min-width: 0;
  justify-content: flex-end;
  padding-block: .55rem .75rem;
}

.hero-movie-slider__thumbnails {
  display: flex;
  width: 100%;
  min-width: 0;
  align-items: flex-end;
  gap: .75rem;
  overflow-x: auto;
  overflow-y: hidden;
  overscroll-behavior-inline: contain;
  scroll-padding-inline: 50%;
  scroll-snap-type: x proximity;
  padding-block: .25rem .1rem;
  -webkit-overflow-scrolling: touch;
  touch-action: pan-x pinch-zoom;
}

.hero-backdrop-enter-active,
.hero-backdrop-leave-active {
  transition: opacity 600ms ease, transform 900ms cubic-bezier(.2, .75, .2, 1);
  will-change: opacity, transform;
}

.hero-backdrop-leave-active { position: absolute; }
.hero-backdrop-enter-from { opacity: 0; transform: translate3d(1%, 0, 0) scale(1.02); }
.hero-backdrop-leave-to { opacity: 0; transform: translate3d(-1%, 0, 0) scale(1.01); }

.hero-content-enter-active,
.hero-content-leave-active {
  transition: opacity 420ms ease, transform 420ms cubic-bezier(.2, .75, .2, 1);
  will-change: opacity, transform;
}

.hero-content-enter-from { opacity: 0; transform: translate3d(0, .5rem, 0); }
.hero-content-leave-to { opacity: 0; transform: translate3d(0, -.35rem, 0); }

.hero-movie-slider--loading { pointer-events: none; }

.hero-movie-slider__loading-art {
  position: absolute;
  inset: 0;
  background:
    radial-gradient(circle at 72% 34%, rgb(var(--palette-sand-rgb) / 11%), transparent 28rem),
    linear-gradient(135deg, #111715, #030504 68%);
}

.hero-movie-slider__loading-content {
  width: min(90%, 28rem);
  display: flex;
  flex-direction: column;
  gap: .65rem;
  justify-self: start;
}

.hero-movie-slider__loading-line {
  display: block;
  border-radius: .65rem;
  background: rgb(255 255 255 / 14%);
  animation: hero-loading-pulse 1.6s ease-in-out infinite;
}

.hero-movie-slider__loading-title { width: min(90%, 22rem); height: clamp(2rem, 5vw, 2.75rem); }
.hero-movie-slider__loading-meta { width: 7rem; height: 1.15rem; }

.hero-movie-slider__loading-dock {
  position: absolute;
  inset-inline: 0;
  bottom: 0;
  z-index: 20;
  min-height: var(--hero-dock-height);
}

.hero-movie-slider__loading-posters {
  display: flex;
  height: 100%;
  align-items: flex-end;
  justify-content: flex-end;
  gap: .55rem;
  overflow: hidden;
  padding-block: .55rem .75rem;
}

.hero-movie-slider__loading-posters span {
  width: var(--hero-poster-width);
  aspect-ratio: 2 / 3;
  flex: none;
}

@keyframes hero-loading-pulse {
  0%, 100% { opacity: .38; }
  50% { opacity: .82; }
}

@media (hover: hover) and (pointer: fine) {
  .hero-movie-slider__play:hover {
    background: rgb(0 0 0 / 48%);
    transform: translate(-50%, -50%) scale(1.06);
  }

  .hero-movie-slider__nav:hover {
    border-color: #fff;
    background: rgb(0 0 0 / 45%);
    transform: translateY(-50%) scale(1.06);
  }
}

@media (max-width: 767px) {
  .hero-movie-slider {
    --hero-poster-width: clamp(3.65rem, min(18vw, 9.5svh), 4.5rem);
  }

  /* Full first-screen canvas: image paints the entire slider frame. */
  .hero-movie-slider__media {
    width: 100%;
    height: 100svh;
    height: 100dvh;
    min-height: 100svh;
    min-height: 100dvh;
    max-height: none;
  }

  .hero-movie-slider__backdrop {
    inset: 0;
    width: 100% !important;
    height: 100% !important;
    aspect-ratio: unset !important;
  }

  .hero-movie-slider__backdrop :deep(img),
  .hero-movie-slider :deep(.hero-movie-slider__backdrop-image) {
    width: 100%;
    height: 100%;
    object-fit: cover;
    object-position: center 30%;
  }

  .hero-movie-slider__play {
    top: 38%;
  }

  .hero-movie-slider__stage {
    padding-inline: max(5vw, var(--layout-gutter));
  }

  .hero-movie-slider__content {
    width: 100%;
    max-width: min(92vw, 30rem);
  }

  .hero-movie-slider__title {
    font-size: clamp(1.65rem, 7.5vw, 2.35rem);
  }

  .hero-movie-slider__thumbnails {
    gap: .55rem;
    scroll-snap-type: x mandatory;
  }
}

@media (max-width: 767px) and (max-height: 560px) {
  .hero-movie-slider__media {
    height: max(22rem, 100svh);
    min-height: max(22rem, 100svh);
  }
}

@media (min-width: 768px) {
  .hero-movie-slider {
    --hero-poster-width: clamp(5rem, 6.8vw, 6.25rem);
  }

  .hero-movie-slider__media {
    height: clamp(30rem, 62svh, 44rem);
    min-height: clamp(30rem, 62svh, 44rem);
    max-height: min(70svh, 48rem);
  }

  .hero-movie-slider__title {
    font-size: clamp(2.1rem, 4.2vw, 2.85rem);
  }

  .hero-movie-slider__dock-inner {
    justify-content: flex-end;
  }

  .hero-movie-slider__thumbnails {
    width: min(100%, 34rem);
    justify-content: flex-start;
    scroll-padding-inline: 0;
    gap: 1rem;
  }
}

@media (min-width: 1024px) {
  .hero-movie-slider {
    --hero-poster-width: clamp(5.75rem, 6.2vw, 7rem);
  }

  .hero-movie-slider__media {
    border-radius: 0 0 1.25rem 1.25rem;
    height: clamp(32rem, 66svh, 48rem);
    min-height: clamp(32rem, 66svh, 48rem);
  }

  .hero-movie-slider__nav {
    display: grid;
    width: 2.75rem;
  }

  .hero-movie-slider__nav--next {
    left: max(.75rem, env(safe-area-inset-left, 0px));
  }

  .hero-movie-slider__nav--previous {
    right: max(.75rem, env(safe-area-inset-right, 0px));
  }

  .hero-movie-slider__stage,
  .hero-movie-slider__dock-inner {
    padding-inline: max(var(--layout-gutter), 3.25rem);
  }

  .hero-movie-slider__content {
    max-width: 40rem;
  }

  .hero-movie-slider__thumbnails {
    width: min(48%, 38rem);
  }
}

@media (min-width: 1280px) {
  .hero-movie-slider {
    --hero-poster-width: clamp(6.25rem, 5.8vw, 7.5rem);
  }

  .hero-movie-slider__media {
    height: clamp(34rem, 68svh, 52rem);
    min-height: clamp(34rem, 68svh, 52rem);
  }

  .hero-movie-slider__title {
    font-size: clamp(2.35rem, 3.4vw, 3.15rem);
  }
}

@media (prefers-reduced-motion: reduce) {
  .hero-movie-slider__loading-line { animation: none; }
  .hero-backdrop-enter-active,
  .hero-backdrop-leave-active,
  .hero-content-enter-active,
  .hero-content-leave-active,
  .hero-movie-slider__play,
  .hero-movie-slider__nav { transition: none; }
}
</style>
