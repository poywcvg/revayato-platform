<script setup lang="ts">
import type { ContentType, Movie } from '~/types'
import {
  adaptApiCatalogListItem,
  type ApiCatalogItem,
  type ApiListResponse,
  unwrapApiList,
} from '~/data/catalogAdapter'
import {
  rankFeatured,
  rankNewest,
  rankPopular,
  rankTrending,
  trendingScore,
} from '~/utils/trendingScore'

const { catalog, recentlyAdded, pending, error, loadFromApi } = useCatalog()
const { api } = useApi()
const config = useRuntimeConfig()
const route = useRoute()
const authStore = useAuthStore()

function heroScore(item: Movie) {
  return trendingScore(item) * 0.55
    + Number(item.is_new) * 4
    + Number(item.is_recommended) * 3
    + Number(item.has_backdrop ?? true) * 2
    + Number(item.has_artwork ?? true)
    + ((item.ratings || []).some(entry => entry.source === 'imdb' || entry.source === 'tmdb') ? 1 : 0)
    + Number(item.is_dubbed || item.has_subtitle) * 2
}

const railLimit = 7
const movies = computed(() => catalog.value.filter(item => item.type === 'movie'))
const seriesOnly = computed(() => catalog.value.filter(item => item.type === 'series'))

/** Backend-scored rails — frontend only renders. */
const remoteTrending = ref<Movie[]>([])
const remoteFeatured = ref<Movie[]>([])
const remoteDubbed = ref<Movie[]>([])
const remotePopularSeries = ref<Movie[]>([])
/** Dedicated «تازه اضافه‌شده‌ها» rail — independent of the lean catalog merge. */
const remoteRecent = ref<Movie[]>([])
const shellPending = ref(true)
const railMeta = ref<{
  focus_genre?: string
  focus_genre_title?: string
  eyebrow?: Record<string, string>
}>({})

const heroSource = computed(() => {
  if (catalog.value.length) return catalog.value
  return remoteRecent.value
})

const heroItems = computed(() => {
  const source = heroSource.value
  const withArt = source.filter(item => item.has_backdrop !== false && item.has_artwork !== false)
  const pool = withArt.length >= 3 ? withArt : source.filter(item => item.backdrop_url && item.poster_url)
  return [...pool].sort((a, b) => heroScore(b) - heroScore(a)).slice(0, 6)
})

const homeBusy = computed(() => (pending.value || shellPending.value) && !heroSource.value.length)

const trending = computed(() => {
  if (remoteTrending.value.length) return remoteTrending.value.slice(0, railLimit)
  return rankTrending(movies.value, railLimit)
})

const featuredPicks = computed(() => {
  if (remoteFeatured.value.length) return remoteFeatured.value.slice(0, railLimit)
  return rankFeatured(catalog.value, railLimit)
})
const newReleases = computed(() => {
  if (remoteRecent.value.length) return remoteRecent.value.slice(0, railLimit)
  const pool = recentlyAdded.value.length
    ? recentlyAdded.value
    : rankNewest(catalog.value, Math.min(catalog.value.length, railLimit * 2))
  return pool.slice(0, railLimit)
})
const newReleasesEyebrow = computed(() => {
  const movieCount = newReleases.value.filter(item => item.type === 'movie').length
  const seriesCount = newReleases.value.filter(item => item.type === 'series').length
  const parts = [
    movieCount ? `${movieCount.toLocaleString('fa-IR')} فیلم` : '',
    seriesCount ? `${seriesCount.toLocaleString('fa-IR')} سریال` : '',
  ].filter(Boolean)
  return parts.length ? parts.join(' و ') : 'جدیدترین عنوان‌های آرشیو'
})
const popularSeries = computed(() => {
  if (remotePopularSeries.value.length) return remotePopularSeries.value.slice(0, railLimit)
  return rankPopular(seriesOnly.value, railLimit)
})
const dubbed = computed(() => {
  const remote = remoteDubbed.value.filter(item => item.is_dubbed)
  if (remote.length) return remote.slice(0, railLimit)
  const fromCatalog = catalog.value.filter(item => item.is_dubbed)
  return rankPopular(fromCatalog, railLimit)
})
const dubbedEyebrow = computed(() =>
  railMeta.value.eyebrow?.dubbed || 'فقط نسخه دوبله فارسی',
)
const featuredEyebrow = computed(() =>
  railMeta.value.eyebrow?.featured || 'انتخاب‌های تازه این بازه',
)
const popularSeriesEyebrow = computed(() =>
  railMeta.value.eyebrow?.popular_series || 'بر اساس بازدید، پسند و تازگی',
)
const familyAnimation = computed(() => {
  const pool = catalog.value.filter(item =>
    item.format === 'animation'
    || item.genres.some(genre => ['family', 'kids', 'animation'].includes(genre.slug)),
  )
  return rankPopular(pool, railLimit)
})
const { recommendations: recommended, isPersonalized, personalizationLevel } = usePersonalizedRecommendations(railLimit)
const { continueWatching: progressItems } = useWatchProgress()
const recommendationEyebrow = computed(() => ({
  cold_start: 'برای شروع',
  learning: 'در حال شکل‌گیری',
  growing: 'نزدیک به سلیقه تو',
  tuned: 'مخصوص تو',
}[personalizationLevel.value]))
const continueWatching = computed(() => progressItems.value.slice(0, railLimit))
const hasContinue = computed(() => continueWatching.value.length > 0)
const activeCategory = ref('all')
const { trackFilterApply } = useAnalyticsEvent()

