<script setup lang="ts">
import type { Genre } from '~/types'

const props = withDefaults(defineProps<{
  genres: Genre[]
  modelValue?: string
  allLabel?: string
  placeholder?: string
  compact?: boolean
}>(), {
  modelValue: '',
  allLabel: 'همه ژانرها',
  placeholder: 'جستجوی ژانر...',
  compact: false,
})

const emit = defineEmits<{
  'update:modelValue': [value: string]
}>()

const { trackGenreClick } = useAnalyticsEvent()

const root = useTemplateRef<HTMLElement>('root')
const trigger = useTemplateRef<HTMLButtonElement>('trigger')
const optionsList = useTemplateRef<HTMLElement>('optionsList')
const searchInput = useTemplateRef<HTMLInputElement>('searchInput')
const instanceId = useId()
const isOpen = ref(false)
const openAbove = ref(false)
const searchQuery = ref('')
const activeIndex = ref(0)

const selectedGenre = computed(() =>
  props.modelValue ? props.genres.find(g => g.slug === props.modelValue) : null,
)

const filteredGenres = computed(() => {
  if (!searchQuery.value) return props.genres
  const q = searchQuery.value.replace(/[يى]/g, 'ی').replace(/ك/g, 'ک').toLowerCase()
  return props.genres.filter(g =>
    g.title.replace(/[يى]/g, 'ی').replace(/ك/g, 'ک').toLowerCase().includes(q)
  )
})

function scrollActiveIntoView() {
  nextTick(() => {
    const list = optionsList.value
    const option = document.getElementById(optionId(activeIndex.value))
    if (activeIndex.value < 0 || !list || !option) return
    const top = option.offsetTop
    const bottom = top + option.offsetHeight
    if (top < list.scrollTop) list.scrollTop = top
    else if (bottom > list.scrollTop + list.clientHeight) list.scrollTop = bottom - list.clientHeight
  })
}

function optionId(index: number) {
  return `${instanceId}-genre-${index}`
}

function openMenu() {
  if (!props.genres.length) return
  const rect = trigger.value?.getBoundingClientRect()
  openAbove.value = Boolean(rect && rect.bottom + 400 > window.innerHeight && rect.top > 400)
  searchQuery.value = ''
  activeIndex.value = props.modelValue
    ? props.genres.findIndex(g => g.slug === props.modelValue)
    : -1
  if (activeIndex.value < -1) activeIndex.value = -1
  isOpen.value = true
  nextTick(() => searchInput.value?.focus())
  scrollActiveIntoView()
}

function closeMenu({ restoreFocus = false } = {}) {
  if (!isOpen.value) return
  isOpen.value = false
  if (restoreFocus) nextTick(() => trigger.value?.focus())
}

function toggleMenu() {
  if (isOpen.value) closeMenu()
  else openMenu()
}

function moveActive(step: number) {
  const total = filteredGenres.value.length
  if (!total) return
  const firstIndex = searchQuery.value ? 0 : -1
  const optionCount = total + (firstIndex === -1 ? 1 : 0)
  const offset = activeIndex.value - firstIndex
  activeIndex.value = ((offset + step + optionCount) % optionCount) + firstIndex
  scrollActiveIntoView()
}

function choose(slug: string) {
  if (slug !== props.modelValue) {
    emit('update:modelValue', slug)
    if (slug) trackGenreClick(slug)
  }
  closeMenu({ restoreFocus: true })
}

function handleKeydown(event: KeyboardEvent) {
  if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
    event.preventDefault()
    if (!isOpen.value) openMenu()
    else moveActive(event.key === 'ArrowDown' ? 1 : -1)
    return
  }

  if (event.key === 'Home' || event.key === 'End') {
    if (!isOpen.value || !filteredGenres.value.length) return
    event.preventDefault()
    activeIndex.value = event.key === 'Home' && !searchQuery.value
      ? -1
      : event.key === 'Home'
        ? 0
        : filteredGenres.value.length - 1
    scrollActiveIntoView()
    return
  }

  if (event.key === 'Enter') {
    event.preventDefault()
    if (!isOpen.value) openMenu()
    else {
      if (activeIndex.value === -1) choose('')
      else {
        const option = filteredGenres.value[activeIndex.value]
        if (option) choose(option.slug)
      }
    }
    return
  }

  if (event.key === 'Escape') {
    event.preventDefault()
    if (searchQuery.value && isOpen.value) {
      searchQuery.value = ''
      return
    }
    closeMenu({ restoreFocus: true })
  }
}

watch(searchQuery, (value) => {
  activeIndex.value = value
    ? 0
    : props.modelValue
      ? props.genres.findIndex(genre => genre.slug === props.modelValue)
      : -1
})

onClickOutside(root, () => closeMenu())
</script>

