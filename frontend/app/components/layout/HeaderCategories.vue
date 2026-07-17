<script setup lang="ts">
import type { CinematicIconName } from '~/types'

const route = useRoute()
const { genres } = useCatalog()
const { trackGenreClick } = useAnalyticsEvent()

const menuRoot = ref<HTMLElement | null>(null)
const trigger = ref<HTMLButtonElement | null>(null)
const isOpen = ref(false)
const genreSearch = ref('')

interface QuickCategory {
  label: string
  hint: string
  to: string
  icon: CinematicIconName
}

const quickCategories: QuickCategory[] = [
  { label: 'همه فیلم‌ها', hint: 'فهرست کامل فیلم‌ها', to: '/movies', icon: 'movie' },
  { label: 'همه سریال‌ها', hint: 'فصل‌ها و قسمت‌ها', to: '/series', icon: 'series' },
  { label: 'انیمیشن', hint: 'برای همه سنین', to: '/movies?format=animation', icon: 'animation' },
  { label: 'تازه‌ها', hint: 'جدیدترین عناوین', to: '/movies?sort=newest', icon: 'sparkles' },
  { label: 'ترندها', hint: 'محبوب‌های امروز', to: '/movies?sort=trending', icon: 'trend' },
  { label: 'پیشنهاد برای تو', hint: 'بر اساس سلیقه‌ات', to: '/?section=recommended', icon: 'ai' },
  { label: 'تماشای گروهی', hint: 'اتاق خصوصی با دوستان', to: '/watch-party', icon: 'users' },
]

const filteredGenres = computed(() => {
  if (!genreSearch.value) return genres
  const q = genreSearch.value.replace(/[يى]/g, 'ی').replace(/ك/g, 'ک').toLowerCase()
  return genres.filter(g =>
    g.title.replace(/[يى]/g, 'ی').replace(/ك/g, 'ک').toLowerCase().includes(q)
  )
})

const hasActiveCategory = computed(() => Boolean(
  route.path.startsWith('/watch-party')
  || route.query.genre
  || route.query.format
  || route.query.sort
  || route.query.section === 'recommended',
))

function isActive(to: string) {
  const [targetPath = '/', targetQuery] = to.split('?')
  if (route.path !== targetPath) return false

  if (!targetQuery) {
    return !route.query.genre && !route.query.format && !route.query.sort && !route.query.section
  }

  const expected = new URLSearchParams(targetQuery)
  return [...expected.entries()].every(([key, value]) => route.query[key] === value)
}

function closeMenu() {
  isOpen.value = false
  genreSearch.value = ''
}

function closeFromKeyboard() {
  if (!isOpen.value) return
  closeMenu()
  trigger.value?.focus()
}

function chooseGenre(slug: string) {
  trackGenreClick(slug)
  closeMenu()
}

onClickOutside(menuRoot, closeMenu)
onKeyStroke('Escape', closeFromKeyboard)
watch(() => route.fullPath, closeMenu)
</script>

