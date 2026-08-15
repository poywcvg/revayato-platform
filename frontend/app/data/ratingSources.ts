import type { RatingSource } from '~/types/ratings'

export interface RatingSourceConfig {
  label: string
  logo: string
  scale: 5 | 10 | 100
  suffix?: string
  wordmark?: boolean
}

export const RATING_SOURCES: Record<RatingSource, RatingSourceConfig> = {
  imdb: {
    label: 'IMDb',
    logo: '/assets/ratings/imdb.svg',
    scale: 10,
    wordmark: true,
  },
  tmdb: {
    label: 'TMDB',
    logo: '/assets/ratings/tmdb.svg',
    scale: 10,
    wordmark: true,
  },
  rottentomatoes: {
    label: 'Rotten Tomatoes',
    logo: '/assets/ratings/rotten-tomatoes.svg',
    scale: 100,
    suffix: '%',
  },
  metacritic: {
    label: 'Metacritic',
    logo: '/assets/ratings/metacritic.svg',
    scale: 100,
    wordmark: true,
  },
  thetvdb: {
    label: 'TheTVDB',
    logo: '/assets/ratings/thetvdb.svg',
    scale: 10,
    wordmark: true,
  },
  trakt: {
    label: 'Trakt',
    logo: '/assets/ratings/trakt.svg',
    scale: 100,
    suffix: '%',
  },
  site: {
    label: 'امتیاز کاربران سایت',
    logo: '/assets/brand/rating-mark.svg',
    scale: 10,
  },
}

export function getRatingSourceConfig(source: RatingSource): RatingSourceConfig {
  return RATING_SOURCES[source]
}
