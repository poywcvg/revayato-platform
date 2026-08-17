import type { AgeRating, ContentType, Genre, Movie } from '~/types'
import { catalogGenres, mergeCatalogGenres } from '~/data/genres'
import { countryCodeForName, localizeCountry } from '~/data/countries'
import { adaptApiCatalogItem, adaptApiCatalogListItem, adaptApiGenre, unwrapApiList } from '~/data/catalogAdapter'
import type { ApiCatalogItem, ApiGenre, ApiListResponse } from '~/data/catalogAdapter'
import { normalizeSearchText, rankCatalogSearch, scoreCatalogItem } from '~/utils/searchRank'
import { featuredScore, popularScore, trendingScore, newestTimestamp } from '~/utils/trendingScore'

export type CatalogSort = 'newest' | 'rating' | 'popular' | 'trending' | 'featured' | 'imdb_top'
export type CatalogLoadMode = 'home' | 'full'

export interface CatalogFilters {
  query: string
  genre: string
  year: string
  ageRating: AgeRating | 'all'
  country: string
  language: string
  availability: 'all' | 'dubbed' | 'subtitle' | 'download'
  format: 'all' | 'animation' | 'short' | 'live_action'
  minRating: string
  sort: CatalogSort
  type?: ContentType
}

/** Client-only shared fetch; never store Promises in useState (SSR payload). */
let clientCatalogInflight: { mode: CatalogLoadMode, promise: Promise<void> } | null = null

