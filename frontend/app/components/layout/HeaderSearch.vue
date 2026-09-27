<script setup lang="ts">
import type { SiteActor } from '~/types'
import { adaptApiCatalogItem, type ApiCatalogItem } from '~/data/catalogAdapter'
import type { RankedSearchHit } from '~/utils/searchRank'
import { detailPathForMovie, normalizeSearchText, parseSearchQuery, scoreCatalogItem } from '~/utils/searchRank'
import { preferEnglishName } from '~/utils/displayNames'

interface ApiSearchActor {
  id: number
  name: string
  original_name?: string
  slug: string
  photo?: string | null
}

interface ApiSearchResponse {
  query?: string
  search_text?: string
  year?: number | null
  match_type?: 'direct' | 'similar' | 'none'
  movies?: ApiCatalogItem[]
  series?: ApiCatalogItem[]
  actors?: ApiSearchActor[]
}

type FlatSearchOption =
  | { kind: 'catalog'; hit: RankedSearchHit; section: 'exact' | 'similar' }
  | { kind: 'actor'; actor: SiteActor; section: 'actor' }

const props = withDefaults(defineProps<{
  active?: boolean
  autofocus?: boolean
  compactPlaceholder?: boolean
  inputId?: string
}>(), {
  active: false,
  autofocus: false,
  compactPlaceholder: false,
  inputId: 'header-search-input',
})

const emit = defineEmits<{
  submitted: []
}>()

const route = useRoute()
const config = useRuntimeConfig()
const { api } = useApi()
const root = useTemplateRef<HTMLElement>('root')
const input = useTemplateRef<HTMLInputElement>('input')
const listboxId = computed(() => `${props.inputId}-listbox`)

function queryFromRoute() {
  if (route.path !== '/search') return ''
  return [String(route.query.q || '').trim(), String(route.query.year || '').trim()]
    .filter(Boolean)
    .join(' ')
}

const query = ref(queryFromRoute())
const focused = ref(false)
const open = ref(false)
const activeIndex = ref(-1)
const actorHits = ref<SiteActor[]>([])
const remoteHits = shallowRef<RankedSearchHit[]>([])
const resolvedRemoteQuery = ref('')
const remotePending = ref(false)
const remoteError = ref(false)
let remoteRequestId = 0
let remoteAbortController: AbortController | null = null
const { trackSearch } = useAnalyticsEvent()

// Always query the live catalog API so newly published titles appear immediately.
// Do not rank against the lean home catalog cache — that subset misses most of the archive.
// /search/suggest/ answers from an in-memory index in milliseconds, so a short
// debounce only coalesces bursts of fast typing instead of hiding latency.
const debouncedQuery = refDebounced(query, 90)

interface CachedSuggestion {
  hits: RankedSearchHit[]
  actors: SiteActor[]
}
// Backspacing or retyping a prefix is answered instantly from this LRU.
const SUGGESTION_CACHE_SIZE = 80
const suggestionCache = new Map<string, CachedSuggestion>()

function rememberSuggestion(key: string, value: CachedSuggestion) {
  suggestionCache.delete(key)
  suggestionCache.set(key, value)
  if (suggestionCache.size > SUGGESTION_CACHE_SIZE) {
    const oldest = suggestionCache.keys().next().value
    if (oldest !== undefined) suggestionCache.delete(oldest)
  }
}
const isAlive = computed(() => focused.value || Boolean(query.value.trim()) || props.active || open.value)

// The empty field cycles through what can be searched (titles, people, a bare
// year) instead of one long placeholder. It pauses while the field is in use
// and never moves for reduced-motion users.
const hints = computed(() => props.compactPlaceholder
  ? ['فیلم یا سریال…', 'نام بازیگر…', 'یا یک سال، مثل 2024']
  : ['جستجوی فیلم و سریال…', 'نام بازیگر را بنویس…', 'یا فقط یک سال، مثل 2024'])
const hintIndex = ref(0)
const reducedMotion = usePreferredReducedMotion()
const hintTicker = useIntervalFn(() => {
  hintIndex.value = (hintIndex.value + 1) % hints.value.length
}, 3200, { immediate: false })
function syncHintTicker() {
  if (focused.value || query.value || reducedMotion.value === 'reduce') hintTicker.pause()
  else hintTicker.resume()
}
onMounted(syncHintTicker)
watch([focused, query, reducedMotion], syncHintTicker)
const normalizedLiveQuery = computed(() => normalizeSearchText(debouncedQuery.value))
const normalizedQuery = computed(() => normalizeSearchText(query.value))
const parsedQuery = computed(() => parseSearchQuery(query.value))
const canSearch = computed(() => Boolean(
  parsedQuery.value.year
  || normalizeSearchText(parsedQuery.value.text).replace(/\s/g, '').length >= 1,
))

