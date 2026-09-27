/** One part of the split sitemap — see routes/sitemap.xml.ts for the index. */
const PART_RE = /^(movies|series|actors)-(\d{1,4})\.xml$/

const DETAIL_BASE: Record<SitemapKind, string> = {
  movies: '/movies',
  series: '/series',
  actors: '/actors',
}

export default defineEventHandler(async (event) => {
  const name = getRouterParam(event, 'name') || ''
  const { siteUrl, apiBase } = sitemapContext(event)
  const absolute = (path: string) => `${siteUrl}${path}`

  if (name === 'static.xml') {
    return sendXml(event, urlset(STATIC_SITEMAP_PATHS.map(path => urlEntry(absolute(path)))))
  }

  if (name === 'landing.xml') {
    const summary = await fetchSitemapSummary(apiBase).catch(() => null)
    if (!summary) throw createError({ statusCode: 503, statusMessage: 'catalog unavailable' })
    const paths: string[] = []
    for (const genre of summary.genres) {
      if (genre.movies) paths.push(`/movies/genre/${encodeURIComponent(genre.slug)}`)
      if (genre.series) paths.push(`/series/genre/${encodeURIComponent(genre.slug)}`)
    }
    for (const country of summary.countries) {
      const code = country.code.toLowerCase()
      if (country.movies) paths.push(`/movies/country/${code}`)
      if (country.series) paths.push(`/series/country/${code}`)
    }
    for (const year of summary.years.movies) paths.push(`/movies/year/${year}`)
    for (const year of summary.years.series) paths.push(`/series/year/${year}`)
    return sendXml(event, urlset(paths.map(path => urlEntry(absolute(path)))))
  }

  const match = name.match(PART_RE)
  if (!match) throw createError({ statusCode: 404, statusMessage: 'Not Found' })
  const kind = match[1] as SitemapKind
  const page = Number(match[2])
  if (page < 1) throw createError({ statusCode: 404, statusMessage: 'Not Found' })

  const rows = await fetchSitemapPart(apiBase, kind, page).catch(() => null)
  if (rows === null) throw createError({ statusCode: 503, statusMessage: 'catalog unavailable' })
  if (!rows.length) throw createError({ statusCode: 404, statusMessage: 'Not Found' })

  const entries = rows
    .filter(row => row.slug)
    .map(row => urlEntry(absolute(`${DETAIL_BASE[kind]}/${encodeURIComponent(row.slug)}`), {
      lastmod: row.lastmod,
      images: row.image ? [row.image] : [],
    }))
  return sendXml(event, urlset(entries))
})