export function useCatalog() {
  const config = useRuntimeConfig()
  const { api } = useApi()
  const catalogState = useState<Movie[]>('catalog-items', () => [])
  const recentlyAddedState = useState<Movie[]>('catalog-recently-added', () => [])
  const genreState = useState<Genre[]>('catalog-genres', () => [...catalogGenres])
  const source = useState<'api' | 'empty'>('catalog-source', () => 'empty')
  const listLoaded = useState('catalog-list-loaded', () => false)
  const listLoadedAt = useState('catalog-list-loaded-at', () => 0)
  const listCoverage = useState<CatalogLoadMode | 'none'>('catalog-list-coverage', () => 'none')
  const listPending = useState('catalog-list-pending', () => false)
  const detailRequests = useState('catalog-detail-requests', () => 0)
  // Nuxt serializes useState values into the SSR payload. FetchError/Error
  // instances are not serializable by devalue, so keep only a plain message.
  const error = useState<string | null>('catalog-error', () => null)
  const catalog = computed(() => catalogState.value)
  const recentlyAdded = computed(() => recentlyAddedState.value)
  const genres = computed(() => genreState.value)
  const pending = computed(() => listPending.value || detailRequests.value > 0)
  const CATALOG_TTL_MS = 15 * 60_000

  function invalidateCatalog() {
    listLoaded.value = false
    listLoadedAt.value = 0
    listCoverage.value = 'none'
  }

  async function loadFromApi(force = false, mode: CatalogLoadMode = 'full') {
    const hasCoverage = mode === 'home'
      ? listCoverage.value === 'home' || listCoverage.value === 'full'
      : listCoverage.value === 'full'
    const fresh = listLoaded.value && hasCoverage && (Date.now() - listLoadedAt.value) < CATALOG_TTL_MS
    if (!force && fresh) return
    if (import.meta.client && clientCatalogInflight) {
      if (mode === 'home' || clientCatalogInflight.mode === 'full') {
        return clientCatalogInflight.promise
      }
      // A full navigation arrived while the lean home request was running.
      // Finish that request first, then expand the catalog exactly once.
      await clientCatalogInflight.promise
      return loadFromApi(force, 'full')
    }
    // Same-request SSR/client: await the in-flight load instead of bailing out.
    if (listPending.value) {
      if (clientCatalogInflight) return clientCatalogInflight.promise
      return
    }

    listPending.value = true
    error.value = null

    const request = (async () => {
      try {
        // Home needs only enough candidates for one full rail (railLimit=7).
        // SSR payload lean cuts HTML transfer/hydration cost without changing UI.
        const limits = mode === 'home'
          // Shell rails (recent/hero) are loaded separately; keep home catalog tiny.
          ? { popularMovies: 12, newestMovies: 0, dubbedMovies: 0, downloadMovies: 0, popularSeries: 8, newestSeries: 0 }
          : { popularMovies: 80, newestMovies: 40, dubbedMovies: 40, downloadMovies: 60, popularSeries: 50, newestSeries: 30 }

        // Popular first so home/rails show playable dubbed+subtitle titles.
        // Newest is merged so freshly imported titles still appear in "تازه‌ها".
        // allSettled: one slow/timeout request must not wipe the whole home layout.
        // Home mode uses a tighter timeout so a hung endpoint cannot stall the UI.
        const requestTimeout = mode === 'home' ? 8_000 : undefined
        const settled = await Promise.allSettled([
          api<ApiListResponse<ApiCatalogItem> | ApiCatalogItem[]>('/movies/', {
            query: { limit: limits.popularMovies, sort: 'popular' },
            ...(requestTimeout ? { timeout: requestTimeout } : {}),
          }),
          limits.newestMovies > 0
            ? api<ApiListResponse<ApiCatalogItem> | ApiCatalogItem[]>('/movies/', {
                query: { limit: limits.newestMovies, sort: 'newest' },
                ...(requestTimeout ? { timeout: requestTimeout } : {}),
              })
            : Promise.resolve(null),
          limits.dubbedMovies > 0
            ? api<ApiListResponse<ApiCatalogItem> | ApiCatalogItem[]>('/movies/', {
                query: { limit: limits.dubbedMovies, availability: 'dubbed', sort: 'popular' },
                ...(requestTimeout ? { timeout: requestTimeout } : {}),
              })
            : Promise.resolve(null),
          limits.downloadMovies > 0
            ? api<ApiListResponse<ApiCatalogItem> | ApiCatalogItem[]>('/movies/', {
                query: { limit: limits.downloadMovies, availability: 'download' },
                ...(requestTimeout ? { timeout: requestTimeout } : {}),
              })
            : Promise.resolve(null),
          api<ApiListResponse<ApiCatalogItem> | ApiCatalogItem[]>('/series/', {
            query: { limit: limits.popularSeries, sort: 'popular' },
            ...(requestTimeout ? { timeout: requestTimeout } : {}),
          }),
          limits.newestSeries > 0
            ? api<ApiListResponse<ApiCatalogItem> | ApiCatalogItem[]>('/series/', {
                query: { limit: limits.newestSeries, sort: 'newest' },
                ...(requestTimeout ? { timeout: requestTimeout } : {}),
              })
            : Promise.resolve(null),
          api<ApiGenre[]>('/genres/', requestTimeout ? { timeout: requestTimeout } : {}),
        ])

        function settledValue<T>(index: number): T | null {
          const result = settled[index]
          return result?.status === 'fulfilled' ? (result.value as T) : null
        }

        const popularMovies = settledValue<ApiListResponse<ApiCatalogItem> | ApiCatalogItem[]>(0)
        const newestMovies = settledValue<ApiListResponse<ApiCatalogItem> | ApiCatalogItem[] | null>(1)
        const dubbedMovies = settledValue<ApiListResponse<ApiCatalogItem> | ApiCatalogItem[] | null>(2)
        const downloadMovies = settledValue<ApiListResponse<ApiCatalogItem> | ApiCatalogItem[] | null>(3)
        const popularSeries = settledValue<ApiListResponse<ApiCatalogItem> | ApiCatalogItem[]>(4)
        const newestSeries = settledValue<ApiListResponse<ApiCatalogItem> | ApiCatalogItem[] | null>(5)
        const genreResponse = settledValue<ApiGenre[]>(6)

        const coreFailed = !popularMovies && !newestMovies && !popularSeries && !newestSeries
        if (coreFailed) {
          const firstReject = settled.find(result => result.status === 'rejected') as PromiseRejectedResult | undefined
          throw (firstReject?.reason instanceof Error
            ? firstReject.reason
            : new Error('Catalog API is unavailable'))
        }
        if (settled.some(result => result.status === 'rejected') && import.meta.dev) {
          console.warn('[catalog] partial load — some rails timed out')
        }
        const mediaBase = String(config.public.mediaCdnBaseUrl)
        const adapt = mode === 'home' ? adaptApiCatalogListItem : adaptApiCatalogItem
        const mergeByKey = (items: Movie[]) => {
          const map = new Map<string, Movie>()
          for (const item of items) {
            const key = `${item.type}:${item.id}`
            const prev = map.get(key)
            // Prefer the copy that already has playback/download metadata.
            if (!prev || (!prev.has_downloads && item.has_downloads) || ((item.download_links?.length || 0) > (prev.download_links?.length || 0))) {
              map.set(key, item)
            }
          }
          return [...map.values()]
        }
        const popularMovieItems = unwrapApiList(popularMovies || []).map(item => adapt(item, 'movie', mediaBase))
        const newestMovieItems = unwrapApiList(newestMovies || []).map(item => adapt(item, 'movie', mediaBase))
        const dubbedMovieItems = unwrapApiList(dubbedMovies || []).map(item => adapt(item, 'movie', mediaBase))
        const downloadMovieItems = unwrapApiList(downloadMovies || []).map(item => adapt(item, 'movie', mediaBase))
        const popularSeriesItems = unwrapApiList(popularSeries || []).map(item => adapt(item, 'series', mediaBase))
        const newestSeriesItems = unwrapApiList(newestSeries || []).map(item => adapt(item, 'series', mediaBase))
        const movies = mergeByKey([
          ...popularMovieItems,
          ...newestMovieItems,
          ...dubbedMovieItems,
          ...downloadMovieItems,
        ])
        const series = mergeByKey([
          ...popularSeriesItems,
          ...newestSeriesItems,
        ])
        catalogState.value = [...movies, ...series]
        recentlyAddedState.value = mergeByKey([
          ...newestMovieItems,
          ...newestSeriesItems,
        ]).sort((left, right) =>
          newestTimestamp(right) - newestTimestamp(left) || right.year - left.year,
        )
        if (genreResponse?.length) {
          genreState.value = mergeCatalogGenres(genreResponse.map(adaptApiGenre))
        }
        source.value = 'api'
        listLoaded.value = true
        listLoadedAt.value = Date.now()
        if (mode === 'full' || listCoverage.value !== 'full') listCoverage.value = mode
      } catch (cause) {
        // Stale-while-revalidate: keep existing catalog on transient failures.
        if (!catalogState.value.length) {
          source.value = 'empty'
          listLoaded.value = false
          listLoadedAt.value = 0
        }
        error.value = cause instanceof Error ? cause.message : 'Catalog API is unavailable'
      } finally {
        listPending.value = false
        if (import.meta.client && clientCatalogInflight?.promise === request) clientCatalogInflight = null
      }
    })()

    if (import.meta.client) clientCatalogInflight = { mode, promise: request }
    return request
  }

  async function loadItemFromApi(slug: string, type: ContentType, options: { softsubPoll?: boolean } = {}) {
    detailRequests.value += 1
    error.value = null
    try {
      const query = options.softsubPoll ? '?softsub_poll=1' : ''
      const item = await api<ApiCatalogItem>(
        `/${type === 'movie' ? 'movies' : 'series'}/${encodeURIComponent(slug)}/${query}`,
        options.softsubPoll
          ? { headers: { 'Cache-Control': 'no-cache', Pragma: 'no-cache' } }
          : {},
      )
      const adapted = adaptApiCatalogItem(item, type, String(config.public.mediaCdnBaseUrl))
      const existingIndex = catalogState.value.findIndex(candidate => candidate.slug === slug && candidate.type === type)
      if (existingIndex === -1) catalogState.value = [...catalogState.value, adapted]
      else catalogState.value = catalogState.value.map((candidate, index) => index === existingIndex ? adapted : candidate)
      source.value = 'api'
      return adapted
    } catch (cause) {
      error.value = cause instanceof Error ? cause.message : 'Catalog detail API is unavailable'
      return null
    } finally {
      detailRequests.value = Math.max(0, detailRequests.value - 1)
    }
  }

  return {
    catalog,
    recentlyAdded,
    genres,
    source: readonly(source),
    pending,
    error: readonly(error),
    loadFromApi,
    loadItemFromApi,
    invalidateCatalog,
  }
}

