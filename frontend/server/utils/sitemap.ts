/**
 * Shared pieces of the split sitemap (see routes/sitemap.xml.ts and
 * routes/sitemaps/[name].ts). The backend feed /api/catalog/sitemap/ lists only
 * published titles and landing facets that hold enough titles, so nothing here
 * can advertise a 404 or a thin page.
 */
import type { H3Event } from 'h3'

export interface SitemapSummary {
  page_size: number
  counts: { movies: number; series: number; actors: number }
  genres: Array<{ slug: string; movies: number; series: number }>
  countries: Array<{ code: string; movies: number; series: number }>
  years: { movies: number[]; series: number[] }
}

export interface SitemapRow {
  slug: string
  lastmod?: string
  image?: string
  title?: string
}

export type SitemapKind = 'movies' | 'series' | 'actors'

/** Indexable pages that are not generated from the catalog. */
export const STATIC_SITEMAP_PATHS = [
  '/',
  '/movies',
  '/series',
  '/new',
  '/top250',
  '/schedule',
  '/actors',
  '/countries',
  '/movies/dubbed',
  '/series/dubbed',
  '/movies/subtitle',
  '/series/subtitle',
  '/about',
  '/contact',
  '/privacy',
  '/terms',
]

export function escapeXml(value: string) {
  return value
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&apos;')
}

export function sitemapContext(event: H3Event) {
  const config = useRuntimeConfig(event)
  return {
    siteUrl: String(config.public.siteUrl).replace(/\/$/, ''),
    apiBase: String(config.apiInternalBase).replace(/\/$/, ''),
  }
}

export function fetchSitemapSummary(apiBase: string) {
  return $fetch<SitemapSummary>(`${apiBase}/catalog/sitemap/`)
}

export async function fetchSitemapPart(apiBase: string, kind: SitemapKind, page: number) {
  const response = await $fetch<{ results?: SitemapRow[] }>(`${apiBase}/catalog/sitemap/`, {
    query: { kind, page },
  })
  return response.results || []
}

export function pageCount(total: number, pageSize: number) {
  return Math.max(0, Math.ceil(total / Math.max(1, pageSize)))
}

export function urlEntry(loc: string, options: { lastmod?: string; images?: string[] } = {}) {
  const parts = [`<loc>${escapeXml(loc)}</loc>`]
  if (options.lastmod) parts.push(`<lastmod>${escapeXml(options.lastmod)}</lastmod>`)
  for (const image of options.images || []) {
    if (/^https?:\/\//.test(image)) parts.push(`<image:image><image:loc>${escapeXml(image)}</image:loc></image:image>`)
  }
  return `  <url>${parts.join('')}</url>`
}

export function sendXml(event: H3Event, body: string) {
  setHeader(event, 'content-type', 'application/xml; charset=utf-8')
  setHeader(event, 'cache-control', 'public, max-age=3600, stale-while-revalidate=86400')
  return body
}

export function urlset(entries: string[]) {
  return '<?xml version="1.0" encoding="UTF-8"?>\n'
    + '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" xmlns:image="http://www.google.com/schemas/sitemap-image/1.1">\n'
    + `${entries.join('\n')}\n</urlset>\n`
}
