import type { Genre } from '~/types'

/**
 * Canonical Persian genre taxonomy shared by discovery UI and API adapters.
 * Stable local IDs keep SSR hydration deterministic before API genres load.
 */
export const catalogGenres: Genre[] = [
  { id: 1, title: 'درام', slug: 'drama', icon: 'genre-drama' },
  { id: 2, title: 'علمی‌تخیلی', slug: 'sci-fi', icon: 'genre-sci-fi' },
  { id: 3, title: 'جنایی', slug: 'crime', icon: 'genre-crime' },
  { id: 4, title: 'ماجراجویی', slug: 'adventure', icon: 'genre-adventure' },
  { id: 5, title: 'معمایی', slug: 'mystery', icon: 'genre-mystery' },
  { id: 6, title: 'عاشقانه', slug: 'romance', icon: 'genre-romance' },
  { id: 7, title: 'اکشن', slug: 'action', icon: 'genre-action' },
  { id: 8, title: 'فانتزی', slug: 'fantasy', icon: 'genre-fantasy' },
  { id: 9, title: 'کمدی', slug: 'comedy', icon: 'genre-comedy' },
  { id: 10, title: 'ترسناک', slug: 'horror', icon: 'genre-horror' },
  { id: 11, title: 'خانوادگی', slug: 'family', icon: 'genre-family' },
  { id: 12, title: 'انیمیشن', slug: 'animation', icon: 'genre-animation' },
  { id: 13, title: 'دلهره‌آور', slug: 'thriller', icon: 'genre-thriller' },
  { id: 14, title: 'مستند', slug: 'documentary', icon: 'genre-documentary' },
  { id: 15, title: 'زندگی‌نامه‌ای', slug: 'biography', icon: 'genre-biography' },
  { id: 16, title: 'تاریخی', slug: 'history', icon: 'genre-history' },
  { id: 17, title: 'جنگی', slug: 'war', icon: 'genre-war' },
  { id: 18, title: 'وسترن', slug: 'western', icon: 'genre-western' },
  { id: 19, title: 'موسیقی', slug: 'music', icon: 'genre-music' },
  { id: 20, title: 'موزیکال', slug: 'musical', icon: 'genre-musical' },
  { id: 21, title: 'ورزشی', slug: 'sport', icon: 'genre-sport' },
  { id: 22, title: 'ابرقهرمانی', slug: 'superhero', icon: 'genre-superhero' },
  { id: 23, title: 'انیمه', slug: 'anime', icon: 'genre-anime' },
  { id: 24, title: 'روان‌شناختی', slug: 'psychological', icon: 'genre-psychological' },
  { id: 25, title: 'سیاسی', slug: 'political', icon: 'genre-political' },
  { id: 26, title: 'فاجعه‌ای', slug: 'disaster', icon: 'genre-disaster' },
  { id: 27, title: 'دادگاهی', slug: 'legal', icon: 'genre-legal' },
  { id: 28, title: 'کودک', slug: 'kids', icon: 'genre-kids' },
  { id: 29, title: 'رئالیتی‌شو', slug: 'reality-tv', icon: 'genre-reality-tv' },
  { id: 30, title: 'نوآر', slug: 'film-noir', icon: 'genre-film-noir' },
  { id: 31, title: 'فیلم تلویزیونی', slug: 'tv-movie', icon: 'genre-tv-movie' },
]

const catalogGenreBySlug = new Map(catalogGenres.map(genre => [genre.slug, genre]))

export function getCatalogGenre(slug: string) {
  return catalogGenreBySlug.get(slug)
}

/** Keep the complete local taxonomy while adopting IDs for genres returned by the API. */
export function mergeCatalogGenres(apiGenres: Genre[]) {
  const apiBySlug = new Map(apiGenres.map(genre => [genre.slug, genre]))
  const canonical = catalogGenres.map((genre) => {
    const apiGenre = apiBySlug.get(genre.slug)
    if (!apiGenre) return genre
    return {
      ...genre,
      id: apiGenre.id,
      is_featured: Boolean(apiGenre.is_featured),
      movie_count: apiGenre.movie_count,
      series_count: apiGenre.series_count,
      title_count: apiGenre.title_count,
    }
  })
  const custom = apiGenres
    .filter(genre => !catalogGenreBySlug.has(genre.slug))
    .map(genre => ({
      ...genre,
      icon: (genre.icon || 'film') as Genre['icon'],
      is_featured: Boolean(genre.is_featured),
      movie_count: genre.movie_count,
      series_count: genre.series_count,
      title_count: genre.title_count,
    }))
  const merged = [...canonical, ...custom]
  merged.sort((a, b) => {
    const featuredDelta = Number(Boolean(b.is_featured)) - Number(Boolean(a.is_featured))
    if (featuredDelta) return featuredDelta
    const countDelta = Number(b.title_count || 0) - Number(a.title_count || 0)
    if (countDelta) return countDelta
    const aCanon = catalogGenreBySlug.has(a.slug) ? 0 : 1
    const bCanon = catalogGenreBySlug.has(b.slug) ? 0 : 1
    if (aCanon !== bCanon) return aCanon - bCanon
    return a.title.localeCompare(b.title, 'fa')
  })
  return merged
}