const categoryOptions = [
  { label: 'منتخب‌ها', value: 'all', icon: 'sparkles' as const, mobile: true },
  { label: 'فیلم', value: 'movie', icon: 'movie' as const, mobile: true },
  { label: 'سریال', value: 'series', icon: 'series' as const, mobile: true },
  { label: 'انیمیشن', value: 'animation', icon: 'animation' as const, mobile: true },
  { label: 'دوبله', value: 'dubbed', icon: 'audio' as const, mobile: true },
]

const categoryItems = computed(() => {
  const value = activeCategory.value
  if (value === 'all') return featuredPicks.value
  if (value === 'movie') return remoteFeatured.value.length ? remoteFeatured.value.slice(0, railLimit) : rankFeatured(movies.value, railLimit)
  if (value === 'series') return popularSeries.value
  if (value === 'animation') return familyAnimation.value
  if (value === 'dubbed') return dubbed.value
  return []
})

const activeCategoryLabel = computed(() => categoryOptions.find(option => option.value === activeCategory.value)?.label || 'منتخب‌ها')
const activeCategoryIcon = computed(() => categoryOptions.find(option => option.value === activeCategory.value)?.icon || 'sparkles')
const activeCategoryHref = computed(() => {
  if (activeCategory.value === 'series') return '/series?sort=popular'
  if (activeCategory.value === 'movie') return '/movies?sort=featured'
  if (activeCategory.value === 'animation') return '/movies?format=animation'
  if (activeCategory.value === 'dubbed') return '/movies?availability=dubbed'
  return '/movies?sort=featured'
})
const activeCategoryEyebrow = computed(() => {
  if (activeCategory.value === 'all' || activeCategory.value === 'movie') return featuredEyebrow.value
  if (activeCategory.value === 'series') return popularSeriesEyebrow.value
  if (activeCategory.value === 'dubbed') return dubbedEyebrow.value
  return `${categoryItems.value.length} عنوان`
})

watch(activeCategory, value => trackFilterApply('home_category', value))

async function loadRecentRail() {
  const mediaBase = String(config.public.mediaCdnBaseUrl)
  try {
    const response = await api<ApiListResponse<ApiCatalogItem & { content_type?: ContentType }>>('/catalog/recent/', {
      query: { limit: railLimit },
      // Keep first paint snappy; catalog/recent is cached and usually sub-second.
      timeout: 6_000,
    })
    remoteRecent.value = unwrapApiList(response).map((item) => {
      const type: ContentType = item.content_type === 'series' ? 'series' : 'movie'
      return adaptApiCatalogListItem(item, type, mediaBase)
    })
  }
  catch {
    remoteRecent.value = []
  }
}

async function loadHeroShell() {
  // The home catalog load already fetches /movies/?limit=12&sort=popular (the
  // popularMovies=12 slice in useContent's home mode), so we reuse that instead
  // of firing the identical request a second time.
  await loadFromApi(false, 'home')
}

