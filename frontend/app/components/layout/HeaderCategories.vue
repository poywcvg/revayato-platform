<script setup lang="ts">
import type { CinematicIconName } from '~/types'
import { getCatalogGenre } from '~/data/genres'

const route = useRoute()
const { genres } = useCatalog()
const { trackGenreClick } = useAnalyticsEvent()
const isDesktop = useMediaQuery('(min-width: 1024px)')
const isTablet = useMediaQuery('(min-width: 640px) and (max-width: 1023px)')

const menuRoot = ref<HTMLElement | null>(null)
const trigger = ref<HTMLButtonElement | null>(null)
const isOpen = ref(false)
const panelStyle = ref<Record<string, string>>({})
const genreQuery = ref('')

interface QuickCategory {
  label: string
  to: string
  icon: CinematicIconName
}

/** Shortcuts not already covered by primary header nav */
const quickCategories: QuickCategory[] = [
  { label: 'انیمیشن', to: '/movies?format=animation', icon: 'animation' },
  { label: 'ترندها', to: '/movies?sort=trending', icon: 'trend' },
  { label: 'منتخب‌ها', to: '/movies?sort=featured', icon: 'sparkles' },
  { label: 'دوبله', to: '/movies?availability=dubbed', icon: 'audio' },
  { label: 'پیشنهاد تو', to: '/?section=recommended', icon: 'ai' },
]

const browseLinks = [
  { label: 'فیلم‌ها', href: '/movies', icon: 'movie' as const },
  { label: 'سریال‌ها', href: '/series', icon: 'series' as const },
  { label: 'تازه‌ها', href: '/new', icon: 'sparkles' as const },
  { label: 'کشورها', href: '/countries', icon: 'globe' as const },
]

const sortedGenres = computed(() => {
  const rows = [...genres.value]
  rows.sort((a, b) => {
    const af = Number(Boolean(a.is_featured))
    const bf = Number(Boolean(b.is_featured))
    if (af !== bf) return bf - af
    const countDelta = Number(b.title_count || 0) - Number(a.title_count || 0)
    if (countDelta) return countDelta
    return a.title.localeCompare(b.title, 'fa')
  })
  return rows
})

function genreTitleCount(genre: { title_count?: number; movie_count?: number; series_count?: number }) {
  if (genre.title_count != null) return Math.max(0, Number(genre.title_count) || 0)
  return Math.max(0, Number(genre.movie_count || 0) + Number(genre.series_count || 0))
}

function formatGenreCount(count: number) {
  return count.toLocaleString('fa-IR')
}

const filteredGenres = computed(() => {
  const q = genreQuery.value.trim()
  if (!q) return sortedGenres.value
  return sortedGenres.value.filter(genre => genre.title.includes(q) || genre.slug.includes(q))
})

const hasActiveCategory = computed(() => Boolean(
  route.query.genre
  || route.query.format
  || route.query.sort
  || route.query.availability
  || route.query.section === 'recommended',
))

function genreIcon(slug: string): CinematicIconName {
  return getCatalogGenre(slug)?.icon || 'film'
}

function positionDesktopPanel() {
  if (!import.meta.client || !isDesktop.value || !trigger.value) {
    panelStyle.value = {}
    return
  }

  const rect = trigger.value.getBoundingClientRect()
  const gutter = 16
  const maxW = window.innerWidth < 1280 ? 560 : window.innerWidth < 1536 ? 680 : 760
  const width = Math.min(maxW, window.innerWidth - gutter * 2)
  const isRtl = getComputedStyle(document.documentElement).direction === 'rtl'
  let left = isRtl ? rect.right - width : rect.left

  if (left < gutter) left = gutter
  if (left + width > window.innerWidth - gutter) left = window.innerWidth - gutter - width

  const top = Math.round(rect.bottom + 10)
  const maxHeight = Math.max(280, Math.min(window.innerHeight - top - gutter, window.innerHeight * 0.78))

  panelStyle.value = {
    top: `${top}px`,
    left: `${Math.round(left)}px`,
    width: `${Math.round(width)}px`,
    maxHeight: `${Math.round(maxHeight)}px`,
  }
}

