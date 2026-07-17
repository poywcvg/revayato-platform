import type { AgeRating } from '~/types'
import { getMockContent, mockCatalog } from '~/data/mockCatalog'

/** Compatibility view for older consumers while metadata now lives on Movie. */
export interface MediaMeta {
  ageRating: AgeRating
  isUncensored: boolean
  contentWarnings: string[]
  popularity: number
}

export const mediaMeta: Record<string, MediaMeta> = Object.fromEntries(
  mockCatalog.map(item => [item.slug, {
    ageRating: item.age_rating,
    isUncensored: item.is_uncensored,
    contentWarnings: item.content_warnings,
    popularity: item.popularity,
  }]),
)

export function getMediaMeta(slug: string): MediaMeta {
  const item = getMockContent(slug)
  return item ? mediaMeta[item.slug]! : {
    ageRating: '12+',
    isUncensored: false,
    contentWarnings: [],
    popularity: 0,
  }
}
