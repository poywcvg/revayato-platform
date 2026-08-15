interface CatalogResponse {
  count?: number
  next?: string | null
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

async function fetchAllSlugs(apiBase: string, path: string, limit = 100, maxPages = 20) {
  const slugs: string[] = []
  let offset = 0
  for (let page = 0; page < maxPages; page += 1) {
    const response = await $fetch<CatalogResponse>(`${apiBase}${path}`, {
      query: { limit, offset },
    })
    for (const row of response.results || []) {
      if (row.slug) slugs.push(row.slug)
    }
    const count = Number(response.count || 0)
    offset += limit
    if (!response.next || offset >= count || !(response.results || []).length) break
  }
  return slugs
}

export default defineEventHandler(async (event) => {
  const config = useRuntimeConfig(event)
  const siteUrl = String(config.public.siteUrl).replace(/\/$/, '')
  const apiBase = String(config.apiInternalBase).replace(/\/$/, '')
  const paths = new Set([
    '/',
    '/movies',
    '/series',
    '/new',
    '/actors',
    '/countries',
    '/search',
    '/about',
    '/contact',
    '/privacy',
    '/terms',
  ])

  try {
    const [movieSlugs, seriesSlugs, actorSlugs] = await Promise.all([
      fetchAllSlugs(apiBase, '/movies/'),
      fetchAllSlugs(apiBase, '/series/'),
      fetchAllSlugs(apiBase, '/actors/', 100, 8),
    ])
    for (const slug of movieSlugs) paths.add(`/movies/${encodeURIComponent(slug)}`)
    for (const slug of seriesSlugs) paths.add(`/series/${encodeURIComponent(slug)}`)
    for (const slug of actorSlugs) paths.add(`/actors/${encodeURIComponent(slug)}`)
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
