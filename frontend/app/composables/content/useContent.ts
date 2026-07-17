import type { AgeRating, ContentType, Movie } from '~/types'
import { mockCatalog, mockGenres } from '~/data/mockCatalog'
import { mergeCatalogGenres } from '~/data/genres'
import { adaptApiCatalogItem, adaptApiGenre, unwrapApiList } from '~/data/catalogAdapter'
import type { ApiCatalogItem, ApiGenre, ApiListResponse } from '~/data/catalogAdapter'

export type CatalogSort = 'newest' | 'rating' | 'popular' | 'trending'

export interface CatalogFilters {
  query: string
  genre: string
  year: string
  ageRating: AgeRating | 'all'
  country: string
  language: string
  availability: 'all' | 'dubbed' | 'subtitle'
  format: 'all' | 'animation' | 'short' | 'live_action'
  minRating: string
  sort: CatalogSort
  type?: ContentType
}

export function useCatalog() {
  const config = useRuntimeConfig()
  const { api } = useApi()
  const catalogState = useState<Movie[]>('mock-catalog', () => mockCatalog)
  const genreState = useState('catalog-genres', () => [...mockGenres])
  const source = useState<'mock' | 'api'>('catalog-source', () => 'mock')
  const listLoaded = useState('catalog-list-loaded', () => false)
  const pending = useState('catalog-pending', () => false)
  const error = useState<Error | null>('catalog-error', () => null)
  const catalog = computed(() => catalogState.value)

  async function loadFromApi() {
    if (pending.value) return
    pending.value = true
    error.value = null
    try {
      const [movieResponse, seriesResponse, genreResponse] = await Promise.all([
        api<ApiListResponse<ApiCatalogItem> | ApiCatalogItem[]>('/movies/', { query: { limit: 100 } }),
        api<ApiListResponse<ApiCatalogItem> | ApiCatalogItem[]>('/series/', { query: { limit: 100 } }),
        api<ApiGenre[]>('/genres/').catch(() => null),
      ])
      const mediaBase = String(config.public.mediaCdnBaseUrl)
      const movies = unwrapApiList(movieResponse).map(item => adaptApiCatalogItem(item, 'movie', mediaBase))
      const series = unwrapApiList(seriesResponse).map(item => adaptApiCatalogItem(item, 'series', mediaBase))
      const apiCatalog = [...movies, ...series]
      if (!apiCatalog.length) throw new Error('Catalog API returned no published content')
      catalogState.value = apiCatalog
      if (genreResponse?.length) {
        genreState.value.splice(
          0,
          genreState.value.length,
          ...mergeCatalogGenres(genreResponse.map(adaptApiGenre)),
        )
      }
      source.value = 'api'
      listLoaded.value = true
    } catch (cause) {
      catalogState.value = mockCatalog
      source.value = 'mock'
      error.value = cause instanceof Error ? cause : new Error('Catalog API is unavailable')
    } finally {
      pending.value = false
    }
  }

  async function loadItemFromApi(slug: string, type: ContentType) {
    if (pending.value) return null
    pending.value = true
    error.value = null
    try {
      const item = await api<ApiCatalogItem>(`/${type === 'movie' ? 'movies' : 'series'}/${encodeURIComponent(slug)}/`)
      const adapted = adaptApiCatalogItem(item, type, String(config.public.mediaCdnBaseUrl))
      const existingIndex = catalogState.value.findIndex(candidate => candidate.slug === slug && candidate.type === type)
      if (existingIndex === -1) catalogState.value = [...catalogState.value, adapted]
      else catalogState.value = catalogState.value.map((candidate, index) => index === existingIndex ? adapted : candidate)
      source.value = 'api'
      return adapted
    } catch (cause) {
      error.value = cause instanceof Error ? cause : new Error('Catalog detail API is unavailable')
      return null
    } finally {
      pending.value = false
    }
  }

  function resetToMock() {
    catalogState.value = mockCatalog
    genreState.value.splice(0, genreState.value.length, ...mockGenres)
    source.value = 'mock'
    listLoaded.value = false
    error.value = null
  }

  if (import.meta.client && config.public.catalogSource === 'api' && !listLoaded.value) {
    onNuxtReady(() => { void loadFromApi() })
  }

  return {
    catalog,
    genres: genreState.value,
    source: readonly(source),
    pending: readonly(pending),
    error: readonly(error),
    loadFromApi,
    loadItemFromApi,
    resetToMock,
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

function normalizeSearchText(value: string) {
  return value
    .normalize('NFKC')
    .replace(/[يى]/g, 'ی')
    .replace(/ك/g, 'ک')
    .replace(/[\u064B-\u065F\u0670]/g, '')
    .replace(/[\u200C\u200D]/g, ' ')
    .toLocaleLowerCase('fa')
    .replace(/\s+/g, ' ')
    .trim()
}

/**
 * Search adapter consumed by discovery UI. It currently ranks local catalog
 * data, while keeping a stable result contract for a future Meilisearch API.
 */
export function useSearch(filters: MaybeRefOrGetter<CatalogFilters>) {
  const { catalog, pending, error } = useCatalog()
  const normalizedQuery = computed(() => normalizeSearchText(toValue(filters).query))
  const results = computed(() => {
    const active = toValue(filters)
    const queryTokens = normalizeSearchText(active.query).split(' ').filter(Boolean)
    return catalog.value
      .filter(item => !active.type || item.type === active.type)
      .filter((item) => {
        if (!queryTokens.length) return true
        const searchableText = normalizeSearchText([
          item.title,
          item.original_title,
          item.description,
          item.director,
          item.country,
          item.language,
          item.type === 'movie' ? 'فیلم سینمایی' : 'سریال',
          item.format === 'animation' ? 'انیمیشن خانوادگی' : item.format === 'short' ? 'فیلم کوتاه سبک' : 'لایو اکشن',
          item.is_dubbed ? 'دوبله فارسی' : '',
          item.has_subtitle ? 'زیرنویس فارسی' : '',
          item.cast.map(person => `${person.name} ${person.role}`).join(' '),
          item.genres.map(genre => genre.title).join(' '),
        ].join(' '))
        return queryTokens.every(token => searchableText.includes(token))
      })
      .filter(item => !active.genre || item.genres.some(genre => genre.slug === active.genre))
      .filter(item => active.year === 'all' || item.year === Number(active.year))
      .filter(item => active.ageRating === 'all' || item.age_rating === active.ageRating)
      .filter(item => active.country === 'all' || item.country.includes(active.country))
      .filter(item => active.language === 'all' || item.language.includes(active.language))
      .filter(item => active.availability === 'all' || (active.availability === 'dubbed' ? item.is_dubbed : item.has_subtitle))
      .filter(item => active.format === 'all' || item.format === active.format)
      .filter(item => active.minRating === 'all' || item.rating >= Number(active.minRating))
      .sort((a, b) => {
        if (active.sort === 'rating') return b.rating - a.rating
        if (active.sort === 'popular') return b.popularity - a.popularity
        if (active.sort === 'trending') return Number(b.is_trending) - Number(a.is_trending) || b.popularity - a.popularity
        return b.year - a.year
      })
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

export function useRelatedMovies(item: MaybeRefOrGetter<Movie | null>, limit = 6) {
  const { catalog } = useCatalog()
  return computed(() => {
    const current = toValue(item)
    if (!current) return []
    const genreSlugs = new Set(current.genres.map(genre => genre.slug))
    return catalog.value
      .filter(candidate => candidate.id !== current.id && candidate.type === current.type)
      .sort((a, b) => {
        const scoreA = a.genres.filter(genre => genreSlugs.has(genre.slug)).length
        const scoreB = b.genres.filter(genre => genreSlugs.has(genre.slug)).length
        return scoreB - scoreA || b.rating - a.rating
      })
      .slice(0, limit)
  })
}
