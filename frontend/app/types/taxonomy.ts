/** Staff taxonomy management contracts (`/api/admin/{genres,countries,tags,actors,directors}/`). */

export type TaxonomyEntity = 'genres' | 'countries' | 'tags' | 'actors' | 'directors'

export interface TaxonomyListResponse<T> {
  count: number
  next: string | null
  previous: string | null
  results: T[]
}

export interface TaxonomyGenre {
  id: number
  title: string
  slug: string
  description?: string
  is_featured?: boolean
}

export interface TaxonomyCountry {
  id: number
  name: string
  code?: string
}

export interface TaxonomyTag {
  id: number
  name: string
  slug: string
  is_featured?: boolean
}

interface TaxonomyPersonBase {
  id: number
  name: string
  original_name?: string
  slug: string
  biography?: string
  birth_date?: string | null
  birth_place?: string
  is_featured?: boolean
  popularity?: number | null
  tmdb_id?: number | null
  photo?: string | null
  photo_external_url?: string
}

export type TaxonomyActor = TaxonomyPersonBase
export type TaxonomyDirector = TaxonomyPersonBase

export type TaxonomyItemMap = {
  genres: TaxonomyGenre
  countries: TaxonomyCountry
  tags: TaxonomyTag
  actors: TaxonomyActor
  directors: TaxonomyDirector
}