export function useMovies(limit?: number) {
  const { catalog, pending, error } = useCatalog()
  const movies = computed(() => {
    const items = catalog.value.filter(item => item.type === 'movie')
    return typeof limit === 'number' ? items.slice(0, limit) : items
  })
  return { data: movies, movies, pending, error }
}

export function useSeries(limit?: number) {
  const { catalog, pending, error } = useCatalog()
  const series = computed(() => {
    const items = catalog.value.filter(item => item.type === 'series')
    return typeof limit === 'number' ? items.slice(0, limit) : items
  })
  return { data: series, series, pending, error }
}

export function useTrending(limit = 8) {
  const { catalog, pending, error } = useCatalog()
  const data = computed(() => ({
    movies: catalog.value.filter(item => item.type === 'movie' && item.is_trending).slice(0, limit),
    series: catalog.value.filter(item => item.type === 'series' && item.is_trending).slice(0, limit),
  }))
  return { data, pending, error }
}

export function useMovieBySlug(slug: MaybeRefOrGetter<string>, expectedType?: ContentType) {
  const { catalog, pending, error, loadItemFromApi } = useCatalog()
  const movie = computed(() => catalog.value.find(item => item.slug === toValue(slug) && (!expectedType || item.type === expectedType)) ?? null)
  const refresh = () => expectedType ? loadItemFromApi(toValue(slug), expectedType) : Promise.resolve(movie.value)
  return { data: movie, movie, pending, error, refresh }
}

