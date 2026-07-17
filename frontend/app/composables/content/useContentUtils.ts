import type { Movie } from '~/types'

export function useContentUtils() {
  const getPoster = (item: Movie) => item.poster_url || '/placeholder-poster.svg'
  const getYear = (item: Movie) => item.year
  const getRating = (item: Movie) => item.rating.toFixed(1)
  const getTitle = (item: Movie) => item.title
  const getDescription = (item: Movie) => item.description
  const getSlug = (item: Movie) => item.slug

  return { getPoster, getYear, getRating, getTitle, getDescription, getSlug }
}