// Keep the previous answer on screen until the next one lands: blanking the
// list on every keystroke made the results flicker while typing.
const hits = computed(() => normalizedQuery.value ? remoteHits.value : [] as RankedSearchHit[])

const exactHits = computed(() => hits.value.filter(hit => hit.kind !== 'similar'))
const similarHits = computed(() => hits.value.filter(hit => hit.kind === 'similar'))
const showPanel = computed(() => open.value && focused.value && normalizedQuery.value.length >= 1)
const hasExact = computed(() => exactHits.value.length > 0)
const searching = computed(() => canSearch.value && (
  remotePending.value
  || normalizedQuery.value !== normalizedLiveQuery.value
  || resolvedRemoteQuery.value !== normalizedLiveQuery.value
))
const shortQuery = computed(() => showPanel.value && !canSearch.value)
const emptyState = computed(() => showPanel.value && canSearch.value && !remoteError.value && !hits.value.length && !actorHits.value.length && !searching.value)

interface CatalogSection {
  key: 'exact' | 'similar'
  label: string | null
  hits: RankedSearchHit[]
  offset: number
}

// Direct hits need no heading unless the query was a year; near-matches always
// say they are near-matches so a fuzzy result never passes as the title typed.
const catalogSections = computed<CatalogSection[]>(() => {
  const sections: CatalogSection[] = []
  if (hasExact.value) {
    sections.push({
      key: 'exact',
      label: parsedQuery.value.year ? `آثار سال ${parsedQuery.value.year}` : null,
      hits: exactHits.value,
      offset: 0,
    })
  }
  if (similarHits.value.length) {
    sections.push({
      key: 'similar',
      label: hasExact.value ? 'شبیه به جستجوی تو' : 'نتیجهٔ دقیقی نبود؛ شاید منظورت این‌ها باشد',
      hits: similarHits.value,
      offset: exactHits.value.length,
    })
  }
  return sections
})

const flatHits = computed<FlatSearchOption[]>(() => [
  ...exactHits.value.map(hit => ({ kind: 'catalog' as const, hit, section: 'exact' as const })),
  ...similarHits.value.map(hit => ({ kind: 'catalog' as const, hit, section: 'similar' as const })),
  ...actorHits.value.map(actor => ({ kind: 'actor' as const, actor, section: 'actor' as const })),
])

function adaptSearchActor(actor: ApiSearchActor): SiteActor {
  const names = preferEnglishName(actor.original_name, actor.name)
  const mediaBase = String(config.public.mediaCdnBaseUrl || '')
  let photo = actor.photo || null
  if (photo && !/^(?:https?:)?\/\//.test(photo) && !photo.startsWith('data:')) {
    photo = photo.startsWith('/') ? photo : `/media/${photo}`
    if (/^https?:\/\//.test(mediaBase)) {
      try {
        photo = new URL(photo.replace(/^\/+/, ''), `${mediaBase.replace(/\/$/, '')}/`).toString()
      } catch { /* keep relative */ }
    }
  }
  return {
    id: actor.id,
    name: names.primary || actor.name,
    secondary_name: names.secondary || undefined,
    original_name: actor.original_name,
    slug: actor.slug,
    photo,
  }
}