function closeMenu() {
  isOpen.value = false
  panelStyle.value = {}
  genreQuery.value = ''
}

function closeFromKeyboard() {
  if (!isOpen.value) return
  closeMenu()
  trigger.value?.focus()
}

function onNavigate(href?: string) {
  if (href) {
    const genreMatch = href.match(/[?&]genre=([^&]+)/)
    if (genreMatch?.[1]) trackGenreClick(decodeURIComponent(genreMatch[1]))
  }
  closeMenu()
}

onClickOutside(menuRoot, (event) => {
  if (!isOpen.value) return
  const target = event.target as Node | null
  const panel = document.getElementById('header-categories-menu')
  if (panel && target && panel.contains(target)) return
  closeMenu()
})
onKeyStroke('Escape', closeFromKeyboard)
watch(() => route.fullPath, closeMenu)
watch(isDesktop, () => closeMenu())

watch(isOpen, async (open) => {
  if (!import.meta.client) return
  if (!isDesktop.value) {
    document.documentElement.style.overflow = open ? 'hidden' : ''
    panelStyle.value = {}
    return
  }
  document.documentElement.style.overflow = ''
  if (open) {
    await nextTick()
    positionDesktopPanel()
  }
  else {
    panelStyle.value = {}
  }
})

useEventListener(window, 'resize', () => {
  if (isOpen.value && isDesktop.value) positionDesktopPanel()
})
useEventListener(window, 'scroll', () => {
  if (isOpen.value && isDesktop.value) positionDesktopPanel()
}, { capture: true, passive: true })

onBeforeUnmount(() => {
  if (import.meta.client) document.documentElement.style.overflow = ''
})
</script>

