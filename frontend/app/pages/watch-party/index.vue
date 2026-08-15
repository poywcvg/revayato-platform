<script setup lang="ts">
import type { AppErrorDetails, Movie, WatchRoom } from '~/types'
import {
  adaptApiCatalogItem,
  type ApiCatalogItem,
} from '~/data/catalogAdapter'
import { normalizeSearchText, rankCatalogSearch } from '~/utils/searchRank'

definePageMeta({ middleware: 'auth' })

type ContentFilter = 'all' | 'movie' | 'series'
interface ApiCatalogSearchResponse {
  query: string
  movies?: ApiCatalogItem[]
  series?: ApiCatalogItem[]
}

const route = useRoute()
const router = useRouter()
const config = useRuntimeConfig()
const {
  catalog,
  source,
  pending,
  error: catalogError,
  loadFromApi,
  loadItemFromApi,
} = useCatalog()
const { api } = useApi()
const notifications = useNotifications()
const { continueWatching, entries } = useWatchProgress()

const creatingId = ref<number | null>(null)
const resolvingId = ref<number | null>(null)
const actionError = ref<AppErrorDetails | null>(null)
const joinDraft = ref('')
const joinError = ref('')
const joining = ref(false)
const pickerQuery = ref(String(route.query.q || ''))
const contentFilter = ref<ContentFilter>(
  route.query.type === 'movie' || route.query.type === 'series'
    ? route.query.type
    : 'all',
)
const remoteResults = shallowRef<Movie[]>([])
const searchPending = ref(false)
const searchError = ref('')
const searchInputFocused = ref(false)
const selectedSeries = ref<Movie | null>(null)
const prefilling = ref(false)
const prefilledItem = shallowRef<Movie | null>(null)
const seriesDialog = useTemplateRef<HTMLElement>('seriesDialog')
const joinInput = useTemplateRef<HTMLInputElement>('joinInput')
const pickerInput = useTemplateRef<HTMLInputElement>('pickerInput')
let pickerPreviousFocus: HTMLElement | null = null
let searchRequestId = 0
let resolveRequestId = 0
let applyingRouteQuery = false
let routeSyncVersion = 0
const pickerFocusable = 'button:not([disabled]), a[href], input:not([disabled]), [tabindex]:not([tabindex="-1"])'

const catalogReady = computed(() => source.value === 'api')
const debouncedQuery = refDebounced(pickerQuery, 280)

const partySteps = [
  { step: '۱', title: 'عنوان را انتخاب کن', hint: 'فیلم یا قسمت سریال' },
  { step: '۲', title: 'لینک دعوت بفرست', hint: 'فقط با لینک وارد می‌شوند' },
  { step: '۳', title: 'هم‌زمان تماشا کنید', hint: 'میزبان پخش را کنترل می‌کند' },
] as const

const filteredPool = computed(() => {
  const pool = catalog.value.filter(item => contentFilter.value === 'all' || item.type === contentFilter.value)
  const term = normalizeSearchText(debouncedQuery.value)
  if (!term) {
    return [...pool].sort((a, b) => Number(b.is_trending) - Number(a.is_trending) || b.popularity - a.popularity).slice(0, 24)
  }

  const localMatches = rankCatalogSearch(pool, term, {
    limit: remoteResults.value.length ? 8 : 24,
    includeSimilar: false,
  }).map(hit => hit.item)

  const merged = new Map<string, Movie>()
  for (const item of [...remoteResults.value, ...localMatches]) {
    if (contentFilter.value !== 'all' && item.type !== contentFilter.value) continue
    const key = `${item.type}-${item.id}`
    const existing = merged.get(key)
    if (!existing || (item.episodes?.length || 0) > (existing.episodes?.length || 0)) {
      merged.set(key, item)
    }
  }
  return [...merged.values()].slice(0, 36)
})

const searchStatus = computed(() => {
  if (searchPending.value && !filteredPool.value.length) return 'در حال جستجو در کل آرشیو…'
  if (searchPending.value) return 'در حال به‌روزرسانی نتایج…'
  if (!normalizeSearchText(debouncedQuery.value)) return 'عنوان را جستجو کن یا از پیشنهادها انتخاب کن.'
  return `${filteredPool.value.length.toLocaleString('fa-IR')} نتیجه برای «${debouncedQuery.value.trim()}»`
})