async function loadRemoteHits(value: string) {
  const term = normalizeSearchText(value)
  const parsed = parseSearchQuery(value)
  const requestId = ++remoteRequestId
  remoteAbortController?.abort()
  remoteAbortController = null
  if (!parsed.year && !normalizeSearchText(parsed.text).replace(/\s/g, '')) {
    actorHits.value = []
    remoteHits.value = []
    resolvedRemoteQuery.value = term
    remotePending.value = false
    remoteError.value = false
    return
  }

  const cacheKey = `${normalizeSearchText(parsed.text)}|${parsed.year || ''}`
  const cached = suggestionCache.get(cacheKey)
  if (cached) {
    rememberSuggestion(cacheKey, cached)
    remoteHits.value = cached.hits
    actorHits.value = cached.actors
    resolvedRemoteQuery.value = term
    remotePending.value = false
    remoteError.value = false
    return
  }

  remotePending.value = true
  remoteError.value = false
  const controller = new AbortController()
  remoteAbortController = controller
  try {
    const response = await api<ApiSearchResponse>('/search/suggest/', {
      query: {
        ...(parsed.text && { q: parsed.text }),
        ...(parsed.year && { year: parsed.year }),
        type: 'all',
        limit: 10,
      },
      signal: controller.signal,
      timeout: 5_000,
    })
    if (requestId !== remoteRequestId) return

    const mediaBase = String(config.public.mediaCdnBaseUrl || '')
    const items = [
      ...(response.movies || []).map(item => adaptApiCatalogItem(item, 'movie', mediaBase)),
      ...(response.series || []).map(item => adaptApiCatalogItem(item, 'series', mediaBase)),
    ]
    remoteHits.value = items
      .map((item, index) => {
        const scored = scoreCatalogItem(item, term)
        const hit: RankedSearchHit = scored || {
          item,
          score: Math.max(1, 100 - index),
          kind: response.match_type === 'similar' ? 'similar' : 'contains',
        }
        if (response.match_type === 'similar') hit.kind = 'similar'
        return { hit, index }
      })
      .sort((left, right) => right.hit.score - left.hit.score || left.index - right.index)
      .slice(0, 12)
      .map(({ hit }) => hit)
    actorHits.value = (response.actors || []).map(adaptSearchActor)
    resolvedRemoteQuery.value = term
    rememberSuggestion(cacheKey, { hits: remoteHits.value, actors: actorHits.value })
  } catch {
    if (requestId !== remoteRequestId) return
    actorHits.value = []
    remoteHits.value = []
    resolvedRemoteQuery.value = term
    remoteError.value = true
  } finally {
    if (requestId === remoteRequestId) {
      remotePending.value = false
      remoteAbortController = null
    }
  }
}

watch(flatHits, () => {
  activeIndex.value = flatHits.value.length ? 0 : -1
})

watch(debouncedQuery, (value) => {
  void loadRemoteHits(value)
})

onClickOutside(root, () => {
  open.value = false
  focused.value = false
})

function submit(term = query.value.trim()) {
  const normalized = term.trim()
  const parsed = parseSearchQuery(normalized)
  trackSearch(normalized, hits.value.length + actorHits.value.length)
  open.value = false
  focused.value = false
  emit('submitted')
  void navigateTo({
    path: '/search',
    query: {
      ...(parsed.text && { q: parsed.text }),
      ...(parsed.year && { year: String(parsed.year) }),
    },
  })
}

function clear() {
  remoteRequestId += 1
  remoteAbortController?.abort()
  remoteAbortController = null
  query.value = ''
  activeIndex.value = -1
  actorHits.value = []
  remoteHits.value = []
  resolvedRemoteQuery.value = ''
  remotePending.value = false
  remoteError.value = false
  open.value = false
  input.value?.focus()
}

onBeforeUnmount(() => {
  remoteAbortController?.abort()
})

function openItem(hit: RankedSearchHit) {
  trackSearch(query.value.trim(), hits.value.length + actorHits.value.length)
  open.value = false
  focused.value = false
  emit('submitted')
  void navigateTo(detailPathForMovie(hit.item))
}

function openActor(actor: SiteActor) {
  trackSearch(query.value.trim(), hits.value.length + actorHits.value.length)
  open.value = false
  focused.value = false
  emit('submitted')
  void navigateTo(`/actors/${encodeURIComponent(actor.slug)}`)
}

function activateOption(option: FlatSearchOption) {
  if (option.kind === 'actor') openActor(option.actor)
  else openItem(option.hit)
}

function onFocus() {
  focused.value = true
  open.value = true
  const term = normalizeSearchText(query.value)
  if (term && resolvedRemoteQuery.value !== term) void loadRemoteHits(query.value)
}

function onInput() {
  open.value = true
  remoteError.value = false
}

function retry() {
  void loadRemoteHits(query.value)
}

function moveActive(delta: number) {
  const total = flatHits.value.length
  if (!total) {
    activeIndex.value = -1
    return
  }
  activeIndex.value = (activeIndex.value + delta + total) % total
}

function onKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape') {
    if (open.value) {
      event.preventDefault()
      open.value = false
      return
    }
  }

  if (!showPanel.value && (event.key === 'ArrowDown' || event.key === 'ArrowUp')) {
    open.value = true
  }

  if (event.key === 'ArrowDown') {
    event.preventDefault()
    moveActive(1)
    return
  }

  if (event.key === 'ArrowUp') {
    event.preventDefault()
    moveActive(-1)
    return
  }

  if (event.key === 'Enter') {
    const active = flatHits.value[activeIndex.value]
    if (showPanel.value && active) {
      event.preventDefault()
      activateOption(active)
    }
  }
}

function focusFromShortcut(event: KeyboardEvent) {
  if (window.matchMedia('(max-width: 1023px)').matches) return
  const target = event.target as HTMLElement | null
  if (target?.matches('input, textarea, select, [contenteditable="true"]')) return
  event.preventDefault()
  input.value?.focus()
}

onKeyStroke('/', focusFromShortcut)
watch(() => route.fullPath, () => {
  query.value = queryFromRoute()
  open.value = false
})

onMounted(async () => {
  if (!props.autofocus) return
  await nextTick()
  input.value?.focus()
})

watch(() => props.autofocus, async (value) => {
  if (!value) return
  await nextTick()
  input.value?.focus()
})
</script>

