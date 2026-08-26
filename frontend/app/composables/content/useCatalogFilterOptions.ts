export interface CatalogFilterCountryOption {
  id: number
  name: string
  code: string
  movie_count: number
  series_count: number
}

export interface CatalogTrendingQuery {
  query: string
  hits: number
}

interface ApiCatalogFiltersResponse {
  years?: number[]
  languages?: string[]
  age_ratings?: string[]
  trending_queries?: CatalogTrendingQuery[]
  countries?: CatalogFilterCountryOption[]
}

const FILTERS_TTL_MS = 15 * 60_000

/**
 * Server-provided filter options (years / languages / countries / age ratings /
 * trending queries) so browse pages never show empty dropdowns on cold visits.
 */
export function useCatalogFilterOptions() {
  const { api } = useApi()
  const optionsState = useState<ApiCatalogFiltersResponse | null>('catalog-filter-options', () => null)
  const loadedAt = useState('catalog-filter-options-at', () => 0)
  const pending = useState('catalog-filter-options-pending', () => false)

  const fresh = computed(() =>
    Boolean(optionsState.value) && Date.now() - loadedAt.value < FILTERS_TTL_MS,
  )

  async function load(force = false) {
    if (!force && fresh.value) return optionsState.value
    if (pending.value) return optionsState.value
    pending.value = true
    try {
      const data = await api<ApiCatalogFiltersResponse>('/catalog/filters/', {
        timeout: 8_000,
      })
      if (data && typeof data === 'object') {
        optionsState.value = data
        loadedAt.value = Date.now()
      }
    } catch {
      // Options are an enhancement; dropdowns fall back to client-derived lists.
    } finally {
      pending.value = false
    }
    return optionsState.value
  }

  const years = computed(() => [...(optionsState.value?.years || [])])
  const languages = computed(() => [...(optionsState.value?.languages || [])])
  const ageRatings = computed(() => [...(optionsState.value?.age_ratings || [])])
  const countries = computed(() => [...(optionsState.value?.countries || [])])
  const trendingQueries = computed(() => [
    ...(optionsState.value?.trending_queries || []),
  ])

  return { load, pending: readonly(pending), years, languages, ageRatings, countries, trendingQueries }
}

const RECENT_SEARCHES_KEY = 'revayato:recent-searches'
const RECENT_SEARCHES_MAX = 6

function readRecentSearches(): string[] {
  try {
    const raw = localStorage.getItem(RECENT_SEARCHES_KEY)
    if (!raw) return []
    const parsed = JSON.parse(raw)
    if (!Array.isArray(parsed)) return []
    return parsed
      .filter((entry): entry is string => typeof entry === 'string')
      .map(entry => entry.trim())
      .filter(Boolean)
      .slice(0, RECENT_SEARCHES_MAX)
  } catch {
    return []
  }
}

/** Client-only recent-search history persisted per browser. */
export function useRecentSearches() {
  const searches = ref<string[]>([])

  onMounted(() => {
    searches.value = readRecentSearches()
  })

  function remember(term: string) {
    const value = term.trim()
    if (value.replace(/\s/g, '').length < 2) return
    const next = [value, ...readRecentSearches().filter(entry => entry !== value)]
      .slice(0, RECENT_SEARCHES_MAX)
    try {
      localStorage.setItem(RECENT_SEARCHES_KEY, JSON.stringify(next))
    } catch { /* storage full/blocked */ }
    searches.value = next
  }

  function forget(term: string) {
    const next = readRecentSearches().filter(entry => entry !== term)
    try {
      localStorage.setItem(RECENT_SEARCHES_KEY, JSON.stringify(next))
    } catch { /* ignore */ }
    searches.value = next
  }

  function clear() {
    try {
      localStorage.removeItem(RECENT_SEARCHES_KEY)
    } catch { /* ignore */ }
    searches.value = []
  }

  return { searches: readonly(searches), remember, forget, clear }
}