function continueEpisodeId(item: Movie) {
  return entries.value.find(
    entry => entry.content_type === item.type && entry.object_id === item.id,
  )?.episode_id
}

function rememberResolvedSeries(detail: Movie) {
  remoteResults.value = remoteResults.value.map((item) => {
    if (item.type !== 'series' || item.id !== detail.id) return item
    return {
      ...item,
      ...detail,
      episodes: detail.episodes?.length ? detail.episodes : item.episodes,
    }
  })
}

function normalizeInviteCode(raw: string) {
  const value = String(raw || '').trim()
  if (!value) return ''
  try {
    const asUrl = new URL(value, 'https://revayato.invalid')
    const match = asUrl.pathname.match(/\/watch-party\/([^/?#]+)/i)
    if (match?.[1]) return decodeURIComponent(match[1]).trim()
  } catch {
    // plain code
  }
  return value.replace(/^\/+/, '').split(/[/?#]/)[0]?.trim() || ''
}

async function focusPartyAction(target: 'join' | 'create') {
  if (!import.meta.client) return
  const section = document.getElementById(target === 'join' ? 'party-join' : 'party-create')
  section?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  await nextTick()
  window.setTimeout(() => {
    if (target === 'join') joinInput.value?.focus()
    else pickerInput.value?.focus()
  }, 420)
}

async function joinWithCode() {
  const code = normalizeInviteCode(joinDraft.value)
  joinError.value = ''
  if (code.length < 4) {
    joinError.value = 'کد یا لینک دعوت را کامل وارد کن.'
    return
  }
  joining.value = true
  try {
    await navigateTo(`/watch-party/${encodeURIComponent(code)}`)
  } finally {
    joining.value = false
  }
}

async function syncPickerRoute() {
  if (applyingRouteQuery) return
  const version = ++routeSyncVersion
  await nextTick()
  if (version !== routeSyncVersion || applyingRouteQuery) return

  const query = {
    ...(route.query.id && { id: String(route.query.id) }),
    ...(route.query.slug && { slug: String(route.query.slug) }),
    ...(route.query.title && { title: String(route.query.title) }),
    ...(pickerQuery.value.trim() && { q: pickerQuery.value.trim() }),
    ...(contentFilter.value !== 'all' && { type: contentFilter.value }),
  }
  const current = JSON.stringify({
    ...(route.query.id && { id: String(route.query.id) }),
    ...(route.query.slug && { slug: String(route.query.slug) }),
    ...(route.query.title && { title: String(route.query.title) }),
    ...(route.query.q && { q: String(route.query.q) }),
    ...(route.query.type && { type: String(route.query.type) }),
  })
  if (current !== JSON.stringify(query)) void router.replace({ query })
}

function applyPickerRoute() {
  if (searchInputFocused.value || applyingRouteQuery) return

  const nextQuery = String(route.query.q || '')
  const nextFilter: ContentFilter =
    route.query.type === 'movie' || route.query.type === 'series'
      ? route.query.type
      : 'all'

  if (nextQuery === pickerQuery.value && nextFilter === contentFilter.value) return

  applyingRouteQuery = true
  pickerQuery.value = nextQuery
  contentFilter.value = nextFilter
  nextTick(() => {
    applyingRouteQuery = false
  })
}

async function searchFullCatalog() {
  const term = debouncedQuery.value.trim()
  const requestId = ++searchRequestId
  searchError.value = ''
  if (normalizeSearchText(term).length < 2) {
    remoteResults.value = []
    searchPending.value = false
    return
  }

  searchPending.value = true
  try {
    const response = await api<ApiCatalogSearchResponse>('/search/', {
      query: {
        q: term,
        type: contentFilter.value,
        limit: 24,
      },
    })
    if (requestId !== searchRequestId) return
    const mediaBase = String(config.public.mediaCdnBaseUrl)
    remoteResults.value = [
      ...(response.movies || []).map(item =>
        adaptApiCatalogItem(item, 'movie', mediaBase),
      ),
      ...(response.series || []).map(item =>
        adaptApiCatalogItem(item, 'series', mediaBase),
      ),
    ]
  } catch {
    if (requestId !== searchRequestId) return
    searchError.value = 'جستجوی کامل در دسترس نیست؛ نتایج فعلی از فهرست بارگذاری‌شده نمایش داده می‌شوند.'
  } finally {
    if (requestId === searchRequestId) searchPending.value = false
  }
}

function selectionFor(item: Movie, episodeId?: number) {
  if (item.type === 'movie') return { content_type: 'movie' as const, content_id: item.id }
  const episode = episodeId
    ? item.episodes?.find(candidate => candidate.id === episodeId)
    : item.episodes?.find(candidate => candidate.hls_url || candidate.download_url) || item.episodes?.[0]
  return episode
    ? { content_type: 'episode' as const, content_id: episode.id }
    : null
}

function detailPath(item: Movie) {
  return `/${item.type === 'movie' ? 'movies' : 'series'}/${item.slug}`
}

function openSeriesPicker(item: Movie) {
  selectedSeries.value = item
}

function closeSeriesPicker() {
  selectedSeries.value = null
}

function showSelectionError(message: string) {
  const details: AppErrorDetails = {
    title: 'این عنوان هنوز آماده نیست',
    message,
    hint: 'یک عنوان دیگر را انتخاب کن یا بعداً دوباره سر بزن.',
    fields: [],
  }
  details.reason = details.message
  actionError.value = details
  notifications.notifyFromDetails(details, { inbox: false })
}

function trapSeriesDialog(event: KeyboardEvent) {
  if (event.key !== 'Tab' || !seriesDialog.value) return
  const controls = [...seriesDialog.value.querySelectorAll<HTMLElement>(pickerFocusable)]
    .filter(control => control.getClientRects().length > 0)
  const first = controls[0]
  const last = controls.at(-1)
  if (!first || !last) {
    event.preventDefault()
    seriesDialog.value.focus()
  } else if (event.shiftKey && document.activeElement === first) {
    event.preventDefault()
    last.focus()
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault()
    first.focus()
  }
}

watch(selectedSeries, async (series) => {
  if (!import.meta.client) return
  document.documentElement.style.overflow = series ? 'hidden' : ''
  if (series) {
    pickerPreviousFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null
    await nextTick()
    seriesDialog.value?.focus()
  } else {
    pickerPreviousFocus?.focus()
    pickerPreviousFocus = null
  }
})

onKeyStroke('Escape', () => {
  if (selectedSeries.value) closeSeriesPicker()
})

onBeforeUnmount(() => {
  if (import.meta.client) document.documentElement.style.overflow = ''
})

async function createParty(item: Movie, episodeId?: number) {
  const selection = selectionFor(item, episodeId)
  if (!selection) {
    showSelectionError(
      item.type === 'series'
        ? 'هنوز قسمت قابل پخشی برای این سریال پیدا نشد.'
        : 'این عنوان برای ساخت اتاق آماده نیست.',
    )
    return
  }
  if (creatingId.value !== null) return
  creatingId.value = item.id
  actionError.value = null
  try {
    const room = await api<WatchRoom>('/watch-party/rooms/', {
      method: 'POST',
      body: selection,
    })
    selectedSeries.value = null
    await navigateTo(`/watch-party/${room.invite_code}?created=1`)
  } catch (error) {
    actionError.value = notifications.notifyError(error, 'ساخت اتاق ممکن نشد.')
  } finally {
    creatingId.value = null
  }
}

async function resolveSeriesDetail(item: Movie) {
  if (item.episodes?.length) return item
  const requestId = ++resolveRequestId
  resolvingId.value = item.id
  actionError.value = null
  try {
    const detail = await loadItemFromApi(item.slug, 'series')
    if (requestId !== resolveRequestId) return null
    if (!detail) {
      showSelectionError('جزئیات قسمت‌های این سریال دریافت نشد.')
      return null
    }
    rememberResolvedSeries(detail)
    return detail
  } finally {
    if (requestId === resolveRequestId) resolvingId.value = null
  }
}

async function handleSelect(item: Movie, preferredEpisodeId?: number) {
  if (item.type === 'series') {
    const resolvedSeries = await resolveSeriesDetail(item)
    if (!resolvedSeries) return

    const episodes = resolvedSeries.episodes || []
    if (preferredEpisodeId && episodes.some(episode => episode.id === preferredEpisodeId)) {
      void createParty(resolvedSeries, preferredEpisodeId)
      return
    }
    if (episodes.length > 1) {
      openSeriesPicker(resolvedSeries)
      return
    }
    if (episodes[0]) {
      void createParty(resolvedSeries, episodes[0].id)
      return
    }
    showSelectionError('هنوز قسمت منتشرشده‌ای برای این سریال وجود ندارد.')
    return
  }
  void createParty(item)
}

function handleContinueSelect(item: Movie) {
  void handleSelect(item, continueEpisodeId(item))
}

async function resolvePrefillFromRoute() {
  const type = route.query.type === 'movie' || route.query.type === 'series'
    ? route.query.type
    : null
  const slug = String(route.query.slug || '').trim()
  const id = Number(route.query.id || 0)
  if (!type || (!slug && !id)) {
    prefilledItem.value = null
    return
  }

  prefilling.value = true
  try {
    let found: Movie | null = null
    if (slug) {
      found = await loadItemFromApi(slug, type)
    }
    if (!found && id) {
      found = catalog.value.find(item => item.type === type && item.id === id) || null
    }
    if (!found && slug) {
      found = catalog.value.find(item => item.type === type && item.slug === slug) || null
    }
    prefilledItem.value = found
    if (!found && String(route.query.title || '').trim()) {
      // Seed search so the user still sees the intended title quickly.
      if (!pickerQuery.value.trim()) pickerQuery.value = String(route.query.title)
      if (contentFilter.value === 'all') contentFilter.value = type
    }
  } finally {
    prefilling.value = false
  }
}

watch([debouncedQuery, contentFilter], () => {
  actionError.value = null
  void searchFullCatalog()
})
watchDebounced(pickerQuery, () => {
  if (!applyingRouteQuery) void syncPickerRoute()
}, { debounce: 650 })
watch(contentFilter, () => {
  if (!applyingRouteQuery) void syncPickerRoute()
})
watch(() => route.query, () => {
  applyPickerRoute()
  void resolvePrefillFromRoute()
}, { deep: true })

onMounted(async () => {
  if (source.value !== 'api') void loadFromApi()
  void searchFullCatalog()
  await resolvePrefillFromRoute()
})

useSeoMeta({
  title: 'تماشای گروهی',
  description: 'ساخت اتاق خصوصی برای تماشای هم‌ زمان فیلم و سریال با دوستان',
})
</script>

<template>
  <div class="cinema-page min-h-dvh pb-16 text-ink">
    <section class="page-section pb-0">
      <PageHero
        title="تماشای گروهی"
        eyebrow="اتاق خصوصی"
        description="با هم یک فیلم ببینید؛ میزبان پخش را کنترل می‌کند و بقیه هم‌زمان تماشا می‌کنند."
        icon="users"
      >
        <div class="mb-4 grid grid-cols-2 gap-2 sm:flex sm:flex-wrap">
          <button
            type="button"
            class="party-hub-btn party-hub-btn--create"
            @click="focusPartyAction('create')"
          >
            <CinematicIcon name="users" class="size-4" />
            ساخت اتاق
          </button>
          <button
            type="button"
            class="party-hub-btn party-hub-btn--join"
            @click="focusPartyAction('join')"
          >
            <CinematicIcon name="login" class="size-4" />
            ورود
          </button>
          <span class="col-span-2 inline-flex min-h-10 items-center justify-center gap-2 px-2 text-[11px] font-bold text-muted sm:col-auto sm:mr-auto">
            <CinematicIcon name="shield-check" class="size-3.5 text-success" />
            فقط با دعوت
          </span>
        </div>
        <ol class="grid gap-2 sm:grid-cols-3" aria-label="مراحل تماشای گروهی">
          <li
            v-for="item in partySteps"
            :key="item.step"
            class="flex items-start gap-2.5 rounded-xl bg-elevated/70 px-3 py-2.5 ring-1 ring-line"
          >
            <span class="grid size-7 shrink-0 place-items-center rounded-lg bg-primary-500/15 text-[11px] font-black text-brand">
              {{ item.step }}
            </span>
            <span class="min-w-0">
              <span class="block text-xs font-black text-ink">{{ item.title }}</span>
              <span class="mt-0.5 block text-[11px] text-muted">{{ item.hint }}</span>
            </span>
          </li>
        </ol>
      </PageHero>
    </section>

    <section id="party-join" class="page-section scroll-mt-20 pt-4" aria-labelledby="party-join-title">
      <div class="relative overflow-hidden rounded-2xl bg-gradient-to-l from-info/10 via-surface to-surface p-4 ring-1 ring-info/20 sm:p-5">
        <div class="pointer-events-none absolute -left-12 -top-16 size-40 rounded-full bg-info/10 blur-3xl" aria-hidden="true" />
        <div class="flex flex-wrap items-end justify-between gap-3">
          <div>
            <p class="inline-flex items-center gap-1.5 text-[11px] font-black text-info">
              <CinematicIcon name="login" class="size-3.5" />
              لینک داری؟
            </p>
            <h2 id="party-join-title" class="mt-1 text-lg font-black sm:text-xl">ورود به اتاق</h2>
            <p class="mt-1 text-xs leading-6 text-secondary">کد دعوت یا لینک کامل را بچسبان.</p>
          </div>
        </div>
        <form class="mt-4 flex flex-col gap-2 sm:flex-row" @submit.prevent="joinWithCode">
          <label class="sr-only" for="party-join-code">کد یا لینک دعوت</label>
          <input
            id="party-join-code"
            ref="joinInput"
            v-model="joinDraft"
            type="text"
            dir="ltr"
            autocomplete="off"
            spellcheck="false"
            placeholder="کد دعوت یا https://…/watch-party/…"
            class="ui-field min-h-12 flex-1 font-latin text-sm focus:border-info/60 focus:ring-info/15"
            :aria-invalid="Boolean(joinError)"
            :aria-describedby="joinError ? 'party-join-error' : undefined"
          >
          <button
            type="submit"
            class="party-hub-btn party-hub-btn--join-solid shrink-0"
            :disabled="joining"
          >
            <span v-if="joining" class="size-3.5 animate-spin rounded-full border border-[#071419]/30 border-t-[#071419]" />
            <CinematicIcon v-else name="login" class="size-4" />
            ورود
          </button>
        </form>
        <p v-if="joinError" id="party-join-error" class="mt-2 text-[11px] font-bold text-error" role="alert">{{ joinError }}</p>
      </div>
    </section>

    <section
      v-if="prefilledItem || prefilling"
      class="page-section pt-2"
      aria-labelledby="party-prefill-title"
    >
      <div class="overflow-hidden rounded-2xl bg-surface ring-1 ring-primary-500/25">
        <div class="flex flex-wrap items-center gap-4 p-4 sm:p-5">
          <div
            v-if="prefilling && !prefilledItem"
            class="flex min-h-24 w-full items-center justify-center gap-3 text-sm text-secondary"
          >
            <span class="size-5 animate-spin rounded-full border-2 border-line border-t-primary-500" />
            در حال آماده‌سازی عنوان…
          </div>
          <template v-else-if="prefilledItem">
            <div class="relative aspect-[2/3] w-20 shrink-0 overflow-hidden rounded-xl bg-canvas-soft sm:w-24">
              <NuxtImg
                v-if="prefilledItem.poster_url"
                :src="prefilledItem.poster_url"
                :alt="prefilledItem.title"
                class="h-full w-full object-cover"
              />
              <div v-else class="grid h-full place-items-center text-muted">
                <CinematicIcon name="film" class="size-6" />
              </div>
            </div>
            <div class="min-w-0 flex-1">
              <p class="text-[11px] font-black text-brand">آماده ساخت اتاق</p>
              <h2 id="party-prefill-title" class="mt-1 truncate text-lg font-black" dir="auto">
                {{ prefilledItem.title }}
              </h2>
              <p class="mt-1 text-xs text-muted">
                {{ prefilledItem.type === 'movie' ? 'فیلم' : 'سریال' }}
                <span v-if="prefilledItem.year"> · {{ prefilledItem.year }}</span>
              </p>
            </div>
            <button
              type="button"
              class="party-hub-btn party-hub-btn--create w-full sm:w-auto"
              :disabled="creatingId !== null || resolvingId !== null"
              @click="handleSelect(prefilledItem)"
            >
              <span
                v-if="creatingId === prefilledItem.id || resolvingId === prefilledItem.id"
                class="size-3.5 animate-spin rounded-full border border-night-950/30 border-t-night-950"
              />
              <CinematicIcon v-else name="users" class="size-4" />
              {{ creatingId === prefilledItem.id
                ? 'ساخت…'
                : resolvingId === prefilledItem.id
                  ? 'قسمت‌ها…'
                  : prefilledItem.type === 'series'
                    ? 'انتخاب قسمت'
                    : 'ساخت اتاق' }}
            </button>
          </template>
        </div>
      </div>
    </section>

    <section
      v-if="continueWatching.length && !pickerQuery"
      class="page-section pt-2"
      aria-labelledby="party-continue-title"
    >
      <SectionHeader id="party-continue-title" title="ادامه از تماشاهای اخیر" eyebrow="سریع‌تر شروع کن" icon="resume" dark />
      <div class="hide-scrollbar rail-bleed flex snap-x gap-3 overflow-x-auto pb-2">
        <button
          v-for="item in continueWatching.slice(0, 8)"
          :key="`continue-${item.type}-${item.id}`"
          type="button"
          class="w-[min(72%,14rem)] shrink-0 snap-start overflow-hidden rounded-2xl bg-surface text-right ring-1 ring-line transition hover:ring-primary-500/40"
          :disabled="creatingId !== null"
          @click="handleContinueSelect(item)"
        >
          <div class="relative aspect-video overflow-hidden bg-canvas-soft">
            <NuxtImg :src="item.backdrop_url || item.poster_url" :alt="item.title" class="h-full w-full object-cover" loading="lazy" />
            <div class="absolute inset-x-0 bottom-0 h-1.5 bg-white/15">
              <div class="h-full bg-primary-500" :style="{ width: `${item.progress_percent}%` }" />
            </div>
          </div>
          <div class="p-3">
            <p class="truncate text-sm font-black">{{ item.title }}</p>
            <p class="mt-1 text-[11px] text-muted">ساخت اتاق · {{ item.progress_percent }}٪</p>
          </div>
        </button>
      </div>
    </section>

    <section id="party-create" class="page-section scroll-mt-20" aria-labelledby="party-create-title">
      <div class="mb-5 flex flex-wrap items-end justify-between gap-4">
        <div>
          <p class="text-xs font-black text-brand">یا عنوان جدید</p>
          <h2 id="party-create-title" class="mt-1 text-xl font-black text-ink sm:text-2xl">جستجو و ساخت اتاق</h2>
        </div>
        <div class="grid w-full grid-cols-3 gap-1 rounded-xl bg-elevated p-1 ring-1 ring-line sm:w-auto" role="group" aria-label="نوع محتوا">
          <button
            v-for="option in [
              { value: 'all', label: 'همه' },
              { value: 'movie', label: 'فیلم' },
              { value: 'series', label: 'سریال' },
            ] as const"
            :key="option.value"
            type="button"
            class="min-h-11 rounded-lg px-3 text-xs font-black transition"
            :class="contentFilter === option.value
              ? 'bg-primary-500 text-night-950 shadow-sm'
              : 'text-secondary hover:bg-surface hover:text-ink'"
            :aria-pressed="contentFilter === option.value"
            @click="contentFilter = option.value"
          >
            {{ option.label }}
          </button>
        </div>
      </div>

      <label class="relative mb-2 block">
        <span class="sr-only">جستجوی عنوان برای اتاق</span>
        <CinematicIcon name="search" class="pointer-events-none absolute right-3.5 top-1/2 size-4.5 -translate-y-1/2 text-muted" />
        <input
          ref="pickerInput"
          v-model="pickerQuery"
          type="search"
          class="ui-field w-full pr-11 pl-12"
          placeholder="نام فارسی یا انگلیسی فیلم و سریال…"
          autocomplete="off"
          enterkeyhint="search"
          spellcheck="false"
          @focus="searchInputFocused = true"
          @blur="searchInputFocused = false"
        >
        <button
          v-if="pickerQuery"
          type="button"
          class="absolute left-1 top-1/2 grid size-11 -translate-y-1/2 place-items-center rounded-xl text-muted hover:bg-primary-500/10 hover:text-brand"
          aria-label="پاک کردن جستجو"
          @click="pickerQuery = ''"
        >
          <CinematicIcon name="x" class="size-4" />
        </button>
      </label>
      <div class="mb-6 flex min-h-6 items-center justify-between gap-3 px-1 text-[11px]" aria-live="polite">
        <p :class="searchError ? 'text-warning' : 'text-muted'">{{ searchError || searchStatus }}</p>
        <span v-if="searchPending" class="size-3.5 shrink-0 animate-spin rounded-full border border-line border-t-primary-500" />
      </div>

      <UiErrorAlert v-if="actionError" class="mb-5" :error="actionError" @close="actionError = null" />

      <div
        v-if="!catalogReady && !filteredPool.length && (pending || !catalogError)"
        class="grid min-h-64 place-items-center rounded-3xl border border-line bg-surface"
      >
        <div class="text-center">
          <span class="mx-auto block size-10 animate-spin rounded-full border-2 border-line border-t-primary-500" />
          <p class="mt-3 text-sm font-bold text-secondary">در حال دریافت عنوان‌ها…</p>
        </div>
      </div>

      <div
        v-else-if="catalogError && !catalogReady && !filteredPool.length"
        class="grid min-h-64 place-items-center rounded-3xl border border-error/20 bg-surface p-6 text-center"
      >
        <div>
          <CinematicIcon name="signal-off" class="mx-auto size-9 text-error" />
          <h3 class="mt-4 text-lg font-black">فهرست فیلم‌ها باز نشد</h3>
          <p class="mt-2 text-sm leading-7 text-secondary">برای ساخت اتاق باید به فهرست اصلی دسترسی داشته باشیم.</p>
          <button
            type="button"
            class="mt-5 min-h-11 rounded-xl bg-primary-500 px-5 text-sm font-black text-night-950 hover:bg-primary-400"
            @click="() => loadFromApi(true)"
          >
            تلاش دوباره
          </button>
        </div>
      </div>

      <div
        v-else-if="searchPending && !filteredPool.length"
        class="grid min-h-64 place-items-center rounded-3xl border border-line bg-surface"
      >
        <div class="text-center">
          <span class="mx-auto block size-10 animate-spin rounded-full border-2 border-line border-t-primary-500" />
          <p class="mt-3 text-sm font-bold text-secondary">در حال جستجو…</p>
        </div>
      </div>

      <div
        v-else-if="filteredPool.length"
        class="catalog-grid"
        :aria-busy="searchPending"
      >
        <article
          v-for="item in filteredPool"
          :key="`${item.type}-${item.id}`"
          class="cinematic-card group flex min-w-0 flex-col overflow-hidden rounded-2xl"
        >
          <NuxtLink :to="detailPath(item)" class="block">
            <CinematicImage
              :src="item.poster_url"
              :alt="`پوستر ${item.title}`"
              ratio="poster"
              image-class="transition-transform duration-300 group-hover:scale-[1.025]"
            />
          </NuxtLink>
          <div class="flex flex-1 flex-col p-3">
            <p class="text-[10px] font-black text-primary-400">
              {{ item.type === 'movie'
                ? 'فیلم'
                : item.episodes?.length
                  ? `سریال · ${item.episodes.length} قسمت`
                  : 'سریال · انتخاب قسمت' }}
            </p>
            <h3 class="mt-1 truncate text-sm font-black">{{ item.title }}</h3>
            <p class="mt-1 text-[11px] text-muted">{{ item.year }} · {{ item.age_rating }}</p>
            <button
              type="button"
              :disabled="creatingId !== null && creatingId !== item.id"
              class="party-hub-btn party-hub-btn--create mt-3 w-full text-[11px]"
              @click="handleSelect(item)"
            >
              <span
                v-if="creatingId === item.id || resolvingId === item.id"
                class="size-3.5 animate-spin rounded-full border border-night-950/30 border-t-night-950"
              />
              <CinematicIcon v-else name="users" class="size-4" />
              {{ creatingId === item.id
                ? 'ساخت…'
                : resolvingId === item.id
                  ? 'قسمت‌ها…'
                  : item.type === 'series'
                    ? 'انتخاب قسمت'
                    : 'ساخت اتاق' }}
            </button>
          </div>
        </article>
      </div>

      <EmptyState
        v-else
        title="عنوانی پیدا نشد"
        description="نام فارسی یا انگلیسی کوتاه‌تری بنویس، یا فیلتر فیلم و سریال را تغییر بده."
      />
    </section>

    <Teleport to="body">
      <div
        v-if="selectedSeries"
        class="theme-media-dark fixed inset-0 z-[80] grid place-items-end bg-black/55 p-0 sm:place-items-center sm:p-4"
        @click.self="closeSeriesPicker"
      >
        <section
          ref="seriesDialog"
          tabindex="-1"
          class="max-h-[calc(100dvh_-_1rem_-_env(safe-area-inset-top)_-_env(safe-area-inset-bottom))] w-[min(100%,calc(100dvw-1rem))] overflow-hidden rounded-t-3xl bg-surface text-ink shadow-2xl outline-none sm:max-h-[min(80dvh,36rem)] sm:max-w-lg sm:rounded-3xl"
          role="dialog"
          aria-modal="true"
          :aria-label="`انتخاب قسمت ${selectedSeries.title}`"
          @keydown="trapSeriesDialog"
        >
          <header class="flex items-center justify-between gap-3 border-b border-line p-4">
            <div class="min-w-0">
              <p class="text-[11px] font-bold text-muted">انتخاب قسمت</p>
              <h3 class="truncate text-base font-black">{{ selectedSeries.title }}</h3>
            </div>
            <button type="button" class="grid size-11 place-items-center rounded-xl hover:bg-elevated" aria-label="بستن" @click="closeSeriesPicker">
              <CinematicIcon name="x" class="size-4.5" />
            </button>
          </header>
          <div class="cinematic-scrollbar max-h-[min(60dvh,28rem)] space-y-2 overflow-y-auto p-3">
            <button
              v-for="episode in (selectedSeries.episodes || [])"
              :key="episode.id"
              type="button"
              class="flex w-full items-center justify-between gap-3 rounded-2xl bg-elevated px-3 py-3 text-right ring-1 ring-line transition hover:ring-primary-500/35"
              :disabled="creatingId !== null"
              @click="createParty(selectedSeries!, episode.id)"
            >
              <span class="min-w-0">
                <span class="block text-sm font-black">قسمت {{ episode.episode_number }} · فصل {{ episode.season_number || 1 }}</span>
                <span class="mt-0.5 block truncate text-[11px] text-muted">{{ episode.title }}</span>
              </span>
              <span class="inline-flex shrink-0 items-center gap-1 text-xs font-black text-primary-300">
                ساخت اتاق
                <CinematicIcon name="users" class="size-3.5" />
              </span>
            </button>
          </div>
        </section>
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
.party-hub-btn {
  display: inline-flex;
  min-height: 2.75rem;
  align-items: center;
  justify-content: center;
  gap: 0.4rem;
  border-radius: 0.9rem;
  border: 1px solid transparent;
  padding-inline: 1rem;
  font-size: 0.8125rem;
  font-weight: 900;
  transition:
    transform 160ms ease,
    background-color 160ms ease,
    border-color 160ms ease,
    color 160ms ease,
    box-shadow 180ms ease,
    filter 160ms ease;
}

.party-hub-btn:hover:not(:disabled) {
  transform: translateY(-1px);
}

.party-hub-btn:active:not(:disabled) {
  transform: scale(0.98);
}

.party-hub-btn:disabled {
  background: var(--color-disabled, #3a3a3a);
  color: var(--color-canvas, #9ca3af);
  box-shadow: none;
  transform: none;
}

.party-hub-btn--create {
  color: var(--color-night-950, #07140f);
  background: var(--color-primary-500, #b0e4cc);
  box-shadow: 0 8px 20px rgb(176 228 204 / 14%);
}

.party-hub-btn--create:hover:not(:disabled) {
  background: var(--color-primary-400, #c8efdc);
  box-shadow: 0 12px 26px rgb(176 228 204 / 28%);
}

.party-hub-btn--join {
  color: #7dd3fc;
  background: rgb(14 165 233 / 12%);
  border-color: rgb(56 189 248 / 28%);
}

.party-hub-btn--join:hover:not(:disabled) {
  color: #e0f2fe;
  background: rgb(14 165 233 / 24%);
  border-color: rgb(56 189 248 / 48%);
  box-shadow: 0 10px 24px rgb(14 165 233 / 18%);
}

.party-hub-btn--join-solid {
  color: #071419;
  background: #38bdf8;
  min-width: 5.5rem;
}

.party-hub-btn--join-solid:hover:not(:disabled) {
  background: #7dd3fc;
  box-shadow: 0 10px 24px rgb(56 189 248 / 26%);
}

@media (max-width: 379px) {
  .party-hub-btn {
    min-height: 2.55rem;
    padding-inline: 0.7rem;
    font-size: 0.75rem;
  }
}
</style>
