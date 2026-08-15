import type { AdminCountry, AdminGenre } from '~/types'
import { mergeCatalogGenres } from '~/data/genres'

/**
 * Shared catalog metadata + public-catalog cache-busting for the admin panel.
 *
 * Consolidates the duplicate `genres()`/`countries()` loaders previously living
 * inside both `useAdminMovies` and `useAdminSeries`, and the single
 * `bumpPublicCatalog()` that must keep clearing actor Nuxt data after a movie
 * save (see `useAdminMovies.bumpPublicCatalog`).
 */
export function useAdminCatalogMeta() {
  const { api } = useApi()
  const { invalidateCatalog } = useCatalog()

  async function genres(): Promise<AdminGenre[]> {
    const list = await api<AdminGenre[]>('/genres/')
    return mergeCatalogGenres(list.map(genre => ({
      id: genre.id,
      title: genre.title,
      slug: genre.slug,
      icon: 'film' as const,
    }))).map(genre => ({
      id: genre.id,
      title: genre.title,
      slug: genre.slug,
    }))
  }

  function countries(): Promise<AdminCountry[]> {
    return api<AdminCountry[]>('/countries/')
  }

  /** Bust the public catalog cache AND any cached actor pages. */
  function bumpPublicCatalog() {
    invalidateCatalog()
    if (import.meta.client) {
      clearNuxtData((key) => {
        if (typeof key !== 'string') return false
        return key === 'home-actors' || key === 'actors-index' || key.startsWith('actor-detail-')
      })
    }
  }

  return { genres, countries, bumpPublicCatalog }
}