<template>
  <div
    ref="root"
    class="genre-select"
    :class="[isOpen && 'genre-select--open', compact && 'genre-select--compact']"
  >
    <button
      :id="`${instanceId}-trigger`"
      ref="trigger"
      type="button"
      role="combobox"
      class="genre-select__trigger"
      :aria-label="'انتخاب ژانر'"
      :aria-expanded="isOpen"
      :aria-controls="`${instanceId}-listbox`"
      :aria-activedescendant="isOpen ? optionId(activeIndex) : undefined"
      aria-haspopup="listbox"
      @click="toggleMenu"
      @keydown="handleKeydown"
    >
      <span class="genre-select__trigger-icon" aria-hidden="true">
        <CinematicIcon v-if="selectedGenre" :name="selectedGenre.icon" class="size-4" />
        <CinematicIcon v-else name="tag" class="size-4" />
      </span>
      <span class="min-w-0 flex-1 truncate text-right">
        {{ selectedGenre?.title || allLabel }}
      </span>
      <CinematicIcon
        name="chevron-down"
        class="genre-select__chevron size-4 shrink-0"
        :class="isOpen && 'rotate-180'"
        aria-hidden="true"
      />
    </button>

    <Transition name="ui-dropdown">
      <div
        v-if="isOpen"
        :id="`${instanceId}-listbox`"
        role="listbox"
        class="genre-select__menu soft-scrollbar"
        :class="openAbove ? 'genre-select__menu--above' : 'genre-select__menu--below'"
        :aria-labelledby="`${instanceId}-trigger`"
      >
        <div class="genre-select__search" role="presentation">
          <CinematicIcon name="search" class="size-4 shrink-0 text-muted" aria-hidden="true" />
          <input
            :id="`${instanceId}-search`"
            ref="searchInput"
            v-model="searchQuery"
            type="text"
            class="genre-select__search-input"
            :placeholder="placeholder"
            aria-label="جستجوی ژانر"
            @keydown.stop="handleKeydown"
          >
          <button
            v-if="searchQuery"
            type="button"
            class="genre-select__search-clear"
            aria-label="پاک کردن جستجو"
            @click="searchQuery = ''"
          >
            <CinematicIcon name="x" class="size-3.5" />
          </button>
        </div>

        <div class="genre-select__all">
          <button
            :id="optionId(-1)"
            type="button"
            role="option"
            class="genre-select__option"
            :class="[
              !modelValue && 'genre-select__option--selected',
              activeIndex === -1 && 'genre-select__option--active',
            ]"
            :aria-selected="!modelValue"
            @mouseenter="activeIndex = -1"
            @click="choose('')"
          >
            <span class="genre-select__option-mark">
              <CinematicIcon v-if="!modelValue" name="check" class="size-3.5" />
            </span>
            <span class="genre-select__option-icon">
              <CinematicIcon name="clapperboard" class="size-4" />
            </span>
            <span class="min-w-0 flex-1 text-right">
              <strong class="block truncate text-xs">{{ allLabel }}</strong>
            </span>
          </button>
        </div>

        <div
          v-if="!filteredGenres.length"
          class="genre-select__empty"
          role="status"
        >
          <CinematicIcon name="search" class="size-5 text-muted" />
          <p class="text-xs text-muted">ژانری با این نام پیدا نشد</p>
        </div>

        <div v-else ref="optionsList" class="genre-select__options">
          <button
            v-for="(genre, index) in filteredGenres"
            :id="optionId(index)"
            :key="genre.id"
            type="button"
            role="option"
            class="genre-select__option"
            :class="[
              modelValue === genre.slug && 'genre-select__option--selected',
              index === activeIndex && 'genre-select__option--active',
            ]"
            :aria-selected="modelValue === genre.slug"
            @mouseenter="activeIndex = index"
            @click="choose(genre.slug)"
          >
            <span class="genre-select__option-mark">
              <CinematicIcon v-if="modelValue === genre.slug" name="check" class="size-3.5" />
            </span>
            <span class="genre-select__option-icon">
              <CinematicIcon :name="genre.icon" class="size-4" />
            </span>
            <span class="min-w-0 flex-1 text-right">
              <strong class="block truncate text-xs">{{ genre.title }}</strong>
            </span>
          </button>
        </div>
      </div>
    </Transition>
  </div>
</template>

<style scoped>
@reference "../../assets/css/main.css";

.genre-select {
  @apply relative;
}

.genre-select__trigger {
  @apply inline-flex min-h-11 w-full items-center gap-2 rounded-xl px-3.5 py-2.5 text-sm font-bold ring-1 ring-line transition-colors;
  @apply bg-elevated text-secondary hover:text-primary-300 hover:ring-primary-500/40;
}

.genre-select--open .genre-select__trigger {
  @apply ring-primary-500/50 text-primary-300;
}

.genre-select--compact .genre-select__trigger {
  @apply min-h-10 py-2 text-xs;
}

.genre-select__trigger-icon {
  @apply grid shrink-0 place-items-center text-primary-400;
}

.genre-select__chevron {
  @apply text-muted transition-transform duration-200;
}

.genre-select__menu {
  @apply absolute mt-1 w-full overflow-hidden rounded-xl border border-line bg-elevated shadow-2xl;
  @apply backdrop-blur-xl;
  z-index: 60;
}

.genre-select__menu--below {
  @apply top-full;
}

.genre-select__menu--above {
  @apply bottom-full mb-1;
}

.genre-select__search {
  @apply flex items-center gap-2 border-b border-line px-3 py-2.5;
}

.genre-select__search-input {
  @apply min-w-0 flex-1 bg-transparent text-xs font-bold text-ink outline-none placeholder:text-muted;
}

.genre-select__search-clear {
  @apply grid size-5 shrink-0 place-items-center rounded-md text-muted transition hover:bg-white/10 hover:text-ink;
}

.genre-select__all {
  @apply border-b border-line;
}

.genre-select__options {
  @apply max-h-56 overflow-y-auto;
}

.genre-select__empty {
  @apply flex flex-col items-center gap-2 py-6;
}

.genre-select__option {
  @apply flex w-full items-center gap-2 px-3 py-2.5 text-right transition-colors;
}

.genre-select__option--active {
  @apply bg-white/[.06];
}

.genre-select__option--selected {
  @apply bg-primary-500/10;
}

.genre-select__option-mark {
  @apply grid size-4 shrink-0 place-items-center text-primary-400;
}

.genre-select__option-icon {
  @apply grid size-7 shrink-0 place-items-center rounded-lg bg-white/[.06] text-primary-400;
}

.genre-select__option--selected .genre-select__option-icon {
  @apply bg-primary-500/14 text-primary-300;
}
</style>