<template>
  <div ref="root" class="header-search-shell">
    <form
      class="header-search"
      :class="{
        'header-search--alive': isAlive,
        'header-search--active': active,
        'header-search--open': showPanel,
        'header-search--busy': showPanel && searching,
      }"
      role="search"
      @submit.prevent="submit()"
    >
      <label class="sr-only" :for="inputId">جستجوی فیلم، سریال، بازیگر یا سال</label>
      <span class="header-search__icon" aria-hidden="true">
        <CinematicIcon name="search" class="size-[1.05rem]" />
      </span>
      <span class="header-search__field">
        <input
          :id="inputId"
          ref="input"
          v-model="query"
          type="search"
          inputmode="search"
          enterkeyhint="search"
          autocomplete="off"
          autocorrect="off"
          spellcheck="false"
          class="header-search__input"
          role="combobox"
          :aria-expanded="showPanel"
          aria-autocomplete="list"
          :aria-controls="listboxId"
          :aria-activedescendant="activeIndex >= 0 ? `${listboxId}-option-${activeIndex}` : undefined"
          @focus="onFocus"
          @input="onInput"
          @keydown="onKeydown"
        >
        <span v-if="!query" class="header-search__hint" aria-hidden="true">
          <Transition name="search-hint">
            <span :key="hintIndex" class="header-search__hint-text">{{ hints[hintIndex] }}</span>
          </Transition>
        </span>
      </span>
      <button
        v-if="query"
        type="button"
        class="header-search__clear"
        aria-label="پاک کردن جستجو"
        @mousedown.prevent="clear"
      >
        <CinematicIcon name="x" class="size-3.5" />
      </button>
      <kbd v-else class="header-search__kbd" aria-hidden="true">/</kbd>
      <span class="header-search__busy" aria-hidden="true" />
    </form>

    <Transition name="search-suggest">
      <div
        v-if="showPanel"
        :id="listboxId"
        class="header-search__panel"
        role="listbox"
        :aria-label="`پیشنهادهای جستجو برای ${query}`"
      >
        <div v-if="searching && !hits.length && !actorHits.length" class="header-search__skeleton" role="status">
          <span class="sr-only">در حال جستجو…</span>
          <span v-for="n in 3" :key="n" class="header-search__skeleton-row" aria-hidden="true">
            <i class="header-search__skeleton-poster" />
            <span class="header-search__skeleton-lines"><i /><i /></span>
          </span>
        </div>

        <template v-else-if="hits.length || actorHits.length">
          <div
            v-for="section in catalogSections"
            :key="section.key"
            class="header-search__group"
            role="group"
            :aria-label="section.label || 'نتایج'"
          >
            <p v-if="section.label" class="header-search__section-label">{{ section.label }}</p>
            <button
              v-for="(hit, index) in section.hits"
              :id="`${listboxId}-option-${section.offset + index}`"
              :key="`${section.key}-${hit.item.type}-${hit.item.id}`"
              type="button"
              role="option"
              class="header-search__option"
              :class="{ 'header-search__option--active': activeIndex === section.offset + index }"
              :aria-selected="activeIndex === section.offset + index"
              @mousedown.prevent="openItem(hit)"
              @mouseenter="activeIndex = section.offset + index"
            >
              <CinematicImage
                :src="hit.item.poster_url"
                :alt="`پوستر ${hit.item.title}`"
                ratio="poster"
                class="header-search__poster"
                :fallback-label="hit.item.title"
              />
              <span class="header-search__text">
                <span class="header-search__title" dir="auto">{{ hit.item.title }}</span>
                <span class="header-search__meta">
                  <span>{{ hit.item.type === 'movie' ? 'فیلم' : 'سریال' }}</span>
                  <template v-if="hit.item.year">
                    <i class="header-search__dot" aria-hidden="true" />
                    <span class="tabular-nums">{{ hit.item.year }}</span>
                  </template>
                  <template v-if="hit.item.secondary_title">
                    <i class="header-search__dot" aria-hidden="true" />
                    <span class="header-search__alt" dir="auto">{{ hit.item.secondary_title }}</span>
                  </template>
                </span>
              </span>
              <DubSubtitleBadge
                v-if="hit.item.is_dubbed || hit.item.has_subtitle"
                class="header-search__badges"
                :is-dubbed="hit.item.is_dubbed"
                :has-subtitle="hit.item.has_subtitle"
                icons-only
                compact
              />
              <CinematicIcon name="arrow-left" class="header-search__go size-4" aria-hidden="true" />
            </button>
          </div>

          <div v-if="actorHits.length" class="header-search__group" role="group" aria-label="بازیگران">
            <p class="header-search__section-label">بازیگران</p>
            <div class="header-search__chips">
              <button
                v-for="(actor, index) in actorHits"
                :id="`${listboxId}-option-${hits.length + index}`"
                :key="`actor-${actor.id}`"
                type="button"
                role="option"
                class="header-search__chip"
                :class="{ 'header-search__chip--active': activeIndex === hits.length + index }"
                :aria-selected="activeIndex === hits.length + index"
                @mousedown.prevent="openActor(actor)"
                @mouseenter="activeIndex = hits.length + index"
              >
                <CinematicImage
                  :src="actor.photo || ''"
                  :alt="`تصویر ${actor.name}`"
                  ratio="square"
                  class="header-search__avatar"
                  :fallback-label="actor.name"
                />
                <span class="truncate" dir="auto">{{ actor.name }}</span>
              </button>
            </div>
          </div>

          <button
            type="button"
            class="header-search__footer"
            @mousedown.prevent="submit()"
          >
            <span class="truncate">همه نتایج برای «{{ query.trim() }}»</span>
            <CinematicIcon name="arrow-left" class="size-3.5 shrink-0" />
          </button>
        </template>

        <div v-else-if="remoteError" class="header-search__status" role="alert">
          <p class="header-search__status-title">جستجو در دسترس نیست</p>
          <p class="header-search__status-note">اتصال اینترنت را بررسی کن و دوباره امتحان کن.</p>
          <button type="button" class="header-search__retry" @mousedown.prevent="retry">
            <CinematicIcon name="refresh" class="size-3.5" />
            تلاش دوباره
          </button>
        </div>

        <div v-else-if="shortQuery" class="header-search__status">
          <p class="header-search__status-title">کمی بیشتر بنویس</p>
          <p class="header-search__status-note">یک حرف دیگر، یا یک سال چهاررقمی مثل 2024.</p>
        </div>

        <div v-else-if="emptyState" class="header-search__status">
          <p class="header-search__status-title">چیزی پیدا نشد</p>
          <p class="header-search__status-note">املای دیگری امتحان کن، یا نام انگلیسی را بنویس.</p>
          <button type="button" class="header-search__retry" @mousedown.prevent="submit()">
            جستجوی پیشرفته
            <CinematicIcon name="arrow-left" class="size-3.5" />
          </button>
        </div>
      </div>
    </Transition>
  </div>
</template>

<style scoped>
/* =====================================================================
   Header search — one quiet pill. At rest it is a hint that cycles through
   what can be searched; on focus it lights a mint ring (the host header
   also widens it). Results are a single clean list: poster, title, one
   meta line. Everything reads theme tokens, so light mode needs no forks.
   ===================================================================== */