async function loadRemoteDiscovery() {
  const mediaBase = String(config.public.mediaCdnBaseUrl)
  const adaptMovies = (rows: ApiCatalogItem[] | undefined) =>
    (rows || []).map(item => adaptApiCatalogListItem(item, 'movie', mediaBase))
  const adaptSeries = (rows: ApiCatalogItem[] | undefined) =>
    (rows || []).map(item => adaptApiCatalogListItem(item, 'series', mediaBase))

  const [trendingResult, railsResult] = await Promise.allSettled([
    api<{ movies?: ApiCatalogItem[] }>('/trending/', {
      query: { type: 'movie', limit: railLimit },
    }),
    api<{
      meta?: {
        focus_genre?: string
        focus_genre_title?: string
        eyebrow?: Record<string, string>
      }
      featured?: ApiCatalogItem[]
      dubbed?: ApiCatalogItem[]
      popular_series?: ApiCatalogItem[]
    }>('/home/rails/', {
      query: { limit: railLimit },
    }),
  ])

  if (trendingResult.status === 'fulfilled') {
    remoteTrending.value = adaptMovies(trendingResult.value.movies)
  } else {
    remoteTrending.value = []
  }

  if (railsResult.status === 'fulfilled') {
    const payload = railsResult.value
    railMeta.value = payload.meta || {}
    remoteFeatured.value = adaptMovies(payload.featured)
    remoteDubbed.value = adaptMovies(payload.dubbed).filter(item => item.is_dubbed)
    remotePopularSeries.value = adaptSeries(payload.popular_series)
  } else {
    railMeta.value = {}
    remoteFeatured.value = []
    remoteDubbed.value = []
    remotePopularSeries.value = []
  }
}

async function refreshHomeShell(force = false) {
  await Promise.all([
    loadRecentRail(),
    loadHeroShell(),
    loadFromApi(force, 'home'),
  ])
}

// Block SSR only on the two fast shell endpoints (recent + popular hero).
// Full catalog merge + discovery rails hydrate after paint so TTFB stays low.
try {
  await Promise.all([loadRecentRail(), loadHeroShell()])
}
finally {
  shellPending.value = false
}

