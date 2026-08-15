import type {
  AdminMovie,
  AdminMovieFilters,
  AdminMovieListResponse,
  CatalogImporterSettings,
  CatalogSyncMode,
  CatalogSyncRun,
  CatalogSyncRunListResponse,
  TMDBImportResponse,
  TMDBPreview,
  TMDBSearchResponse,
} from '~/types'

export function useAdminMovies() {
  const { api } = useApi()
  const { genres, countries, bumpPublicCatalog } = useAdminCatalogMeta()

  function list(filters: AdminMovieFilters) {
    return api<AdminMovieListResponse>('/admin/movies/', {
      query: {
        q: filters.q || undefined,
        status: filters.status || undefined,
        source: filters.source || undefined,
        type: filters.type || undefined,
        genre: filters.genre || undefined,
        year: filters.year || undefined,
        ordering: filters.ordering,
        limit: filters.limit,
        offset: filters.offset,
      },
    })
  }

  function detail(id: number) {
    return api<AdminMovie>(`/admin/movies/${id}/`)
  }

  async function create(payload: FormData | Record<string, unknown>) {
    const saved = await api<AdminMovie>('/admin/movies/', { method: 'POST', body: payload })
    bumpPublicCatalog()
    return saved
  }

  async function update(id: number, payload: FormData | Record<string, unknown>) {
    const saved = await api<AdminMovie>(`/admin/movies/${id}/`, { method: 'PATCH', body: payload })
    bumpPublicCatalog()
    return saved
  }

  async function archive(id: number) {
    const saved = await api<{ id: number; publication_status: 'archived'; archived: boolean }>(`/admin/movies/${id}/`, { method: 'DELETE' })
    bumpPublicCatalog()
    return saved
  }

  async function setPublicationStatus(id: number, publication_status: 'draft' | 'published' | 'archived') {
    const saved = await api<AdminMovie>(`/admin/movies/${id}/`, {
      method: 'PATCH',
      body: { publication_status },
    })
    bumpPublicCatalog()
    return saved
  }

  function tmdbSearch(query: string, page = 1, language = 'fa-IR') {
    return api<TMDBSearchResponse>('/admin/tmdb/search/', {
      query: { query, page, language },
      timeout: 45_000,
    })
  }

  function tmdbPreview(tmdbId: number) {
    return api<TMDBPreview>(`/admin/tmdb/movie/${tmdbId}/preview/`, { timeout: 45_000 })
  }

  function tmdbSeriesPreview(tmdbId: number) {
    return api<TMDBPreview>(`/admin/tmdb/series/${tmdbId}/preview/`, { timeout: 45_000 })
  }

  async function tmdbImport(tmdbId: number, options: { publish?: boolean; overwrite_manual?: boolean; link_movie_id?: number } = {}) {
    const result = await api<TMDBImportResponse>(`/admin/tmdb/movie/${tmdbId}/import/`, {
      method: 'POST',
      body: options,
      timeout: 60_000,
    })
    bumpPublicCatalog()
    return result
  }

  async function tmdbSeriesImport(tmdbId: number) {
    const result = await api<TMDBImportResponse>(`/admin/tmdb/series/${tmdbId}/import/`, {
      method: 'POST',
      timeout: 60_000,
    })
    bumpPublicCatalog()
    return result
  }

  async function sync(id: number, options: { dry_run?: boolean; overwrite_manual?: boolean } = {}) {
    const result = await api<TMDBImportResponse>(`/admin/movies/${id}/sync-tmdb/`, {
      method: 'POST',
      body: options,
      timeout: 60_000,
    })
    if (!options.dry_run) bumpPublicCatalog()
    return result
  }

  function catalogSyncRuns(limit = 10) {
    return api<CatalogSyncRunListResponse>('/admin/catalog-sync/runs/', { query: { limit } })
  }

  function catalogSyncRun(id: number) {
    return api<CatalogSyncRun>(`/admin/catalog-sync/runs/${id}/`)
  }

  async function startCatalogSync(mode: CatalogSyncMode) {
    const run = await api<CatalogSyncRun>('/admin/catalog-sync/runs/', {
      method: 'POST',
      body: { mode, confirm_full: mode === 'full' },
    })
    bumpPublicCatalog()
    return run
  }

  function cancelCatalogSync(id: number) {
    return api<CatalogSyncRun>(`/admin/catalog-sync/runs/${id}/cancel/`, { method: 'POST' })
  }

  function importerSettings() {
    return api<CatalogImporterSettings>('/admin/catalog-sync/settings/')
  }

  function updateImporterSettings(payload: Partial<CatalogImporterSettings>) {
    return api<CatalogImporterSettings>('/admin/catalog-sync/settings/', {
      method: 'PATCH',
      body: payload,
    })
  }

  return {
    list, detail, create, update, archive, setPublicationStatus, genres, countries,
    tmdbSearch, tmdbPreview, tmdbSeriesPreview, tmdbImport, tmdbSeriesImport, sync,
    catalogSyncRuns, catalogSyncRun, startCatalogSync, cancelCatalogSync,
    importerSettings, updateImporterSettings, bumpPublicCatalog,
  }
}
