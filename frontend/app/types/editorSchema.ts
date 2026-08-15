import type {
  AdminCountry,
  AdminGenre,
  AdminMovie,
  AdminSeries,
  TMDBImportResponse,
} from '~/types'

/**
 * Schema for the shared content editor (movies + series).
 *
 * A per-content-type config describes the form sections and the field specs
 * that drive a single `AdminContentEditor` component, eliminating the ~450
 * lines of duplicated logic between the legacy movie/series editors.
 */

export type AdminEditorFieldType =
  | 'text'
  | 'textarea'
  | 'number'
  | 'date'
  | 'select'
  | 'checkbox'
  | 'radio-cards'
  | 'genres-picker'
  | 'countries-picker'
  | 'availability-indicators'
  | 'url'
  | 'tmdb-id'
  | 'imdb-id'
  | 'image-upload'
  | 'download-links'
  | 'crew-display'
  | 'seo'
  | 'f2m-crawl'
  | 'sync-tmdb'
  | 'published-url'
  | 'meta'
  | 'static-hint'

export interface AdminEditorOption {
  value: string
  title: string
  /** Long-form description (radio-cards only). */
  text?: string
}

export interface AdminFieldSpec {
  /** Form key, or `__static__` for non-bound display sections. */
  key: string
  label?: string
  type: AdminEditorFieldType
  required?: boolean
  hint?: string
  dir?: 'ltr' | 'rtl'
  placeholder?: string
  colSpan?: string
  /** For `image-upload`, which image slot this field fills. */
  kind?: 'poster' | 'backdrop'
  options?: AdminEditorOption[]
  /** Optional per-field validator returning an error message or ''. */
  validate?: (form: Record<string, unknown>) => string
}

export interface AdminEditorSection {
  id: string
  label: string
  fields: AdminFieldSpec[]
}

/** Union of the API surface both admin composables expose that the editor needs. */
export interface AdminItemApiLike {
  genres(): Promise<AdminGenre[]>
  countries(): Promise<AdminCountry[]>
  detail(id: number): Promise<AdminMovie | AdminSeries>
  create(payload: FormData | Record<string, unknown>): Promise<AdminMovie | AdminSeries>
  update(id: number, payload: FormData | Record<string, unknown>): Promise<AdminMovie | AdminSeries>
  crawlProviderDownloads(
    id: number,
    options: { page_url?: string; replace?: boolean },
  ): Promise<{ imported_count: number; movie?: AdminMovie; series?: AdminSeries; has_subtitle?: boolean; is_dubbed?: boolean }>
  bumpPublicCatalog(): void
  sync?(id: number, options: { dry_run?: boolean; overwrite_manual?: boolean }): Promise<TMDBImportResponse>
}

export type EditorContentType = 'movie' | 'series'

export interface AdminEditorConfig {
  contentType: EditorContentType
  /** Callback returning the API object — keeps the editor inert until used. */
  api: () => AdminItemApiLike
  listBackHref: string
  newTitle: string
  editTitle: string
  /** Verb used in post-save success copy (e.g. «فیلم», «سریال»). */
  contentNoun: string
  sections: AdminEditorSection[]
  includes: {
    releaseYear: boolean
    duration: boolean
    releaseDate: boolean
    spokenLanguages: boolean
    trailer: boolean
    videoUrl: boolean
    downloadKey: boolean
    tmdbSection: boolean
    syncAvailable: boolean
    seoSection: boolean
    mediaStatus: boolean
    isRecommended: boolean
  }
}
