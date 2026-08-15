import type {
  ProviderImportJob,
  ProviderImportItem,
  ProviderImportLog,
  ProviderSource,
  ProviderValidateResult,
} from '~/types'

export type ProviderJobRequest = {
  content_type?: 'movies' | 'series' | 'both'
  mode?: 'discover_only' | 'import_missing_files' | 'import_selected' | 'sync_all'
  limit?: number
  dry_run?: boolean
  overwrite?: boolean
  quality_preference?: string[]
  max_pages?: number
  publish?: boolean
  create_missing?: boolean
  replace_links?: boolean
}

export function useProviderImport() {
  const { api } = useApi()

  function listSources() {
    return api<{ results: ProviderSource[] }>('/admin/provider-sources/')
  }

  function getSource(id: number) {
    return api<ProviderSource>(`/admin/provider-sources/${id}/`)
  }

  function validateSource(id: number) {
    return api<ProviderValidateResult>(`/admin/provider-sources/${id}/validate/`, {
      method: 'POST',
      timeout: 45_000,
    })
  }

  function discoverMovie(movieId: number, options: { force?: boolean } = {}) {
    return api<ProviderImportJob>(`/admin/catalog/movies/${movieId}/provider-discover/`, {
      method: 'POST',
      body: { mode: 'discover_only', force: Boolean(options.force) },
      timeout: 30_000,
    })
  }

  function discoverSeries(seriesId: number, options: { force?: boolean } = {}) {
    return api<ProviderImportJob>(`/admin/catalog/series/${seriesId}/provider-discover/`, {
      method: 'POST',
      body: { mode: 'discover_only', force: Boolean(options.force) },
      timeout: 30_000,
    })
  }

  function discover(id: number, payload: ProviderJobRequest) {
    return api<ProviderImportJob>(`/admin/provider-sources/${id}/discover/`, {
      method: 'POST',
      body: { mode: 'discover_only', ...payload },
      timeout: 30_000,
    })
  }

  function startImport(id: number, payload: ProviderJobRequest) {
    return api<ProviderImportJob>(`/admin/provider-sources/${id}/import/`, {
      method: 'POST',
      body: { mode: 'import_missing_files', ...payload },
      timeout: 30_000,
    })
  }

  function listJobs() {
    return api<{ results: ProviderImportJob[] }>('/admin/provider-import/jobs/')
  }

  function getJob(id: string) {
    return api<ProviderImportJob>(`/admin/provider-import/jobs/${id}/`)
  }

  function cancelJob(id: string) {
    return api<ProviderImportJob>(`/admin/provider-import/jobs/${id}/cancel/`, { method: 'POST' })
  }

  function approveMatch(jobId: string, candidateId: number) {
    return api<ProviderImportItem>(`/admin/provider-import/jobs/${jobId}/approve-match/`, {
      method: 'POST',
      body: { candidate_id: candidateId },
    })
  }

  function crawlMovieDownloads(movieId: number, payload: { page_url?: string; provider_item_id?: string; replace?: boolean } = {}) {
    return api<{
      imported_count: number
      page_url?: string
      page_path?: string
      download_links: Array<{ label: string; url?: string; quality?: string; size_label?: string }>
      movie: import('~/types').AdminMovie
      code?: string
    }>(`/admin/catalog/movies/${movieId}/provider-crawl-downloads/`, {
      method: 'POST',
      body: payload,
      timeout: 60_000,
    })
  }

  function jobItems(id: string) {
    return api<{ results: ProviderImportItem[] }>(`/admin/provider-import/jobs/${id}/items/`)
  }

  function jobCandidates(id: string) {
    return api<{ results: ProviderImportItem[] }>(`/admin/provider-import/jobs/${id}/candidates/`)
  }

  function jobLogs(id: string) {
    return api<{ results: ProviderImportLog[] }>(`/admin/provider-import/jobs/${id}/logs/`)
  }

  return {
    listSources, getSource, validateSource,
    discoverMovie, discoverSeries, discover, startImport,
    listJobs, getJob, cancelJob, approveMatch, crawlMovieDownloads, jobItems, jobCandidates, jobLogs,
  }
}
