/** Normalized external and site rating types for movies and series. */

export type RatingSource =
  | 'imdb'
  | 'tmdb'
  | 'rottentomatoes'
  | 'metacritic'
  | 'thetvdb'
  | 'trakt'
  | 'site'

export type RatingCriticType = 'critics' | 'audience' | 'users'

export interface MediaRating {
  source: RatingSource
  value: number
  scale: 5 | 10 | 100
  displayValue: string
  voteCount?: number
  url?: string
  updatedAt?: string
  criticType?: RatingCriticType
  isVerified: boolean
}

export interface MediaRatingsPayload {
  ratings: MediaRating[]
  fetchedAt?: string
}
