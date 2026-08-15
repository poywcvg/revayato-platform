<script setup lang="ts">
import type { CinematicIconName, Genre } from '~/types'

const route = useRoute()
const { genres } = useCatalog()
const { trackGenreClick } = useAnalyticsEvent()

interface GenreGroup {
  label: string
  icon: CinematicIconName
  path: string
  query: Record<string, string>
  genreSlugs: string[]
}

const groups: GenreGroup[] = [
  {
    label: 'فیلم‌ها',
    icon: 'movie',
    path: '/movies',
    query: {},
    genreSlugs: ['drama', 'sci-fi', 'crime', 'action', 'romance', 'comedy', 'horror', 'thriller', 'fantasy', 'adventure', 'mystery', 'documentary', 'biography', 'history', 'war', 'western', 'musical', 'sport', 'superhero', 'psychological', 'political', 'disaster', 'legal', 'film-noir', 'music'],
  },
  {
    label: 'سریال‌ها',
    icon: 'series',
    path: '/series',
    query: {},
    genreSlugs: ['drama', 'sci-fi', 'crime', 'mystery', 'romance', 'action', 'fantasy', 'comedy', 'horror', 'family', 'thriller', 'documentary', 'history', 'war', 'political', 'legal', 'reality-tv', 'anime', 'psychological'],
  },
  {
    label: 'انیمیشن',
    icon: 'animation',
    path: '/movies',
    query: { format: 'animation' },
    genreSlugs: ['animation', 'anime', 'kids', 'family', 'fantasy', 'comedy', 'adventure', 'musical', 'action'],
  },
]

const openIndex = ref(-1)
const menuRoot = ref<HTMLElement | null>(null)
const panelAlignEnd = ref(false)

const groupedGenres = computed(() =>
  groups.map(g => ({
    ...g,
    relatedGenres: g.genreSlugs
      .map(s => genres.value.find(genre => genre.slug === s))
      .filter((g): g is Genre => !!g),
  }))
)

function isActiveGroup(group: GenreGroup) {
  if (group.path === '/movies' && !group.query.format) return route.path === '/movies' && !route.query.format && !route.query.genre
  if (group.path === '/series') return route.path.startsWith('/series')
  if (group.query.format) return route.query.format === 'animation'
  return false
}

function isActiveGenre(slug: string) {
  return route.path === '/movies' && route.query.genre === slug
}

function openGroup(idx: number, event?: MouseEvent) {
  openIndex.value = idx
  const el = event?.currentTarget as HTMLElement | undefined
  const anchor = el ?? null
  if (!import.meta.client || !anchor) {
    panelAlignEnd.value = false
    return
  }
  const rect = anchor.getBoundingClientRect()
  const panelWidth = Math.min(20 * 16, window.innerWidth - 24)
  const isRtl = getComputedStyle(document.documentElement).direction === 'rtl'
  panelAlignEnd.value = isRtl
    ? rect.right - panelWidth < 12
    : rect.left + panelWidth > window.innerWidth - 12
}

function closeGroup() {
  openIndex.value = -1
  panelAlignEnd.value = false
}

function pickGenre(slug: string) {
  trackGenreClick(slug)
  closeGroup()
}

onClickOutside(menuRoot, closeGroup)
onKeyStroke('Escape', closeGroup)
watch(() => route.fullPath, closeGroup)
</script>

<template>
  <div ref="menuRoot" class="flex h-full items-center gap-0.5">
    <template v-for="(group, idx) in groupedGenres" :key="group.label">
      <div
        class="relative h-full"
        @mouseenter="openGroup(idx, $event)"
        @mouseleave="closeGroup"
      >
        <NuxtLink
          :to="group.path"
          class="relative flex h-11 items-center gap-1.5 rounded-xl px-2.5 text-sm font-bold transition-colors 2xl:px-3"
          :class="isActiveGroup(group) ? 'bg-primary-500/13 text-brand' : 'text-secondary hover:bg-elevated hover:text-ink'"
          :aria-current="isActiveGroup(group) ? 'page' : undefined"
          :aria-expanded="openIndex === idx"
          :aria-controls="`header-genre-menu-${idx}`"
          @click="closeGroup"
        >
          <CinematicIcon :name="group.icon" class="size-4.5" />
          {{ group.label }}
          <CinematicIcon name="chevron-down" class="size-3.5 text-muted transition-transform" :class="openIndex === idx && 'rotate-180'" />
          <span v-if="isActiveGroup(group)" class="absolute inset-x-4 -bottom-3.5 h-0.5 rounded-full bg-primary-500" aria-hidden="true" />
        </NuxtLink>

        <Transition name="header-dropdown">
          <div
            v-if="openIndex === idx"
            :id="`header-genre-menu-${idx}`"
            class="header-dropdown header-nav-genre__panel absolute top-full z-50 mt-2 rounded-2xl p-3 shadow-2xl"
            :class="panelAlignEnd ? 'end-0 start-auto' : 'start-0'"
            role="menu"
            :aria-label="`ژانرهای ${group.label}`"
            @mouseenter="openGroup(idx)"
            @mouseleave="closeGroup"
          >
            <div class="mb-2 flex items-center gap-2.5 px-1 pb-2">
              <span class="grid size-8 place-items-center rounded-xl bg-primary-500/13 text-primary-300">
                <CinematicIcon :name="group.icon" class="size-4" />
              </span>
              <span class="text-xs font-black text-ink">{{ group.label }}</span>
            </div>
            <div class="header-nav-genre__chips soft-scrollbar" role="group" :aria-label="`ژانرهای ${group.label}`">
              <NuxtLink
                v-for="genre in group.relatedGenres"
                :key="genre.slug"
                :to="{ path: group.path, query: { ...group.query, genre: genre.slug } }"
                class="inline-flex min-h-10 items-center gap-1.5 rounded-xl px-2.5 py-1.5 text-[11px] font-bold ring-1 ring-transparent transition-colors"
                :class="isActiveGenre(genre.slug) ? 'bg-energy-500/14 text-brand ring-energy-400/20' : 'text-secondary hover:bg-elevated hover:text-ink'"
                :aria-current="isActiveGenre(genre.slug) ? 'page' : undefined"
                role="menuitem"
                @click="pickGenre(genre.slug)"
              >
                <CinematicIcon :name="genre.icon" class="size-3.5 shrink-0 text-primary-400" />
                {{ genre.title }}
              </NuxtLink>
            </div>
            <NuxtLink
              :to="group.path"
              class="mt-3 flex min-h-11 items-center justify-center gap-1.5 rounded-xl border border-line bg-elevated/70 py-2 text-[10px] font-black text-muted transition hover:border-primary-500/40 hover:bg-elevated hover:text-brand"
              role="menuitem"
              @click="closeGroup"
            >
              <CinematicIcon name="arrow-left" class="size-3.5" />
              همه {{ group.label }}
            </NuxtLink>
          </div>
        </Transition>
      </div>
    </template>
  </div>
</template>

<style scoped>
.header-nav-genre__panel {
  width: min(20rem, calc(100dvw - 1.5rem));
  max-height: min(70vh, 28rem);
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.header-nav-genre__chips {
  display: flex;
  flex-wrap: wrap;
  gap: 0.375rem;
  max-height: min(42vh, 16rem);
  overflow-y: auto;
  overscroll-behavior: contain;
  padding-bottom: 0.15rem;
}

@media (min-width: 1280px) {
  .header-nav-genre__panel {
    width: min(22rem, calc(100dvw - 2rem));
  }
}
</style>
