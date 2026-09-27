/**
 * Sitemap index. The catalog is far past the 50,000-URL / single-file limits, so
 * it is split into parts that each stay small and cacheable:
 *
 *   /sitemaps/static.xml     hand-made pages
 *   /sitemaps/landing.xml    genre / country / year / dubbed landing pages
 *   /sitemaps/movies-N.xml   every published movie (+ poster)
 *   /sitemaps/series-N.xml   every published series (+ poster)
 *   /sitemaps/actors-N.xml   everyone who appears in a published title
 */
export default defineEventHandler(async (event) => {
  const { siteUrl, apiBase } = sitemapContext(event)
  const names = ['static', 'landing']
  try {
    const summary = await fetchSitemapSummary(apiBase)
    for (const kind of ['movies', 'series', 'actors'] as const) {
      const pages = pageCount(summary.counts[kind], summary.page_size)
      for (let page = 1; page <= pages; page += 1) names.push(`${kind}-${page}`)
    }
  }
  catch {
    // The static part still gets listed while the catalog API is unreachable.
  }

  const entries = names
    .map(name => `  <sitemap><loc>${escapeXml(`${siteUrl}/sitemaps/${name}.xml`)}</loc></sitemap>`)
    .join('\n')
  return sendXml(
    event,
    `<?xml version="1.0" encoding="UTF-8"?>\n<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n${entries}\n</sitemapindex>\n`,
  )
})
