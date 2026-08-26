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
const debouncedQuery = refDebounced(query, 220)
const isAlive = computed(() => focused.value || Boolean(query.value.trim()) || props.active || open.value)
const placeholder = computed(() => props.compactPlaceholder ? 'نام یا سال…' : 'جستجوی فیلم، سریال، بازیگر یا سال…')
const normalizedLiveQuery = computed(() => normalizeSearchText(debouncedQuery.value))
const normalizedQuery = computed(() => normalizeSearchText(query.value))
const parsedQuery = computed(() => parseSearchQuery(query.value))
const canSearch = computed(() => Boolean(
  parsedQuery.value.year
  || normalizeSearchText(parsedQuery.value.text).replace(/\s/g, '').length >= 2,
))

const hits = computed(() => {
  const term = normalizedLiveQuery.value
  if (!term) return [] as RankedSearchHit[]
  if (resolvedRemoteQuery.value === term) return remoteHits.value
  return [] as RankedSearchHit[]
})

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
const directSectionLabel = computed(() => parsedQuery.value.year
  ? `آثار سال ${parsedQuery.value.year}`
  : 'نتایج مستقیم از کل آرشیو')

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
  if (!parsed.year && normalizeSearchText(parsed.text).replace(/\s/g, '').length < 2) {
    actorHits.value = []
    remoteHits.value = []
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
    const response = await api<ApiSearchResponse>('/search/', {
      query: {
        ...(parsed.text && { q: parsed.text }),
        ...(parsed.year && { year: parsed.year }),
        type: 'all',
        limit: 12,
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
  actorHits.value = []
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
  if (window.matchMedia('(max-width: 767px)').matches) return
  const target = event.target as HTMLElement | null
  if (target?.matches('input, textarea, select, [contenteditable="true"]')) return
  event.preventDefault()
  input.value?.focus()
}

function kindLabel(kind: RankedSearchHit['kind']) {
  if (kind === 'exact') return 'تطبیق دقیق'
  if (kind === 'prefix' || kind === 'contains') return 'نتیجه مرتبط'
  return 'مرتبط یا شبیه'
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
      :class="{ 'header-search--alive': isAlive, 'header-search--active': active, 'header-search--open': showPanel }"
      role="search"
      @submit.prevent="submit()"
    >
      <label class="sr-only" :for="inputId">جستجوی فیلم، سریال یا بازیگر</label>
      <span class="header-search__icon" aria-hidden="true">
        <CinematicIcon name="search" class="size-[1.05rem]" />
      </span>
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
        :placeholder="placeholder"
        role="combobox"
        :aria-expanded="showPanel"
        aria-autocomplete="list"
        :aria-controls="listboxId"
        :aria-activedescendant="activeIndex >= 0 ? `${listboxId}-option-${activeIndex}` : undefined"
        @focus="onFocus"
        @input="onInput"
        @keydown="onKeydown"
      >
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
    </form>

    <Transition name="search-suggest">
      <div
        v-if="showPanel"
        :id="listboxId"
        class="header-search__panel"
        role="listbox"
        :aria-label="`پیشنهادهای جستجو برای ${query}`"
      >
        <div v-if="searching && !hits.length && !actorHits.length" class="header-search__status" role="status">
          <CinematicIcon name="refresh" class="mx-auto mb-2 size-5 animate-spin text-brand" />
          در حال جستجو در آرشیو…
        </div>

        <template v-else-if="hits.length || actorHits.length">
          <p v-if="hasExact" class="header-search__section-label">{{ directSectionLabel }}</p>
          <button
            v-for="(hit, index) in exactHits"
            :id="`${listboxId}-option-${index}`"
            :key="`exact-${hit.item.type}-${hit.item.id}`"
            type="button"
            role="option"
            class="header-search__option"
            :class="{ 'header-search__option--active': activeIndex === index }"
            :aria-selected="activeIndex === index"
            @mousedown.prevent="openItem(hit)"
          >
            <CinematicImage
              :src="hit.item.poster_url"
              :alt="`پوستر ${hit.item.title}`"
              ratio="poster"
              class="header-search__poster"
              :fallback-label="hit.item.title"
            />
            <span class="min-w-0 flex-1 text-right">
              <span class="block truncate text-sm font-black text-ink" dir="auto">{{ hit.item.title }}</span>
              <span v-if="hit.item.secondary_title" class="mt-0.5 block truncate text-[11px] text-muted" dir="rtl">{{ hit.item.secondary_title }}</span>
              <span class="mt-1 flex flex-wrap items-center gap-1.5 text-[11px] text-secondary">
                <span class="rounded-md bg-elevated px-1.5 py-0.5 font-bold">{{ hit.item.type === 'movie' ? 'فیلم' : 'سریال' }}</span>
                <span v-if="hit.item.year" class="tabular-nums">{{ hit.item.year }}</span>
                <DubSubtitleBadge
                  v-if="hit.item.is_dubbed || hit.item.has_subtitle"
                  :is-dubbed="hit.item.is_dubbed"
                  :has-subtitle="hit.item.has_subtitle"
                  icons-only
                  compact
                />
                <span class="text-muted">{{ kindLabel(hit.kind) }}</span>
              </span>
            </span>
            <CinematicIcon name="arrow-left" class="size-4 shrink-0 text-muted" />
          </button>

          <template v-if="similarHits.length">
            <p class="header-search__section-label">
              {{ hasExact ? 'موارد مرتبط و نام‌های شبیه' : 'نتیجهٔ مستقیم پیدا نشد؛ نزدیک‌ترین پیشنهادها' }}
            </p>
            <button
              v-for="(hit, index) in similarHits"
              :id="`${listboxId}-option-${exactHits.length + index}`"
              :key="`similar-${hit.item.type}-${hit.item.id}`"
              type="button"
              role="option"
              class="header-search__option"
              :class="{ 'header-search__option--active': activeIndex === exactHits.length + index }"
              :aria-selected="activeIndex === exactHits.length + index"
              @mousedown.prevent="openItem(hit)"
            >
              <CinematicImage
                :src="hit.item.poster_url"
                :alt="`پوستر ${hit.item.title}`"
                ratio="poster"
                class="header-search__poster"
                :fallback-label="hit.item.title"
              />
              <span class="min-w-0 flex-1 text-right">
                <span class="block truncate text-sm font-black text-ink" dir="auto">{{ hit.item.title }}</span>
                <span v-if="hit.item.secondary_title" class="mt-0.5 block truncate text-[11px] text-muted" dir="rtl">{{ hit.item.secondary_title }}</span>
                <span class="mt-1 flex flex-wrap items-center gap-1.5 text-[11px] text-secondary">
                  <span class="rounded-md bg-elevated px-1.5 py-0.5 font-bold">{{ hit.item.type === 'movie' ? 'فیلم' : 'سریال' }}</span>
                  <span v-if="hit.item.year" class="tabular-nums">{{ hit.item.year }}</span>
                  <DubSubtitleBadge
                    v-if="hit.item.is_dubbed || hit.item.has_subtitle"
                    :is-dubbed="hit.item.is_dubbed"
                    :has-subtitle="hit.item.has_subtitle"
                    icons-only
                    compact
                  />
                  <span class="text-primary-300">مرتبط یا شبیه</span>
                </span>
              </span>
              <CinematicIcon name="arrow-left" class="size-4 shrink-0 text-muted" />
            </button>
          </template>

          <template v-if="actorHits.length">
            <p class="header-search__section-label">بازیگران</p>
            <button
              v-for="(actor, index) in actorHits"
              :id="`${listboxId}-option-${hits.length + index}`"
              :key="`actor-${actor.id}`"
              type="button"
              role="option"
              class="header-search__option"
              :class="{ 'header-search__option--active': activeIndex === hits.length + index }"
              :aria-selected="activeIndex === hits.length + index"
              @mousedown.prevent="openActor(actor)"
            >
              <CinematicImage
                :src="actor.photo || ''"
                :alt="`تصویر ${actor.name}`"
                ratio="poster"
                class="header-search__poster header-search__poster--actor"
                :fallback-label="actor.name"
              />
              <span class="min-w-0 flex-1 text-right">
                <span class="block truncate text-sm font-black text-ink" dir="auto">{{ actor.name }}</span>
                <span v-if="actor.secondary_name" class="mt-0.5 block truncate text-[11px] text-muted" dir="rtl">{{ actor.secondary_name }}</span>
                <span class="mt-1 inline-flex rounded-md bg-elevated px-1.5 py-0.5 text-[11px] font-bold text-secondary">بازیگر</span>
              </span>
              <CinematicIcon name="arrow-left" class="size-4 shrink-0 text-muted" />
            </button>
          </template>

          <button
            type="button"
            class="header-search__footer"
            @mousedown.prevent="submit()"
          >
            مشاهده همه نتایج برای «{{ query.trim() }}»
            <CinematicIcon name="arrow-left" class="size-3.5" />
          </button>
        </template>

        <div v-else-if="remoteError" class="header-search__status" role="alert">
          <CinematicIcon name="signal-off" class="mx-auto mb-2 size-5 text-muted" />
          <p class="font-bold text-ink">ارتباط با جستجو برقرار نشد</p>
          <p class="mt-1 text-[11px] leading-5 text-muted">اتصال اینترنت را بررسی کن و دوباره تلاش کن.</p>
          <button type="button" class="header-search__retry" @mousedown.prevent="retry">
            <CinematicIcon name="refresh" class="size-3.5" />
            تلاش دوباره
          </button>
        </div>

        <div v-else-if="shortQuery" class="header-search__status">
          <p class="font-bold text-ink">کمی بیشتر بنویس</p>
          <p class="mt-1 text-[11px] leading-5 text-muted">حداقل دو حرف یا یک سال چهاررقمی مثل 2024 وارد کن.</p>
        </div>

        <div v-else-if="emptyState" class="header-search__status">
          <p class="font-bold text-ink">نتیجه‌ای پیدا نشد</p>
          <p class="mt-1 text-[11px] leading-5 text-muted">نام یا سال دیگری بنویس، یا جست‌وجوی پیشرفته را باز کن.</p>
          <button type="button" class="header-search__footer mt-2" @mousedown.prevent="submit()">
            جستجوی پیشرفته
            <CinematicIcon name="arrow-left" class="size-3.5" />
          </button>
        </div>
      </div>
    </Transition>
  </div>
</template>

<style scoped>
.header-search-shell {
  position: relative;
  width: 100%;
  min-width: 0;
}

.header-search {
  --search-fg: var(--theme-text-secondary);
  position: relative;
  z-index: 2;
  display: flex;
  min-width: 0;
  width: 100%;
  max-width: 100%;
  height: 2.75rem;
  align-items: center;
  gap: .5rem;
  padding-inline: .85rem .65rem;
  overflow: hidden;
  border: 1px solid color-mix(in srgb, var(--theme-border) 88%, transparent);
  border-radius: .7rem;
  background:
    linear-gradient(180deg, rgb(255 255 255 / 5%), transparent 55%),
    color-mix(in srgb, var(--theme-bg-elevated) 38%, transparent);
  color: var(--search-fg);
  transition: border-color 200ms ease, background-color 200ms ease, color 180ms ease;
  -webkit-backdrop-filter: blur(14px) saturate(140%);
  backdrop-filter: blur(14px) saturate(140%);
}

.header-search--alive,
.header-search--active,
.header-search:focus-within,
.header-search--open {
  --search-fg: var(--theme-text-primary);
  border-color: color-mix(in srgb, var(--theme-accent-primary) 42%, var(--theme-border));
  background:
    linear-gradient(180deg, rgb(255 255 255 / 7%), transparent 55%),
    color-mix(in srgb, var(--theme-bg-surface) 55%, transparent);
}

.header-search__icon {
  display: grid;
  flex: none;
  place-items: center;
  color: color-mix(in srgb, var(--theme-accent-primary) 78%, var(--theme-text-secondary));
}

.header-search:focus-within .header-search__icon {
  color: var(--theme-accent-primary);
}

.header-search__input {
  min-width: 0;
  flex: 1 1 auto;
  height: 100%;
  border: 0;
  background: transparent;
  color: var(--theme-text-secondary);
  font-size: .875rem;
  font-weight: 500;
  letter-spacing: -.01em;
  outline: none;
}

.header-search:focus-within .header-search__input {
  color: var(--theme-text-primary);
}

.header-search__input::placeholder {
  color: var(--theme-text-muted);
  font-weight: 400;
}

.header-search__input::-webkit-search-decoration,
.header-search__input::-webkit-search-cancel-button,
.header-search__input::-webkit-search-results-button,
.header-search__input::-webkit-search-results-decoration {
  display: none;
}

.header-search__clear {
  display: grid;
  flex: none;
  width: 2.25rem;
  height: 2.25rem;
  place-items: center;
  border-radius: 9999px;
  background: color-mix(in srgb, var(--theme-bg-elevated) 70%, transparent);
  color: var(--theme-text-secondary);
  -webkit-tap-highlight-color: transparent;
}

@media (max-width: 767px) {
  .header-search {
    height: 2.75rem;
    padding-inline: .7rem .45rem;
  }

  .header-search__input {
    font-size: 1rem; /* avoid iOS zoom on focus */
  }

  .header-search__panel {
    max-height: min(58dvh, 24rem);
    overscroll-behavior: contain;
    -webkit-overflow-scrolling: touch;
  }
}

.header-search__kbd {
  display: none;
  flex: none;
  min-width: 1.35rem;
  padding: .15rem .35rem;
  border: 1px solid color-mix(in srgb, var(--theme-border) 90%, transparent);
  border-radius: .45rem;
  background: color-mix(in srgb, var(--theme-bg-main) 55%, transparent);
  color: var(--theme-text-muted);
  font-family: var(--font-latin-ui);
  font-size: .625rem;
  font-weight: 500;
  line-height: 1.2;
  opacity: .85;
}

.header-search__panel {
  position: absolute;
  inset-inline: 0;
  top: calc(100% + .5rem);
  z-index: 80;
  max-height: min(70dvh, 28rem);
  overflow: auto;
  border: 1px solid color-mix(in srgb, var(--theme-accent-primary) 28%, var(--theme-border));
  border-radius: .8rem;
  background: color-mix(in srgb, var(--theme-bg-surface) 98%, transparent);
  box-shadow: 0 18px 40px rgb(0 0 0 / 28%);
  -webkit-backdrop-filter: blur(18px) saturate(140%);
  backdrop-filter: blur(18px) saturate(140%);
}

.header-search__section-label {
  padding: .75rem 1rem .3rem;
  color: color-mix(in srgb, var(--theme-text-primary) 78%, transparent);
  font-size: .6875rem;
  font-weight: 800;
}

.header-search__option {
  display: flex;
  width: 100%;
  align-items: center;
  gap: .75rem;
  padding: .5rem 1rem;
  text-align: right;
  transition: background-color 140ms ease;
}

.header-search__option--active {
  background: color-mix(in srgb, var(--theme-accent-primary-soft) 88%, transparent);
}

.header-search__poster {
  width: 2.5rem;
  flex: none;
  overflow: hidden;
  border-radius: .55rem;
  box-shadow: inset 0 0 0 1px rgb(var(--palette-ink-rgb) / 8%);
}

.header-search__poster--actor {
  border-radius: 999px;
}

.header-search__footer {
  display: flex;
  width: 100%;
  min-height: 2.75rem;
  align-items: center;
  justify-content: center;
  gap: .4rem;
  border-top: 1px solid var(--theme-border);
  padding: .75rem .9rem;
  color: var(--theme-accent-primary);
  font-size: .75rem;
  font-weight: 800;
}

.header-search__retry {
  display: inline-flex;
  min-height: 2.5rem;
  align-items: center;
  justify-content: center;
  gap: .4rem;
  margin-top: .65rem;
  padding-inline: .9rem;
  border-radius: .8rem;
  background: color-mix(in srgb, var(--theme-accent-primary) 14%, transparent);
  color: var(--theme-accent-primary);
  font-size: .75rem;
  font-weight: 800;
}

@media (hover: hover) and (pointer: fine) {
  .header-search__clear:hover {
    background: color-mix(in srgb, var(--theme-accent-primary) 18%, transparent);
    color: var(--theme-accent-primary);
  }

  .header-search__option:hover {
    background: color-mix(in srgb, var(--theme-accent-primary-soft) 88%, transparent);
  }

  .header-search__footer:hover {
    background: color-mix(in srgb, var(--theme-accent-primary-soft) 70%, transparent);
  }

  .header-search__retry:hover {
    background: color-mix(in srgb, var(--theme-accent-primary) 22%, transparent);
  }
}

.header-search__status {
  padding: 1rem .95rem 1.05rem;
  color: var(--theme-text-secondary);
  font-size: .8125rem;
  text-align: center;
}

.search-suggest-enter-active,
.search-suggest-leave-active {
  transition: opacity 140ms ease, transform 160ms ease;
}

.search-suggest-enter-from,
.search-suggest-leave-to {
  opacity: 0;
  transform: translateY(-.35rem);
}

@media (min-width: 1280px) {
  .header-search {
    height: 2.5rem;
    padding-inline: 1rem .8rem;
  }

  .header-search__kbd {
    display: inline-grid;
    place-items: center;
  }
}

:global(html[data-theme="light"] .header-search) {
  border-color: var(--theme-border-strong);
  background:
    linear-gradient(180deg, rgb(255 255 255 / 96%), rgb(248 250 248 / 92%)),
    var(--theme-bg-surface);
  box-shadow: 0 1px 0 rgb(23 50 38 / 3%);
}

:global(html[data-theme="light"] .header-search__panel) {
  border-color: var(--theme-border);
  background: color-mix(in srgb, var(--theme-bg-surface) 98%, transparent);
  box-shadow: var(--theme-shadow-float);
}

@media (prefers-reduced-motion: reduce) {
  .header-search,
  .search-suggest-enter-active,
  .search-suggest-leave-active {
    transition: none;
  }
}
</style>
