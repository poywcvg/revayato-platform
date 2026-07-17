import type { Genre } from '~/types'

/**
 * Canonical Persian genre taxonomy shared by mock data and API adapters.
 * Stable local IDs keep SSR hydration deterministic when the API is disabled.
 */
export const catalogGenres: Genre[] = [
  { id: 1, title: 'درام', slug: 'drama', icon: 'masks' },
  { id: 2, title: 'علمی‌تخیلی', slug: 'sci-fi', icon: 'rocket' },
  { id: 3, title: 'جنایی', slug: 'crime', icon: 'investigate' },
  { id: 4, title: 'ماجراجویی', slug: 'adventure', icon: 'map' },
  { id: 5, title: 'معمایی', slug: 'mystery', icon: 'puzzle' },
  { id: 6, title: 'عاشقانه', slug: 'romance', icon: 'heart' },
  { id: 7, title: 'اکشن', slug: 'action', icon: 'bolt' },
  { id: 8, title: 'فانتزی', slug: 'fantasy', icon: 'sparkles' },
  { id: 9, title: 'کمدی', slug: 'comedy', icon: 'smile' },
  { id: 10, title: 'ترسناک', slug: 'horror', icon: 'eye' },
  { id: 11, title: 'خانوادگی', slug: 'family', icon: 'users' },
  { id: 12, title: 'انیمیشن', slug: 'animation', icon: 'palette' },
  { id: 13, title: 'دلهره‌آور', slug: 'thriller', icon: 'shield-alert' },
  { id: 14, title: 'مستند', slug: 'documentary', icon: 'document' },
  { id: 15, title: 'زندگی‌نامه‌ای', slug: 'biography', icon: 'profile' },
  { id: 16, title: 'تاریخی', slug: 'history', icon: 'history' },
  { id: 17, title: 'جنگی', slug: 'war', icon: 'shield-alert' },
  { id: 18, title: 'وسترن', slug: 'western', icon: 'map' },
  { id: 19, title: 'موسیقی', slug: 'music', icon: 'audio' },
  { id: 20, title: 'موزیکال', slug: 'musical', icon: 'star' },
  { id: 21, title: 'ورزشی', slug: 'sport', icon: 'badge' },
  { id: 22, title: 'ابرقهرمانی', slug: 'superhero', icon: 'bolt' },
  { id: 23, title: 'انیمه', slug: 'anime', icon: 'animation' },
  { id: 24, title: 'روان‌شناختی', slug: 'psychological', icon: 'thoughtful' },
  { id: 25, title: 'سیاسی', slug: 'political', icon: 'globe' },
  { id: 26, title: 'فاجعه‌ای', slug: 'disaster', icon: 'alert-triangle' },
  { id: 27, title: 'دادگاهی', slug: 'legal', icon: 'investigate' },
  { id: 28, title: 'کودک', slug: 'kids', icon: 'family' },
  { id: 29, title: 'رئالیتی‌شو', slug: 'reality-tv', icon: 'users' },
  { id: 30, title: 'نوآر', slug: 'film-noir', icon: 'film' },
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
    return apiGenre ? { ...genre, id: apiGenre.id } : genre
  })
  const custom = apiGenres.filter(genre => !catalogGenreBySlug.has(genre.slug))
  return [...canonical, ...custom]
}
