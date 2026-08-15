/**
 * Broad catalog preload only where local filtering needs a large pool.
 * /movies and /series use remote pagination in CatalogBrowser — skip them
 * so those routes stay out of a heavy shared SSR payload.
 */
export default defineNuxtPlugin(async () => {
  const route = useRoute()
  const broadCatalogRoutes = new Set([
    '/search',
    '/watchlist',
    '/profile',
    '/profile/favorites',
    '/profile/watchlist',
  ])
  if (!broadCatalogRoutes.has(route.path.replace(/\/+$/, '') || '/')) return

  const { loadFromApi } = useCatalog()
  await loadFromApi(false, 'full')
})