.header-search-shell {
  --hs-accent: var(--theme-accent-primary, #b0e4cc);
  --hs-h: 2.6rem;
  position: relative;
  width: 100%;
  min-width: 0;
}

.header-search {
  position: relative;
  z-index: 2;
  display: flex;
  width: 100%;
  min-width: 0;
  height: var(--hs-h);
  align-items: center;
  gap: .55rem;
  padding-inline: .95rem .45rem;
  overflow: hidden;
  border: 1px solid color-mix(in srgb, var(--theme-text-primary, #fff) 9%, transparent);
  border-radius: 999px;
  background: color-mix(in srgb, var(--theme-text-primary, #fff) 5%, transparent);
  color: var(--theme-text-secondary, #c4c4c4);
  cursor: text;
  transition:
    border-color 200ms ease,
    background-color 200ms ease,
    box-shadow 260ms cubic-bezier(.22, 1, .36, 1);
}

.header-search:hover {
  border-color: color-mix(in srgb, var(--theme-text-primary, #fff) 16%, transparent);
}

.header-search:focus-within,
.header-search--open {
  border-color: color-mix(in srgb, var(--hs-accent) 60%, transparent);
  background: color-mix(in srgb, var(--theme-bg-surface, #0d0d0d) 70%, transparent);
  color: var(--theme-text-primary, #fff);
  box-shadow: 0 0 0 4px color-mix(in srgb, var(--hs-accent) 14%, transparent);
}

.header-search__icon {
  display: grid;
  flex: none;
  place-items: center;
  color: var(--theme-text-muted, #979797);
  transition: color 200ms ease, transform 260ms cubic-bezier(.34, 1.56, .64, 1);
}

.header-search:focus-within .header-search__icon,
.header-search--active .header-search__icon {
  color: var(--hs-accent);
  transform: scale(1.08);
}

.header-search__field {
  position: relative;
  display: flex;
  min-width: 0;
  height: 100%;
  flex: 1 1 auto;
  align-items: center;
}

.header-search__input {
  width: 100%;
  min-width: 0;
  height: 100%;
  border: 0;
  background: transparent;
  color: var(--theme-text-primary, #fff);
  font-size: .875rem;
  font-weight: 500;
  outline: none;
}

.header-search__input::-webkit-search-decoration,
.header-search__input::-webkit-search-cancel-button,
.header-search__input::-webkit-search-results-button,
.header-search__input::-webkit-search-results-decoration {
  display: none;
}

/* Cycling hint: stacked in one grid cell so the outgoing and incoming lines
   cross-slide in place without shifting anything around them. */
.header-search__hint {
  position: absolute;
  inset: 0;
  display: grid;
  align-items: center;
  overflow: hidden;
  pointer-events: none;
  color: var(--theme-text-muted, #979797);
  font-size: .85rem;
  white-space: nowrap;
  transition: opacity 160ms ease;
}

.header-search__hint-text {
  grid-area: 1 / 1;
  overflow: hidden;
  text-overflow: ellipsis;
}

.header-search:focus-within .header-search__hint { opacity: .6; }

.search-hint-enter-active,
.search-hint-leave-active {
  transition: opacity 320ms ease, transform 420ms cubic-bezier(.22, 1, .36, 1);
}

.search-hint-enter-from {
  opacity: 0;
  transform: translateY(70%);
}

.search-hint-leave-to {
  opacity: 0;
  transform: translateY(-70%);
}

.header-search__clear {
  display: grid;
  flex: none;
  width: 1.85rem;
  height: 1.85rem;
  place-items: center;
  border-radius: 999px;
  background: color-mix(in srgb, var(--theme-text-primary, #fff) 8%, transparent);
  color: var(--theme-text-secondary, #c4c4c4);
  transition: background-color 160ms ease, color 160ms ease, transform 160ms ease;
  -webkit-tap-highlight-color: transparent;
}

.header-search__clear:active { transform: scale(.9); }

.header-search__kbd {
  display: none;
  flex: none;
  min-width: 1.6rem;
  height: 1.6rem;
  place-items: center;
  border-radius: 999px;
  background: color-mix(in srgb, var(--theme-text-primary, #fff) 7%, transparent);
  color: var(--theme-text-muted, #979797);
  font-family: var(--font-latin-ui);
  font-size: 0.75rem;
  font-weight: 600;
  line-height: 1;
  transition: opacity 160ms ease;
}

.header-search:focus-within .header-search__kbd { opacity: 0; }

/* A thin mint sweep along the pill's floor while an answer is in flight. */
.header-search__busy {
  position: absolute;
  inset-inline: 1.2rem;
  bottom: 0;
  height: 2px;
  border-radius: 999px;
  background: linear-gradient(90deg, transparent, var(--hs-accent), transparent);
  background-size: 40% 100%;
  background-repeat: no-repeat;
  opacity: 0;
  pointer-events: none;
  transition: opacity 160ms ease;
}

.header-search--busy .header-search__busy {
  opacity: .9;
  animation: header-search-sweep 900ms ease-in-out infinite;
}

@keyframes header-search-sweep {
  from { background-position: 130% 0; }
  to { background-position: -30% 0; }
}

/* ---- Results ---- */
.header-search__panel {
  position: absolute;
  inset-inline: 0;
  top: calc(100% + .6rem);
  z-index: 80;
  display: flex;
  flex-direction: column;
  max-height: min(70dvh, 30rem);
  padding: .4rem;
  overflow: auto;
  overscroll-behavior: contain;
  border: 1px solid color-mix(in srgb, var(--theme-text-primary, #fff) 9%, transparent);
  border-radius: 1.35rem;
  background: color-mix(in srgb, var(--theme-bg-elevated, #141414) 96%, transparent);
  box-shadow:
    0 1.5rem 3rem rgb(0 0 0 / 38%),
    inset 0 1px 0 rgb(255 255 255 / 5%);
  -webkit-backdrop-filter: blur(18px) saturate(140%);
  backdrop-filter: blur(18px) saturate(140%);
  scrollbar-width: thin;
}

.header-search__group + .header-search__group {
  margin-top: .25rem;
  padding-top: .25rem;
  border-top: 1px solid color-mix(in srgb, var(--theme-text-primary, #fff) 6%, transparent);
}

.header-search__section-label {
  padding: .55rem .7rem .35rem;
  color: var(--theme-text-muted, #979797);
  font-size: 0.75rem;
  font-weight: 700;
}

.header-search__option {
  display: flex;
  width: 100%;
  align-items: center;
  gap: .7rem;
  padding: .4rem .5rem;
  border-radius: .95rem;
  text-align: right;
  transition: background-color 140ms ease;
}

.header-search__option--active {
  background: color-mix(in srgb, var(--hs-accent) 11%, transparent);
}

.header-search__poster {
  width: 2.3rem;
  flex: none;
  overflow: hidden;
  border-radius: .6rem;
  box-shadow: inset 0 0 0 1px rgb(255 255 255 / 6%);
}

.header-search__text {
  display: flex;
  min-width: 0;
  flex: 1 1 auto;
  flex-direction: column;
  gap: .2rem;
}

.header-search__title {
  overflow: hidden;
  color: var(--theme-text-primary, #fff);
  font-size: .875rem;
  font-weight: 800;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.header-search__meta {
  display: flex;
  min-width: 0;
  align-items: center;
  gap: .4rem;
  color: var(--theme-text-muted, #979797);
  font-size: .72rem;
  white-space: nowrap;
}

.header-search__alt {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
}

.header-search__dot {
  width: 3px;
  height: 3px;
  flex: none;
  border-radius: 50%;
  background: currentcolor;
  opacity: .6;
}

.header-search__badges { flex: none; }

.header-search__go {
  flex: none;
  color: var(--hs-accent);
  opacity: 0;
  transform: translateX(.35rem);
  transition: opacity 160ms ease, transform 200ms cubic-bezier(.22, 1, .36, 1);
}

.header-search__option--active .header-search__go {
  opacity: 1;
  transform: none;
}

/* Actors: a wrap of compact chips instead of full rows. */
.header-search__chips {
  display: flex;
  flex-wrap: wrap;
  gap: .4rem;
  padding: .1rem .5rem .5rem;
}

.header-search__chip {
  display: inline-flex;
  max-width: 12rem;
  align-items: center;
  gap: .45rem;
  padding: .2rem .25rem .2rem .75rem;
  border-radius: 999px;
  background: color-mix(in srgb, var(--theme-text-primary, #fff) 5%, transparent);
  color: var(--theme-text-secondary, #c4c4c4);
  font-size: .78rem;
  font-weight: 600;
  transition: background-color 140ms ease, color 140ms ease;
}

.header-search__chip--active {
  background: color-mix(in srgb, var(--hs-accent) 16%, transparent);
  color: var(--theme-text-primary, #fff);
}

.header-search__avatar {
  width: 1.7rem;
  flex: none;
  overflow: hidden;
  border-radius: 999px;
}

.header-search__footer {
  display: flex;
  min-height: 2.6rem;
  align-items: center;
  justify-content: center;
  gap: .4rem;
  margin-top: .3rem;
  padding-inline: 1rem;
  border-radius: 999px;
  background: color-mix(in srgb, var(--hs-accent) 9%, transparent);
  color: var(--hs-accent);
  font-size: .78rem;
  font-weight: 800;
  transition: background-color 160ms ease;
}

/* ---- Loading / empty / error ---- */
.header-search__skeleton {
  display: grid;
  gap: .15rem;
  padding: .1rem 0;
}

.header-search__skeleton-row {
  display: flex;
  align-items: center;
  gap: .7rem;
  padding: .4rem .5rem;
}

.header-search__skeleton-poster,
.header-search__skeleton-lines i {
  display: block;
  border-radius: .5rem;
  background: color-mix(in srgb, var(--theme-text-primary, #fff) 7%, transparent);
  animation: header-search-pulse 1.2s ease-in-out infinite;
}

.header-search__skeleton-poster {
  width: 2.3rem;
  height: 3.45rem;
  flex: none;
  border-radius: .6rem;
}

.header-search__skeleton-lines {
  display: grid;
  flex: 1;
  gap: .45rem;
}

.header-search__skeleton-lines i:first-child { width: 55%; height: .7rem; }
.header-search__skeleton-lines i:last-child { width: 30%; height: .55rem; }
.header-search__skeleton-row:nth-child(3) i { animation-delay: 120ms; }
.header-search__skeleton-row:nth-child(4) i { animation-delay: 240ms; }

@keyframes header-search-pulse {
  0%, 100% { opacity: .55; }
  50% { opacity: 1; }
}

.header-search__status {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: .3rem;
  padding: 1.1rem 1rem 1rem;
  text-align: center;
}

.header-search__status-title {
  color: var(--theme-text-primary, #fff);
  font-size: .85rem;
  font-weight: 800;
}

.header-search__status-note {
  color: var(--theme-text-muted, #979797);
  font-size: .75rem;
  line-height: 1.6;
}

.header-search__retry {
  display: inline-flex;
  min-height: 2.3rem;
  align-items: center;
  gap: .4rem;
  margin-top: .45rem;
  padding-inline: 1rem;
  border-radius: 999px;
  background: color-mix(in srgb, var(--hs-accent) 12%, transparent);
  color: var(--hs-accent);
  font-size: .75rem;
  font-weight: 800;
}

@media (hover: hover) and (pointer: fine) {
  .header-search__clear:hover {
    background: color-mix(in srgb, var(--hs-accent) 18%, transparent);
    color: var(--hs-accent);
  }

  .header-search__chip:hover {
    background: color-mix(in srgb, var(--hs-accent) 16%, transparent);
    color: var(--theme-text-primary, #fff);
  }

  .header-search__footer:hover,
  .header-search__retry:hover {
    background: color-mix(in srgb, var(--hs-accent) 17%, transparent);
  }
}

.search-suggest-enter-active,
.search-suggest-leave-active {
  transition: opacity 160ms ease, transform 220ms cubic-bezier(.22, 1, .36, 1);
  transform-origin: top center;
}

.search-suggest-enter-from,
.search-suggest-leave-to {
  opacity: 0;
  transform: translateY(-.4rem) scale(.98);
}

@media (max-width: 1023px) {
  .header-search-shell { --hs-h: 2.85rem; }

  .header-search__input,
  .header-search__hint {
    font-size: 1rem; /* 16px keeps iOS from zooming on focus */
  }

  .header-search__panel {
    max-height: min(62dvh, 26rem);
    -webkit-overflow-scrolling: touch;
  }
}

@media (min-width: 1280px) {
  .header-search__kbd { display: inline-grid; }
}

:global(html[data-theme="light"] .header-search) {
  border-color: var(--theme-border, #d5ddd8);
  background: var(--theme-bg-surface, #fff);
}

:global(html[data-theme="light"] .header-search__panel) {
  border-color: var(--theme-border, #d5ddd8);
  background: var(--theme-bg-surface, #fff);
  box-shadow: var(--theme-shadow-float, 0 18px 40px rgb(23 50 38 / 14%));
}

@media (prefers-reduced-motion: reduce) {
  .header-search,
  .header-search__icon,
  .header-search__go,
  .search-hint-enter-active,
  .search-hint-leave-active,
  .search-suggest-enter-active,
  .search-suggest-leave-active {
    transition: none;
  }

  .header-search--busy .header-search__busy,
  .header-search__skeleton-poster,
  .header-search__skeleton-lines i {
    animation: none;
  }
}
</style>
