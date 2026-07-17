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

const groupedGenres = computed(() =>
  groups.map(g => ({
    ...g,
    relatedGenres: g.genreSlugs
      .map(s => genres.find(genre => genre.slug === s))
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

function openGroup(idx: number) {
  openIndex.value = idx
}

function closeGroup() {
  openIndex.value = -1
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
        @mouseenter="openGroup(idx)"
        @mouseleave="closeGroup"
      >
        <NuxtLink
          :to="group.path"
          class="relative flex h-10 items-center gap-1.5 rounded-xl px-2.5 text-sm font-bold transition-colors 2xl:px-3"
          :class="isActiveGroup(group) ? 'bg-primary-500/13 text-primary-300' : 'text-slate-400 hover:bg-white/[.055] hover:text-white'"
          :aria-current="isActiveGroup(group) ? 'page' : undefined"
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
            class="header-dropdown absolute right-0 top-full z-50 mt-2 w-64 rounded-2xl p-3 shadow-2xl"
            @mouseenter="openGroup(idx)"
            @mouseleave="closeGroup"
          >
            <div class="mb-2 flex items-center gap-2.5 px-1 pb-2">
              <span class="grid size-8 place-items-center rounded-xl bg-primary-500/13 text-primary-300">
                <CinematicIcon :name="group.icon" class="size-4" />
              </span>
              <span class="text-xs font-black text-ink">{{ group.label }}</span>
            </div>
            <div class="flex flex-wrap gap-1.5" role="group" :aria-label="`ژانرهای ${group.label}`">
              <NuxtLink
                v-for="genre in group.relatedGenres"
                :key="genre.slug"
                :to="{ path: group.path, query: { ...group.query, genre: genre.slug } }"
                class="inline-flex items-center gap-1.5 rounded-xl px-2.5 py-1.5 text-[11px] font-bold ring-1 ring-transparent transition-colors"
                :class="isActiveGenre(genre.slug) ? 'bg-energy-500/14 text-energy-300 ring-energy-400/20' : 'text-slate-400 hover:bg-white/[.06] hover:text-white'"
                :aria-current="isActiveGenre(genre.slug) ? 'page' : undefined"
                @click="pickGenre(genre.slug)"
              >
                <CinematicIcon :name="genre.icon" class="size-3.5 shrink-0 text-primary-400" />
                {{ genre.title }}
              </NuxtLink>
            </div>
            <NuxtLink
              :to="group.path"
              class="mt-3 flex items-center justify-center gap-1.5 rounded-xl border border-line bg-white/[.03] py-2 text-[10px] font-black text-muted transition hover:border-primary-500/40 hover:text-primary-300"
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