<template>
  <div ref="menuRoot" class="relative shrink-0">
    <button v-if="isOpen" type="button" class="fixed inset-0 z-40 cursor-default bg-black/35 lg:hidden" aria-label="بستن منوی دسته‌بندی" @click="closeMenu" />
    <button
      id="header-categories-trigger"
      ref="trigger"
      type="button"
      class="relative inline-flex size-11 items-center justify-center gap-2 rounded-xl px-0 text-sm font-bold ring-1 ring-transparent transition-colors lg:h-10 lg:w-auto lg:px-3"
      :class="isOpen || hasActiveCategory ? 'bg-primary-500/13 text-primary-300 ring-primary-400/15' : 'text-slate-400 hover:bg-white/[.055] hover:text-white'"
      aria-label="دسته‌بندی‌های محتوا"
      :aria-expanded="isOpen"
      aria-controls="header-categories-menu"
      @click="isOpen = !isOpen"
    >
      <CinematicIcon name="grid" class="size-4.5" />
      <span class="hidden lg:inline">دسته‌بندی‌ها</span>
      <CinematicIcon name="chevron-down" class="hidden size-3.5 transition-transform lg:block" :class="isOpen && 'rotate-180'" />
      <span v-if="hasActiveCategory" class="absolute inset-x-5 -bottom-3.5 h-0.5 rounded-full bg-primary-500" aria-hidden="true" />
    </button>

    <Transition name="header-dropdown">
      <div
        v-if="isOpen"
        id="header-categories-menu"
        class="header-dropdown soft-scrollbar fixed inset-x-3 top-[132px] z-50 max-h-[calc(100dvh-9rem)] overflow-y-auto rounded-3xl p-3 text-right md:top-[76px] md:max-h-[calc(100dvh-6rem)] lg:absolute lg:inset-x-auto lg:right-0 lg:top-[calc(100%+0.8rem)] lg:max-h-[80vh] lg:w-[42rem] lg:max-w-[calc(100vw-2rem)]"
        aria-labelledby="header-categories-trigger"
      >
        <div class="mb-3 flex items-center justify-between gap-3 rounded-2xl border border-white/[.06] bg-white/[.025] px-3 py-2.5">
          <div class="flex min-w-0 items-center gap-2.5">
            <span class="grid size-9 shrink-0 place-items-center rounded-xl bg-primary-500/14 text-primary-400">
              <CinematicIcon name="clapperboard" class="size-4.5" />
            </span>
            <span class="min-w-0">
              <strong class="block text-xs font-black text-ink">کشف سریع محتوا</strong>
              <span class="block truncate text-[9px] text-muted">مسیر تماشای امشب را انتخاب کن</span>
            </span>
          </div>
          <span class="rounded-lg bg-crimson/15 px-2 py-1 text-[9px] font-black text-crimson-hover ring-1 ring-crimson/25">{{ genres.length }} ژانر</span>
        </div>

        <div class="grid grid-cols-2 gap-2 sm:grid-cols-3">
          <NuxtLink
            v-for="category in quickCategories"
            :key="category.to"
            :to="category.to"
            class="group flex min-w-0 items-center gap-2.5 rounded-2xl px-3 py-2.5 ring-1 transition-colors"
            :class="isActive(category.to) ? 'bg-primary-500/14 text-primary-200 ring-primary-400/25' : 'bg-white/[.035] text-slate-300 ring-white/[.06] hover:bg-white/[.07] hover:text-white hover:ring-white/10'"
            :aria-current="isActive(category.to) ? 'page' : undefined"
            @click="closeMenu"
          >
            <span class="grid size-9 shrink-0 place-items-center rounded-xl bg-white/[.05] text-primary-400 transition-colors group-hover:bg-primary-500 group-hover:text-night-950">
              <CinematicIcon :name="category.icon" class="size-4.5" />
            </span>
            <span class="min-w-0">
              <strong class="block truncate text-xs font-black">{{ category.label }}</strong>
              <span class="mt-0.5 block truncate text-[9px] text-slate-500">{{ category.hint }}</span>
            </span>
          </NuxtLink>
        </div>

        <div class="my-3 h-px bg-gradient-to-l from-transparent via-white/10 to-transparent" />

        <div class="flex items-center justify-between gap-3 px-1 pb-2">
          <p class="text-[10px] font-black tracking-[.06em] text-slate-500">مرور بر اساس ژانر</p>
        </div>

        <div class="relative mb-3">
          <div class="flex items-center gap-2 rounded-xl bg-white/[.05] px-3 py-2.5 ring-1 ring-white/[.08] transition focus-within:ring-primary-500/40">
            <CinematicIcon name="search" class="size-3.5 shrink-0 text-slate-500" />
            <input
              v-model="genreSearch"
              type="text"
              class="min-w-0 flex-1 bg-transparent text-xs font-bold text-white outline-none placeholder:text-slate-500"
              placeholder="جستجوی ژانر..."
              aria-label="جستجوی ژانر"
            >
            <button
              v-if="genreSearch"
              type="button"
              class="grid size-5 shrink-0 place-items-center rounded-md text-slate-500 transition hover:bg-white/10 hover:text-white"
              aria-label="پاک کردن جستجو"
              @click="genreSearch = ''"
            >
              <CinematicIcon name="x" class="size-3" />
            </button>
          </div>
        </div>

        <div
          v-if="!filteredGenres.length"
          class="flex flex-col items-center gap-2 py-6"
          role="status"
        >
          <CinematicIcon name="search" class="size-6 text-slate-600" />
          <p class="text-xs font-bold text-slate-500">ژانری با این نام پیدا نشد</p>
        </div>

        <div v-else class="grid grid-cols-3 gap-1.5 sm:grid-cols-4" role="group" aria-label="ژانرها">
          <NuxtLink
            v-for="genre in filteredGenres"
            :key="genre.id"
            :to="{ path: '/movies', query: { genre: genre.slug } }"
            class="flex min-w-0 items-center gap-2 rounded-xl px-2.5 py-2 text-[11px] font-bold ring-1 ring-transparent transition-colors"
            :class="route.path === '/movies' && route.query.genre === genre.slug ? 'bg-energy-500/14 text-energy-300 ring-energy-400/20' : 'text-slate-400 hover:bg-white/[.055] hover:text-white'"
            :aria-current="route.path === '/movies' && route.query.genre === genre.slug ? 'page' : undefined"
            @click="chooseGenre(genre.slug)"
          >
            <CinematicIcon :name="genre.icon" class="size-3.5 shrink-0 text-primary-400" />
            <span class="truncate">{{ genre.title }}</span>
          </NuxtLink>
        </div>

        <div class="mt-3 flex justify-center border-t border-white/[.06] pt-3">
          <NuxtLink
            to="/movies"
            class="inline-flex min-h-10 items-center gap-1.5 rounded-xl bg-white/[.05] px-4 text-[10px] font-black text-slate-400 ring-1 ring-white/[.06] transition hover:bg-primary-500 hover:text-night-950 hover:ring-primary-400"
            @click="closeMenu"
          >
            <CinematicIcon name="movie" class="size-3.5" />
            مرور همه فیلم‌ها و سریال‌ها
          </NuxtLink>
        </div>
      </div>
    </Transition>
  </div>
</template>
