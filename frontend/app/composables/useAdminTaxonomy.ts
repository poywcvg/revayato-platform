import type {
  TaxonomyEntity,
  TaxonomyItemMap,
  TaxonomyListResponse,
} from '~/types'

const ENDPOINTS: Record<TaxonomyEntity, string> = {
  genres: '/admin/genres/',
  countries: '/admin/countries/',
  tags: '/admin/tags/',
  actors: '/admin/actors/',
  directors: '/admin/directors/',
}

/**
 * Staff CRUD surface for catalog taxonomy (genres, countries, tags, actors, directors).
 * Mirrors the backend generic list/create + detail views in
 * `apps/catalog/taxonomy_api.py` (limit/offset pagination, `q` search, ordering).
 */
export function useAdminTaxonomy() {
  const { api } = useApi()

  function endpoint(entity: TaxonomyEntity, id?: number) {
    return id == null ? ENDPOINTS[entity] : `${ENDPOINTS[entity]}${id}/`
  }

  async function list<T extends TaxonomyEntity>(
    entity: T,
    filters: { q?: string; ordering?: string; limit?: number; offset?: number } = {},
  ): Promise<TaxonomyListResponse<TaxonomyItemMap[T]>> {
    return api<TaxonomyListResponse<TaxonomyItemMap[T]>>(endpoint(entity), {
      query: {
        q: filters.q || undefined,
        ordering: filters.ordering || undefined,
        limit: filters.limit ?? 20,
        offset: filters.offset ?? 0,
      },
    })
  }

  function create(entity: TaxonomyEntity, payload: Record<string, unknown> | FormData) {
    return api<TaxonomyItemMap[TaxonomyEntity]>(endpoint(entity), { method: 'POST', body: payload })
  }

  function update(entity: TaxonomyEntity, id: number, payload: Record<string, unknown> | FormData) {
    return api<TaxonomyItemMap[TaxonomyEntity]>(endpoint(entity, id), { method: 'PATCH', body: payload })
  }

  function remove(entity: TaxonomyEntity, id: number) {
    return api<null>(endpoint(entity, id), { method: 'DELETE' })
  }

  /** Lightweight options fetch for pickers elsewhere in the admin. */
  async function options(entity: TaxonomyEntity): Promise<Array<{ id: number, label: string }>> {
    const response = await list(entity, { limit: 100, ordering: entity === 'genres' ? 'title' : 'name' })
    const rows = response.results as unknown as Array<Record<string, unknown>>
    return rows.map(row => ({
      id: Number(row.id),
      label: String(row.title ?? row.name ?? row.slug ?? row.id),
    }))
  }

  return { list, create, update, remove, options }
}