<template>
  <div ref="menuRoot" class="header-categories relative shrink-0">
    <button
      id="header-categories-trigger"
      ref="trigger"
      type="button"
      class="header-categories__trigger relative inline-flex size-[var(--touch-target)] items-center justify-center gap-1.5 rounded-xl px-0 text-sm font-medium ring-1 ring-transparent transition-colors lg:h-11 lg:w-auto lg:px-2.5 xl:px-3"
      :class="isOpen || hasActiveCategory ? 'bg-elevated text-ink ring-white/10' : 'text-secondary hover:bg-elevated/70 hover:text-ink'"
      aria-label="دسته‌بندی‌های محتوا"
      :aria-expanded="isOpen"
      aria-controls="header-categories-menu"
      @click="isOpen = !isOpen"
    >
      <CinematicIcon name="grid" class="size-4.5" />
      <span class="hidden xl:inline">دسته‌بندی‌ها</span>
      <CinematicIcon name="chevron-down" class="hidden size-3.5 transition-transform xl:block" :class="isOpen && 'rotate-180'" />
      <span v-if="hasActiveCategory" class="absolute inset-x-3 bottom-1 h-0.5 rounded-full bg-white/55" aria-hidden="true" />
    </button>

    <Teleport to="body">
      <Transition name="cat-backdrop">
        <button
          v-if="isOpen && !isDesktop"
          type="button"
          class="header-categories__backdrop"
          aria-label="بستن منوی دسته‌بندی"
          @click="closeMenu"
        />
      </Transition>

      <Transition :name="isDesktop ? 'cat-panel-desktop' : 'cat-panel-mobile'">
        <div
          v-if="isOpen"
          id="header-categories-menu"
          class="header-categories__panel"
          :class="isDesktop ? 'header-categories__panel--desktop' : isTablet ? 'header-categories__panel--tablet' : 'header-categories__panel--mobile'"
          :style="isDesktop ? panelStyle : undefined"
          aria-labelledby="header-categories-trigger"
          role="dialog"
          :aria-modal="!isDesktop"
        >
          <div class="header-categories__sheet-head">
            <span v-if="!isDesktop && !isTablet" class="header-categories__handle" aria-hidden="true" />
            <div class="header-categories__sheet-row">
              <div class="header-categories__sheet-title">
                <span class="text-sm font-bold text-ink">دسته‌بندی‌ها</span>
                <span class="text-[11px] text-muted">همه ژانرها، میانبر و مرور</span>
              </div>
              <button
                type="button"
                class="header-categories__close"
                aria-label="بستن"
                @click="closeMenu"
              >
                <CinematicIcon name="x" class="size-4.5" />
              </button>
            </div>
          </div>

          <div class="header-categories__body soft-scrollbar">
            <section class="header-categories__section" aria-label="میانبرها">
              <h3 class="header-categories__label">میانبرها</h3>
              <div class="header-categories__chips">
                <NuxtLink
                  v-for="item in quickCategories"
                  :key="item.to"
                  :to="item.to"
                  class="header-categories__chip"
                  @click="onNavigate(item.to)"
                >
                  <CinematicIcon :name="item.icon" class="size-3.5 shrink-0 opacity-80" />
                  <span>{{ item.label }}</span>
                </NuxtLink>
              </div>
            </section>

            <section class="header-categories__section" aria-label="مرور">
              <h3 class="header-categories__label">مرور</h3>
              <div class="header-categories__browse">
                <NuxtLink
                  v-for="item in browseLinks"
                  :key="item.href"
                  :to="item.href"
                  class="header-categories__browse-link"
                  @click="onNavigate(item.href)"
                >
                  <CinematicIcon :name="item.icon" class="size-4 shrink-0 opacity-75" />
                  <span>{{ item.label }}</span>
                </NuxtLink>
              </div>
            </section>

            <section class="header-categories__section header-categories__section--genres" aria-label="ژانرها">
              <div class="header-categories__genres-head">
                <h3 class="header-categories__label">
                  ژانرها
                  <span class="header-categories__count">{{ filteredGenres.length.toLocaleString('fa-IR') }}</span>
                </h3>
                <label class="header-categories__search">
                  <span class="sr-only">جستجوی ژانر</span>
                  <CinematicIcon name="search" class="size-3.5 opacity-60" />
                  <input
                    v-model="genreQuery"
                    type="search"
                    inputmode="search"
                    autocomplete="off"
                    placeholder="جستجوی ژانر…"
                    class="header-categories__search-input"
                  >
                </label>
              </div>

              <div v-if="filteredGenres.length" class="header-categories__genre-grid">
                <NuxtLink
                  v-for="genre in filteredGenres"
                  :key="genre.slug"
                  :to="`/movies?genre=${encodeURIComponent(genre.slug)}`"
                  class="header-categories__genre"
                  :class="{ 'header-categories__genre--featured': genre.is_featured }"
                  :aria-label="`${genre.title}، ${formatGenreCount(genreTitleCount(genre))} عنوان`"
                  @click="onNavigate(`/movies?genre=${encodeURIComponent(genre.slug)}`)"
                >
                  <CinematicIcon :name="genreIcon(genre.slug)" class="size-4 shrink-0 opacity-75" />
                  <span class="header-categories__genre-title truncate">{{ genre.title }}</span>
                  <span class="header-categories__genre-count font-latin tabular-nums">
                    {{ formatGenreCount(genreTitleCount(genre)) }}
                  </span>
                </NuxtLink>
              </div>
              <p v-else class="header-categories__empty">ژانری با این عبارت پیدا نشد.</p>
            </section>
          </div>
        </div>
      </Transition>
    </Teleport>
  </div>
</template>

<style scoped>
.header-categories__backdrop {
  position: fixed;
  inset: 0;
  z-index: 55;
  cursor: default;
  border: 0;
  background: rgb(0 0 0 / 48%);
  -webkit-backdrop-filter: blur(2px);
  backdrop-filter: blur(2px);
}