/**
 * Search adapter consumed by discovery UI. Ranks local catalog by relevance
 * (exact → prefix → contains → similar titles) for precise + fuzzy results.
 */
export function useSearch(filters: MaybeRefOrGetter<CatalogFilters>) {
  const { catalog, pending, error } = useCatalog()
  const normalizedQuery = computed(() => normalizeSearchText(toValue(filters).query))
  const results = computed(() => {
    const active = toValue(filters)
    const query = normalizeSearchText(active.query)

    let pool = catalog.value.filter(item => !active.type || item.type === active.type)

    pool = pool
      .filter(item => !active.genre || item.genres.some(genre => genre.slug === active.genre))
      .filter(item => active.year === 'all' || item.year === Number(active.year))
      .filter(item => active.ageRating === 'all' || item.age_rating === active.ageRating)
      .filter(item => active.country === 'all' || (() => {
        const code = countryCodeForName(active.country)
        const label = localizeCountry(active.country, code)
        return item.country.includes(label)
          || item.country.includes(active.country)
          || (code ? item.country.includes(localizeCountry('', code)) : false)
      })())
      .filter(item => active.language === 'all' || item.language.includes(active.language))
      .filter((item) => {
        if (active.availability === 'all') return true
        if (active.availability === 'dubbed') return item.is_dubbed
        if (active.availability === 'subtitle') return item.has_subtitle
        if (active.availability === 'download') return Boolean(item.has_downloads)
        return true
      })
      .filter(item => active.format === 'all' || item.format === active.format)
      .filter(item => active.minRating === 'all' || item.rating >= Number(active.minRating))

    if (query) {
      const ranked = rankCatalogSearch(pool, query, { limit: pool.length, includeSimilar: true })
      // Keep a soft floor so very weak fuzzy noise does not flood discovery.
      const strong = ranked.filter(hit => hit.score >= 240)
      pool = (strong.length ? strong : ranked).map(hit => hit.item)
    }

    if (!query) {
      return [...pool].sort((a, b) => {
        if (active.sort === 'rating') return b.rating - a.rating
        if (active.sort === 'popular') return popularScore(b) - popularScore(a) || b.popularity - a.popularity
        if (active.sort === 'trending') return trendingScore(b) - trendingScore(a) || b.popularity - a.popularity
        if (active.sort === 'featured') return featuredScore(b) - featuredScore(a) || b.popularity - a.popularity
        return newestTimestamp(b) - newestTimestamp(a) || b.year - a.year
      })
    }

    if (active.sort === 'rating') {
      return [...pool].sort((a, b) => b.rating - a.rating || (scoreCatalogItem(b, query)?.score || 0) - (scoreCatalogItem(a, query)?.score || 0))
    }
    if (active.sort === 'popular') {
      return [...pool].sort((a, b) => popularScore(b) - popularScore(a) || b.popularity - a.popularity)
    }
    if (active.sort === 'trending') {
      return [...pool].sort((a, b) => trendingScore(b) - trendingScore(a) || b.popularity - a.popularity)
    }
    if (active.sort === 'featured') {
      return [...pool].sort((a, b) => featuredScore(b) - featuredScore(a) || b.popularity - a.popularity)
    }
    // Default for queried discovery: relevance order already applied.
    return pool
  })

  return {
    results,
    total: computed(() => results.value.length),
    normalizedQuery: readonly(normalizedQuery),
    pending,
    error,
    engine: 'local' as const,
  }
}

/** @deprecated Prefer useSearch().results for new discovery surfaces. */
export function useFilteredMovies(filters: MaybeRefOrGetter<CatalogFilters>) {
  return useSearch(filters).results
}

// Broad genres describe thousands of titles; sharing only them is weak evidence.
const BROAD_GENRES = new Set(['drama', 'comedy', 'romance', 'thriller'])

function titleTokens(value: string | undefined): Set<string> {
  const normalized = (value || '').toLowerCase().replace(/[^a-z0-9]+/g, ' ')
  return new Set(normalized.split(' ').filter(token => token.length >= 3))
}

