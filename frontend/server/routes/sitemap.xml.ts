interface CatalogResponse {
  results?: Array<{ slug?: string }>
}

function escapeXml(value: string) {
  return value
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&apos;')
}

export default defineEventHandler(async (event) => {
  const config = useRuntimeConfig(event)
  const siteUrl = String(config.public.siteUrl).replace(/\/$/, '')
  const apiBase = String(config.apiInternalBase).replace(/\/$/, '')
  const paths = new Set([
    '/',
    '/movies',
    '/series',
    '/about',
    '/contact',
    '/privacy',
    '/terms',
  ])

  try {
    const [movies, series] = await Promise.all([
      $fetch<CatalogResponse>(`${apiBase}/movies/`, { query: { limit: 100 } }),
      $fetch<CatalogResponse>(`${apiBase}/series/`, { query: { limit: 100 } }),
    ])
    for (const movie of movies.results || []) {
      if (movie.slug) paths.add(`/movies/${encodeURIComponent(movie.slug)}`)
    }
    for (const show of series.results || []) {
      if (show.slug) paths.add(`/series/${encodeURIComponent(show.slug)}`)
    }
  } catch {
    // Static routes remain available if the catalog API is temporarily unavailable.
  }

  const urls = [...paths]
    .map(path => `  <url><loc>${escapeXml(`${siteUrl}${path}`)}</loc></url>`)
    .join('\n')

  setHeader(event, 'content-type', 'application/xml; charset=utf-8')
  setHeader(event, 'cache-control', 'public, max-age=3600, stale-while-revalidate=86400')

  return `<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n${urls}\n</urlset>\n`
})