async function revealRequestedSection(section: unknown) {
  if (!import.meta.client || section !== 'recommended') return
  await nextTick()
  document.getElementById('recommended')?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

watch(() => route.query.section, revealRequestedSection)
onMounted(() => {
  void revealRequestedSection(route.query.section)
  void loadFromApi(false, 'home')
  void loadRemoteDiscovery()
})
useSeoMeta({ title: 'خانه', description: 'در روایتو فیلم و سریال را پیدا کن، تماشا کن و تجربه‌ات را با دوستانت به اشتراک بگذار.' })
</script>

<template>
  <div class="home-landing overflow-x-clip pb-8 sm:pb-14" :aria-busy="homeBusy">
    <HeroMovieSlider :items="heroItems" :loading="homeBusy" />

    <CatalogSourceNotice class="content-section pt-2 sm:pt-4" :error="error" :pending="pending || shellPending" @retry="() => refreshHomeShell(true)" />

    <section v-if="!shellPending && !pending && !heroSource.length && !newReleases.length" class="content-section">
      <EmptyState
        :title="error ? 'فهرست محتوا در دسترس نیست' : 'هنوز عنوانی برای نمایش آماده نیست'"
        :description="error
          ? 'ارتباط با سرویس محتوا برقرار نشد. یک‌بار دیگر تلاش کن یا کمی بعد سر بزن.'
          : 'کاتالوگ در حال تکمیل است. کمی بعد دوباره سر بزن یا صفحه فیلم‌ها را بررسی کن.'"
        icon="film"
        :action-label="error ? 'تلاش دوباره' : 'رفتن به فیلم‌ها'"
        :action-href="error ? undefined : '/movies'"
        :action-handler="error ? () => refreshHomeShell(true) : undefined"
      />
    </section>

    <LazyMovieRow
      v-if="newReleases.length"
      hydrate-on-visible
      title="تازه اضافه‌شده‌ها"
      :eyebrow="newReleasesEyebrow"
      description="جدیدترین فیلم‌ها و سریال‌هایی که به آرشیو روایتو اضافه شده‌اند."
      :items="newReleases"
      href="/new"
      link-label="همه تازه‌ها"
      icon="sparkles"
      dark
    />

    <!-- Below-fold: client-only to keep SSR HTML lean (was ~600KB+ with every rail). -->
    <ClientOnly>
      <DeferredContent v-if="hasContinue" class="home-landing__deferred" min-height="14rem">
        <section id="continue" class="content-section">
          <SectionHeader title="ادامه تماشا" eyebrow="از همان‌جا ادامه بده" href="/profile#continue" icon="resume" dark />
          <div class="hide-scrollbar rail-bleed flex snap-x gap-2.5 overflow-x-auto pb-2 sm:gap-3 sm:pb-3 lg:grid lg:grid-cols-3 lg:gap-4 lg:overflow-visible xl:grid-cols-4 2xl:grid-cols-7">
            <ContinueWatchingCard v-for="item in continueWatching" :key="item.id" :item="item" class="w-[min(82%,16.5rem)] shrink-0 snap-start lg:w-auto" />
          </div>
        </section>
      </DeferredContent>

      <section class="content-section" aria-labelledby="home-party-title">
        <NuxtLink
          to="/watch-party"
          class="group flex flex-wrap items-center justify-between gap-4 rounded-2xl bg-elevated/80 px-4 py-4 ring-1 ring-line transition hover:ring-primary-500/35 sm:px-5"
        >
          <div class="flex min-w-0 items-start gap-3">
            <span class="grid size-11 shrink-0 place-items-center rounded-xl bg-primary-500/15 text-brand">
              <CinematicIcon name="users" class="size-5" />
            </span>
            <div class="min-w-0">
              <p class="text-[11px] font-black text-brand">با دوستان</p>
              <h2 id="home-party-title" class="mt-0.5 text-base font-black text-ink sm:text-lg">تماشای گروهی</h2>
              <p class="mt-1 text-xs leading-6 text-secondary">اتاق خصوصی بساز، لینک بفرست و هم‌زمان تماشا کنید.</p>
            </div>
          </div>
          <span class="inline-flex min-h-11 items-center gap-1.5 rounded-xl bg-primary-500 px-4 text-xs font-black text-night-950 transition group-hover:bg-primary-400">
            شروع
            <CinematicIcon name="arrow-left" class="size-3.5" />
          </span>
        </NuxtLink>
      </section>

      <DeferredContent v-if="authStore.isAuthenticated && recommended.length" class="home-landing__deferred">
        <LazyMovieRow
          id="recommended"
          hydrate-on-visible
          title="پیشنهادهای مخصوص تو"
          :eyebrow="recommendationEyebrow"
          :description="isPersonalized ? 'انتخاب‌شده برای سلیقه تو' : 'با تماشا و پسند، دقیق‌تر می‌شود'"
          :items="recommended"
          href="/profile#personalization"
          icon="wand"
          dark
          show-reasons
        />
      </DeferredContent>

      <DeferredContent v-if="trending.length" class="home-landing__deferred">
        <LazyMovieRow
          hydrate-on-visible
          title="ترند امروز"
          eyebrow="داغ‌ترین‌های امروز"
          :items="trending"
          href="/movies?sort=trending"
          icon="trend"
          dark
        />
      </DeferredContent>

      <DeferredContent v-if="catalog.length || featuredPicks.length" class="home-landing__deferred" min-height="8rem">
        <section class="content-section" aria-labelledby="home-categories-title">
          <SectionHeader
            id="home-categories-title"
            title="با سلیقه‌ات انتخاب کن"
            eyebrow="مرور دسته‌بندی‌ها"
            :href="activeCategoryHref"
            link-label="مشاهده همه"
            icon="sliders"
            dark
          />
          <CategoryChips v-model="activeCategory" :items="categoryOptions" />
        </section>
        <LazyMovieRow
          v-if="categoryItems.length"
          :key="activeCategory"
          hydrate-on-visible
          :title="activeCategoryLabel"
          :eyebrow="activeCategoryEyebrow"
          :items="categoryItems"
          :href="activeCategoryHref"
          :icon="activeCategoryIcon"
          dark
        />
      </DeferredContent>

      <DeferredContent v-if="dubbed.length" class="home-landing__deferred">
        <LazyMovieRow
          hydrate-on-visible
          title="دوبله فارسی"
          :eyebrow="dubbedEyebrow"
          :items="dubbed"
          href="/movies?availability=dubbed"
          icon="audio"
          dark
        />
      </DeferredContent>
      <DeferredContent v-if="popularSeries.length" class="home-landing__deferred">
        <LazyMovieRow
          hydrate-on-visible
          title="سریال‌های محبوب"
          :eyebrow="popularSeriesEyebrow"
          :items="popularSeries"
          href="/series?sort=popular"
          icon="series"
          dark
        />
      </DeferredContent>
      <template #fallback>
        <div class="content-section space-y-6 py-6" aria-hidden="true">
          <div class="h-40 animate-pulse rounded-2xl bg-elevated/60" />
          <div class="h-52 animate-pulse rounded-2xl bg-elevated/50" />
        </div>
      </template>
    </ClientOnly>
  </div>
</template>