function heuristicRelated(item: Movie, catalog: Movie[], limit: number): Movie[] {
  // SSR-safe fallback + instant rail. Mirrors the backend _similarity signals
  // (specific-genre overlap, weighted cast, shared director, franchise title
  // tokens, year/country proximity) so the rail is relevant even before the
  // server-computed payload arrives. The backend row wins once it loads.
  const genreSlugs = [...new Set(item.genres.map(genre => genre.slug))]
  const sourceSpecific = genreSlugs.filter(slug => !BROAD_GENRES.has(slug))
  const castNames = item.cast.map(member => member.name)
  const directorNames = new Set(
    item.crew.filter(member => member.job === 'کارگردان').map(member => member.name),
  )
  const sourceTokens = titleTokens(item.original_title || item.title)
  const year = item.year

  const score = (candidate: Movie): number => {
    let value = 0
    // Specific shared genres (action, horror, western...) outweigh broad ones.
    const shared = candidate.genres
      .map(genre => genre.slug)
      .filter(slug => genreSlugs.includes(slug))
    const sharedSpecific = shared.filter(slug => !BROAD_GENRES.has(slug))
    if (sharedSpecific.length) value += sharedSpecific.length * 5
    if (shared.length) value += shared.length * 2.5
    // Missing the source's dominant (most specific) genre halves the genre score.
    if (sourceSpecific.length && !shared.includes(sourceSpecific[0])) value *= 0.55

    // Shared top-billed cast is strong; earlier seats count more.
    const sharedCast = candidate.cast.filter(member => castNames.includes(member.name)).length
    if (sharedCast) value += sharedCast * 4
    if (directorNames.size && candidate.crew.some(member => directorNames.has(member.name))) {
      value += 5
    }
    // Franchise: same original-title tokens (e.g. Scream / Scream 7).
    const sharedTokens = [...titleTokens(candidate.original_title || candidate.title)].filter(
      token => sourceTokens.has(token),
    )
    if (sharedTokens.length) value += sharedTokens.length * 3
    if (year && Math.abs((candidate.year as number) - year) <= 1) value += 2
    if (candidate.country && candidate.country === item.country) value += 1
    return value
  }

  const strong = catalog
    .filter(candidate => candidate.id !== item.id && candidate.type === item.type)
    .map(candidate => ({ candidate, value: score(candidate) }))
    .filter(entry => entry.value >= 3)
    .sort((a, b) => b.value - a.value || b.candidate.rating - a.candidate.rating)
    .map(entry => entry.candidate)

  // Every detail page shows a full rail (mirrors the backend guarantee). For
  // signal-weak titles (no genres/cast/director) nothing scores above the
  // threshold, so fill from the same-type pool ranked by rating/popularity.
  if (strong.length >= limit) return strong.slice(0, limit)
  const strongPks = new Set(strong.map(candidate => candidate.id))
  const fill = catalog
    .filter(candidate => candidate.type === item.type
      && candidate.id !== item.id
      && !strongPks.has(candidate.id))
    .slice()
    .sort((a, b) => (b.rating - a.rating) || (b.popularity - a.popularity) || (b.id - a.id))
    .slice(0, limit - strong.length)
  return [...strong, ...fill]
}

export function useRelatedMovies(item: MaybeRefOrGetter<Movie | null>, limit = 6) {
  const { catalog } = useCatalog()
  const { api } = useApi()
  const config = useRuntimeConfig()
  const related = ref<Movie[]>([])
  const mediaBase = String(config.public.mediaCdnBaseUrl)

  // Render immediately with the local heuristic so the tab/rail never flashes.
  watch(
    () => toValue(item),
    (current) => {
      related.value = current ? heuristicRelated(current, catalog.value, limit) : []
    },
    { immediate: true },
  )

  // Then upgrade to the server-computed similarity (director/cast-aware) once
  // it returns. Fall back to the heuristic value on error or empty payload.
  // Client-only (like loadReviews): SSR renders the heuristic rail and never
  // waits on an extra API round-trip.
  if (import.meta.client) {
    watch(
      () => toValue(item),
      async (current) => {
        if (!current) return
        try {
          const data = await api<ApiListResponse<ApiCatalogItem> | ApiCatalogItem[]>(
            `/${current.type}/${current.slug}/similar/`,
            { query: { limit } },
          )
          const items = unwrapApiList(data)
            .map(entry => adaptApiCatalogListItem(entry, current.type, mediaBase))
            .filter(entry => entry.id !== current.id)
          if (items.length) related.value = items.slice(0, limit)
        } catch {
          // Keep the heuristic rail; the similar endpoint is an enhancement.
        }
      },
      { immediate: true },
    )
  }

  return computed(() => related.value)
}
