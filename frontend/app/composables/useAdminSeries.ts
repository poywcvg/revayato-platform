import type {
  AdminSeries,
  AdminSeriesFilters,
  AdminSeriesListResponse,
  TMDBImportResponse,
} from '~/types'

export function useAdminSeries() {
  const { api } = useApi()
  const { genres, countries, bumpPublicCatalog } = useAdminCatalogMeta()

  function list(filters: AdminSeriesFilters) {
    return api<AdminSeriesListResponse>('/admin/series/', {
      query: {
        q: filters.q || undefined,
        status: filters.status || undefined,
        source: filters.source || undefined,
        genre: filters.genre || undefined,
        year: filters.year || undefined,
        ordering: filters.ordering,
        limit: filters.limit,
        offset: filters.offset,
      },
    })
  }

  function detail(id: number) {
    return api<AdminSeries>(`/admin/series/${id}/`)
  }

  async function create(payload: FormData | Record<string, unknown>) {
    const saved = await api<AdminSeries>('/admin/series/', { method: 'POST', body: payload })
    bumpPublicCatalog()
    return saved
  }

  async function update(id: number, payload: FormData | Record<string, unknown>) {
    const saved = await api<AdminSeries>(`/admin/series/${id}/`, { method: 'PATCH', body: payload })
    bumpPublicCatalog()
    return saved
  }

  async function archive(id: number) {
    const saved = await api<{ id: number; is_published: false; archived: boolean }>(`/admin/series/${id}/`, { method: 'DELETE' })
    bumpPublicCatalog()
    return saved
  }

  async function setPublished(id: number, is_published: boolean) {
    const saved = await api<AdminSeries>(`/admin/series/${id}/`, {
      method: 'PATCH',
      body: { is_published },
    })
    bumpPublicCatalog()
    return saved
  }

  async function sync(id: number, options: { dry_run?: boolean; overwrite_manual?: boolean } = {}) {
    const result = await api<TMDBImportResponse>(`/admin/series/${id}/sync-tmdb/`, {
      method: 'POST',
      body: options,
      timeout: 60_000,
    })
    if (!options.dry_run) bumpPublicCatalog()
    return result
  }

  async function crawlProviderDownloads(id: number, payload: { page_url?: string; replace?: boolean } = {}) {
    const result = await api<{
      imported_count: number
      has_subtitle: boolean
      is_dubbed: boolean
      series: AdminSeries
    }>(`/admin/catalog/series/${id}/provider-crawl-downloads/`, {
      method: 'POST',
      body: payload,
      timeout: 90_000,
    })
    bumpPublicCatalog()
    return result
  }

  return {
    list,
    detail,
    create,
    update,
    archive,
    setPublished,
    genres,
    countries,
    sync,
    crawlProviderDownloads,
    bumpPublicCatalog,
  }
}