.header-categories__panel {
  z-index: 60;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  text-align: right;
  border: 1px solid color-mix(in srgb, var(--theme-border) 70%, transparent);
  background: color-mix(in srgb, var(--theme-bg-elevated) 94%, #0a0a0b);
  box-shadow: 0 18px 48px rgb(0 0 0 / 38%);
  -webkit-backdrop-filter: blur(18px) saturate(130%);
  backdrop-filter: blur(18px) saturate(130%);
}

.header-categories__panel--mobile {
  position: fixed;
  inset-inline: 0;
  bottom: 0;
  top: auto;
  max-height: min(90dvh, calc(100dvh - env(safe-area-inset-top, 0px) - 2.5rem));
  border-radius: 1.25rem 1.25rem 0 0;
  border-bottom: 0;
  padding-bottom: env(safe-area-inset-bottom, 0px);
}

.header-categories__panel--tablet {
  position: fixed;
  left: 50%;
  right: auto;
  top: calc(var(--sticky-offset, 3.5rem) + 0.45rem);
  bottom: auto;
  width: min(36rem, calc(100dvw - 1.5rem));
  max-height: min(82dvh, calc(100dvh - var(--sticky-offset, 3.5rem) - 1rem));
  transform: translateX(-50%);
  border-radius: 1.1rem;
}

.header-categories__panel--desktop {
  position: fixed;
  overflow: hidden;
  border-radius: 1.1rem;
}

.header-categories__sheet-head {
  display: flex;
  flex-shrink: 0;
  flex-direction: column;
  gap: 0.35rem;
  padding: 0.55rem 0.75rem 0.55rem;
  border-bottom: 1px solid color-mix(in srgb, var(--theme-border) 55%, transparent);
}

.header-categories__panel--mobile .header-categories__sheet-head {
  padding-top: 0.4rem;
}

.header-categories__handle {
  display: block;
  width: 2.5rem;
  height: 0.28rem;
  margin-inline: auto;
  border-radius: 999px;
  background: rgb(255 255 255 / 22%);
}

.header-categories__sheet-row {
  display: flex;
  align-items: center;
  gap: 0.65rem;
}

.header-categories__sheet-title {
  display: flex;
  min-width: 0;
  flex: 1;
  flex-direction: column;
  gap: 0.1rem;
  text-align: right;
}

.header-categories__close {
  display: grid;
  width: 2.5rem;
  height: 2.5rem;
  flex-shrink: 0;
  place-items: center;
  border: 0;
  border-radius: 0.75rem;
  background: rgb(255 255 255 / 6%);
  color: var(--theme-text-secondary);
  transition: background-color 140ms ease, color 140ms ease;
}

.header-categories__close:hover,
.header-categories__close:focus-visible {
  background: rgb(255 255 255 / 10%);
  color: var(--theme-text-primary);
  outline: none;
}

.header-categories__body {
  min-height: 0;
  flex: 1 1 auto;
  overflow-x: hidden;
  overflow-y: auto;
  overscroll-behavior: contain;
  -webkit-overflow-scrolling: touch;
  padding: 0.65rem 0.75rem 0.9rem;
  display: flex;
  flex-direction: column;
  gap: 0.95rem;
}

.header-categories__section {
  display: flex;
  flex-direction: column;
  gap: 0.45rem;
}

.header-categories__label {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  margin: 0;
  font-size: 0.7rem;
  font-weight: 800;
  letter-spacing: 0.02em;
  color: var(--theme-text-muted);
}

.header-categories__count {
  display: inline-flex;
  min-width: 1.35rem;
  justify-content: center;
  border-radius: 999px;
  background: rgb(255 255 255 / 7%);
  padding: 0.05rem 0.4rem;
  font-size: 0.65rem;
  font-weight: 700;
  color: var(--theme-text-secondary);
}

.header-categories__chips {
  display: flex;
  flex-wrap: wrap;
  gap: 0.4rem;
}

.header-categories__chip {
  display: inline-flex;
  min-height: 2.35rem;
  align-items: center;
  gap: 0.35rem;
  border-radius: 0.85rem;
  background: rgb(255 255 255 / 5%);
  padding: 0.35rem 0.7rem;
  font-size: 0.78rem;
  font-weight: 700;
  color: var(--theme-text-primary);
  transition: background-color 140ms ease, color 140ms ease;
}

.header-categories__chip:hover,
.header-categories__chip:focus-visible {
  background: rgb(255 255 255 / 10%);
  outline: none;
}

.header-categories__browse {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0.4rem;
}

@media (min-width: 640px) {
  .header-categories__browse {
    grid-template-columns: repeat(4, minmax(0, 1fr));
  }
}

.header-categories__browse-link {
  display: flex;
  min-height: 2.6rem;
  align-items: center;
  gap: 0.45rem;
  border-radius: 0.9rem;
  background: rgb(255 255 255 / 4%);
  padding: 0.45rem 0.65rem;
  font-size: 0.8rem;
  font-weight: 700;
  color: var(--theme-text-primary);
  transition: background-color 140ms ease;
}

.header-categories__browse-link:hover,
.header-categories__browse-link:focus-visible {
  background: rgb(255 255 255 / 9%);
  outline: none;
}

.header-categories__genres-head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem;
}

.header-categories__search {
  display: inline-flex;
  min-height: 2.25rem;
  min-width: min(100%, 11rem);
  flex: 1 1 10rem;
  max-width: 16rem;
  align-items: center;
  gap: 0.4rem;
  border-radius: 0.8rem;
  background: rgb(0 0 0 / 28%);
  padding: 0.3rem 0.65rem;
  color: var(--theme-text-secondary);
}

.header-categories__search-input {
  width: 100%;
  border: 0;
  background: transparent;
  color: var(--theme-text-primary);
  font-size: 0.8rem;
  outline: none;
}

.header-categories__search-input::placeholder {
  color: var(--theme-text-muted);
}

.header-categories__genre-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0.4rem;
}

@media (min-width: 640px) {
  .header-categories__genre-grid {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}

@media (min-width: 1024px) {
  .header-categories__genre-grid {
    grid-template-columns: repeat(4, minmax(0, 1fr));
  }
}

.header-categories__genre {
  display: flex;
  min-height: 2.55rem;
  align-items: center;
  gap: 0.45rem;
  border-radius: 0.85rem;
  background: rgb(255 255 255 / 4%);
  padding: 0.4rem 0.6rem;
  font-size: 0.78rem;
  font-weight: 700;
  color: var(--theme-text-primary);
  transition: background-color 140ms ease, box-shadow 140ms ease;
}

.header-categories__genre-title {
  flex: 1 1 auto;
  min-width: 0;
}

.header-categories__genre-count {
  flex-shrink: 0;
  margin-inline-start: auto;
  border-radius: 999px;
  background: rgb(255 255 255 / 8%);
  padding: 0.12rem 0.45rem;
  font-size: 0.68rem;
  font-weight: 700;
  color: var(--theme-text-muted);
  line-height: 1.2;
}

.header-categories__genre:hover,
.header-categories__genre:focus-visible {
  background: rgb(255 255 255 / 9%);
  outline: none;
}

.header-categories__genre--featured {
  box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--theme-brand, #5ad67d) 35%, transparent);
}

.header-categories__empty {
  margin: 0.35rem 0 0;
  font-size: 0.8rem;
  color: var(--theme-text-muted);
}

@media (max-width: 379px) {
  .header-categories__body {
    padding: 0.5rem 0.55rem 0.75rem;
    gap: 0.8rem;
  }
}

.cat-backdrop-enter-active,
.cat-backdrop-leave-active {
  transition: opacity 180ms ease;
}

.cat-backdrop-enter-from,
.cat-backdrop-leave-to {
  opacity: 0;
}

.cat-panel-mobile-enter-active,
.cat-panel-mobile-leave-active {
  transition: transform 260ms cubic-bezier(0.22, 1, 0.36, 1), opacity 200ms ease;
}

.cat-panel-mobile-enter-from,
.cat-panel-mobile-leave-to {
  opacity: 0.85;
  transform: translateY(100%);
}

.header-categories__panel--tablet.cat-panel-mobile-enter-from,
.header-categories__panel--tablet.cat-panel-mobile-leave-to {
  opacity: 0;
  transform: translate(-50%, -0.5rem) scale(0.98);
}

.cat-panel-desktop-enter-active,
.cat-panel-desktop-leave-active {
  transition: opacity 160ms ease, transform 180ms cubic-bezier(0.22, 1, 0.36, 1);
}

.cat-panel-desktop-enter-from,
.cat-panel-desktop-leave-to {
  opacity: 0;
  transform: translateY(-0.4rem) scale(0.985);
}

@media (prefers-reduced-motion: reduce) {
  .cat-backdrop-enter-active,
  .cat-backdrop-leave-active,
  .cat-panel-mobile-enter-active,
  .cat-panel-mobile-leave-active,
  .cat-panel-desktop-enter-active,
  .cat-panel-desktop-leave-active {
    transition: none !important;
  }
}
</style>
