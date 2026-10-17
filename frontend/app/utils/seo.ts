/**
 * One place that decides how a movie/series page presents itself to search
 * engines: the <title>, the meta description and the schema.org graph.
 *
 * Persian searchers type the intent first («دانلود فیلم …», «سریال … دوبله
 * فارسی») and then either name — the Persian title, the English one, often with
 * the year. The generated title carries all three so every one of those queries
 * matches, and the description leads with facts (genre, country, IMDb, director,
 * cast) before the plot, because that is what earns the click.
 *
 * Editors still win: a title/description written by hand in the admin
 * (``seo_custom``) is used verbatim. The importer's automatic copy of the plain
 * title is NOT treated as custom — it would throw all of the above away.
 */
import type { Ref } from 'vue'
import type { Movie } from '~/types'

export const SITE_NAME = 'روایتو'
/** Google shows ~60 Latin / fewer Persian characters; « | روایتو» is appended by titleTemplate. */
const TITLE_BUDGET = 62
const DESCRIPTION_BUDGET = 165

export function siteOrigin(siteUrl: unknown) {
  return String(siteUrl || '').replace(/\/+$/, '')
}

export function absoluteUrl(siteUrl: unknown, path: string) {
  if (/^https?:\/\//i.test(path)) return path
  return `${siteOrigin(siteUrl)}${path.startsWith('/') ? path : `/${path}`}`
}

export function detailPath(item: Pick<Movie, 'type' | 'slug'>) {
  return `${item.type === 'series' ? '/series' : '/movies'}/${item.slug}`
}

function kindWord(item: Pick<Movie, 'type'>) {
  return item.type === 'series' ? 'سریال' : 'فیلم'
}

function englishName(item: Movie) {
  const english = (item.original_title || '').trim()
  return english && english !== item.title ? english : ''
}

/** «با دوبله فارسی» / «با زیرنویس فارسی» / «با دوبله و زیرنویس فارسی» — only what is true. */
export function persianAudioPhrase(item: Pick<Movie, 'is_dubbed' | 'has_subtitle'>) {
  if (item.is_dubbed && item.has_subtitle) return 'با دوبله و زیرنویس فارسی'
  if (item.is_dubbed) return 'با دوبله فارسی'
  if (item.has_subtitle) return 'با زیرنویس فارسی'
  return ''
}

function isWatchable(item: Movie) {
  return Boolean(item.hls_url || item.playback?.hls_url || item.episodes?.some(episode => episode.hls_url))
}

/** The verb a searcher uses for what this page actually offers — never a promise it can't keep. */
function offerVerb(item: Movie) {
  if (item.has_downloads && isWatchable(item)) return 'دانلود و تماشای آنلاین'
  if (item.has_downloads) return 'دانلود'
  if (isWatchable(item)) return 'تماشای آنلاین'
  return ''
}

function trimToWord(text: string, budget: number) {
  const clean = text.replace(/\s+/g, ' ').trim()
  if (clean.length <= budget) return clean
  const cut = clean.slice(0, budget - 1)
  const space = cut.lastIndexOf(' ')
  return `${(space > budget * 0.6 ? cut.slice(0, space) : cut).replace(/[\s،,؛;:.\-–]+$/, '')}…`
}

function hasCustom(item: Movie, field: 'title' | 'description') {
  return Boolean(item.seo_custom?.[field])
}

/** e.g. «دانلود فیلم تلقین Inception 2010 با دوبله فارسی» */
export function detailSeoTitle(item: Movie) {
  if (hasCustom(item, 'title') && item.seo_title) return item.seo_title
  const verb = item.has_downloads ? 'دانلود' : ''
  const base = [verb, kindWord(item), item.title, englishName(item), item.year ? String(item.year) : '']
    .filter(Boolean)
    .join(' ')
  const audio = persianAudioPhrase(item)
  if (audio && base.length + audio.length + 1 <= TITLE_BUDGET) return `${base} ${audio}`
  return base
}

/** e.g. «دانلود فیلم تلقین Inception 2010» — the H2 over the download section. */
export function downloadHeading(item: Movie) {
  return ['دانلود', kindWord(item), item.title, englishName(item), item.year ? String(item.year) : '']
    .filter(Boolean)
    .join(' ')
}

export type LinkVersion = 'dub' | 'sub' | 'original'

export function versionWord(version: LinkVersion) {
  if (version === 'dub') return 'دوبله فارسی'
  if (version === 'sub') return 'زیرنویس فارسی'
  return 'زبان اصلی'
}

export function directorNames(item: Movie, limit = 2) {
  const fromCrew = (item.crew || [])
    .filter(person => person.job === 'کارگردان' || person.job?.toLowerCase().includes('director'))
    .map(person => person.name)
  const names = fromCrew.length ? fromCrew : (item.director ? [item.director] : [])
  return [...new Set(names.filter(Boolean))].slice(0, limit)
}

/** Facts first (they decide the click), then as much of the plot as fits. */
export function detailSeoDescription(item: Movie) {
  if (hasCustom(item, 'description') && item.seo_description) return item.seo_description
  const english = englishName(item)
  const identity = english
    ? `${item.title} (${english}${item.year ? ` ${item.year}` : ''})`
    : `${item.title}${item.year ? ` (${item.year})` : ''}`
  const lead = [offerVerb(item) || 'معرفی', kindWord(item), identity, persianAudioPhrase(item)]
    .filter(Boolean)
    .join(' ')

  const facts: string[] = []
  const genres = (item.genres || []).slice(0, 3).map(genre => genre.title).filter(Boolean)
  if (genres.length) facts.push(genres.join('، '))
  if (item.country) facts.push(`محصول ${item.country.split('،')[0]!.trim()}`)
  if (item.imdb_rating) facts.push(`امتیاز IMDb ${Number(item.imdb_rating).toFixed(1)}`)
  const directors = directorNames(item, 1)
  if (directors.length) facts.push(`کارگردان ${directors[0]}`)
  const stars = (item.cast || []).slice(0, 2).map(person => person.name).filter(Boolean)
  if (stars.length) facts.push(`با بازی ${stars.join(' و ')}`)

  const head = facts.length ? `${lead}؛ ${facts.join('، ')}.` : `${lead}.`
  const plot = (item.description || '').trim()
  return trimToWord(plot ? `${head} ${plot}` : head, DESCRIPTION_BUDGET)
}

/** Meta keywords are ignored by Google but still read by Persian engines and on-site search. */
export function detailSeoKeywords(item: Movie) {
  const kind = kindWord(item)
  const english = englishName(item)
  const local = [
    item.title,
    english,
    english && item.year ? `${english} ${item.year}` : '',
    `${kind} ${item.title}`,
    item.has_downloads ? `دانلود ${kind} ${item.title}` : '',
    english && item.has_downloads ? `دانلود ${kind} ${english}` : '',
    item.is_dubbed ? `${kind} ${item.title} دوبله فارسی` : '',
    item.has_subtitle ? `${kind} ${item.title} زیرنویس فارسی` : '',
    ...(item.download_qualities || []),
    ...(item.cast || []).slice(0, 5).map(person => person.name),
    ...directorNames(item),
    ...(item.genres || []).map(genre => genre.title),
  ].filter(Boolean) as string[]
  return [...new Set([...(item.seo_keywords || []), ...local])].join(', ')
}

function youtubeId(url: string) {
  const match = url.match(/(?:youtube\.com\/(?:watch\?(?:.*&)?v=|embed\/|shorts\/)|youtu\.be\/)([\w-]{11})/)
  return match?.[1] || ''
}

function trailerNode(item: Movie) {
  const url = item.trailer_url || ''
  const id = url ? youtubeId(url) : ''
  if (!id) return undefined
  return {
    '@type': 'VideoObject',
    name: `تریلر ${kindWord(item)} ${item.title}${englishName(item) ? ` (${englishName(item)})` : ''}`,
    description: `پیش‌نمایش رسمی ${kindWord(item)} ${item.title}${item.year ? ` محصول ${item.year}` : ''}`,
    thumbnailUrl: [`https://i.ytimg.com/vi/${id}/hqdefault.jpg`],
    embedUrl: `https://www.youtube.com/embed/${id}`,
    ...(item.created_at ? { uploadDate: item.created_at } : {}),
  }
}

function personNode(siteUrl: unknown, person: { name: string; slug?: string }) {
  return {
    '@type': 'Person',
    name: person.name,
    ...(person.slug ? { url: absoluteUrl(siteUrl, `/actors/${person.slug}`) } : {}),
  }
}

/**
 * An absolute URL for a stored image, or ``''`` for none/placeholder. Posters are
 * served as site-relative ``/media/...`` paths; og:image, twitter:image and
 * schema.org need the full URL, and a relative one was silently dropped — so no
 * detail page had a share/Google Images picture.
 */
export function seoImage(siteUrl: unknown, url: string | null | undefined) {
  const value = String(url || '').trim()
  if (!value || /placeholder/i.test(value)) return ''
  if (/^https?:\/\//i.test(value)) return value
  if (value.startsWith('//')) return `https:${value}`
  return value.startsWith('/') ? absoluteUrl(siteUrl, value) : ''
}

function realImage(siteUrl: unknown, url: string | undefined, has: boolean | undefined) {
  return has === false ? '' : seoImage(siteUrl, url)
}

/** JSON for a <script> body: `<` escaped so a plot containing "</script>" can't break out. */
export function jsonLdString(value: unknown) {
  return JSON.stringify(value).replace(/</g, '\\u003c')
}

export interface Crumb { name: string; path: string }

export function breadcrumbNode(siteUrl: unknown, crumbs: Crumb[]) {
  return {
    '@type': 'BreadcrumbList',
    itemListElement: crumbs.map((crumb, index) => ({
      '@type': 'ListItem',
      position: index + 1,
      name: crumb.name,
      item: absoluteUrl(siteUrl, crumb.path),
    })),
  }
}

export function detailCrumbs(item: Movie): Crumb[] {
  const section = item.type === 'series' ? { name: 'سریال‌ها', path: '/series' } : { name: 'فیلم‌ها', path: '/movies' }
  const genre = item.genres?.[0]
  return [
    { name: SITE_NAME, path: '/' },
    section,
    ...(genre ? [{ name: `${kindWord(item)} ${genre.title}`, path: `${section.path}/genre/${genre.slug}` }] : []),
    { name: item.title, path: detailPath(item) },
  ]
}

/** schema.org @graph for a movie/series page: the work itself + its breadcrumb. */
export function detailJsonLd(item: Movie, siteUrl: unknown) {
  const url = absoluteUrl(siteUrl, detailPath(item))
  const isSeries = item.type === 'series'
  const english = englishName(item)
  const images = [
    realImage(siteUrl, item.poster_url, item.has_artwork),
    realImage(siteUrl, item.backdrop_url, item.has_backdrop),
  ].filter(Boolean)
  const site = (item.ratings || []).find(entry => entry.source === 'site' && entry.value > 0)
  const sameAs = [
    item.imdb_id ? `https://www.imdb.com/title/${item.imdb_id}/` : '',
    item.tmdb_id ? `https://www.themoviedb.org/${isSeries ? 'tv' : 'movie'}/${item.tmdb_id}` : '',
  ].filter(Boolean)
  const seasons = new Set((item.episodes || []).map(episode => episode.season_number).filter(Boolean))

  const work: Record<string, unknown> = {
    '@type': isSeries ? 'TVSeries' : 'Movie',
    '@id': `${url}#work`,
    url,
    name: item.title,
    ...(english ? { alternateName: english } : {}),
    ...(item.description ? { description: item.description } : {}),
    ...(images.length ? { image: images } : {}),
    ...(item.year ? { [isSeries ? 'startDate' : 'datePublished']: String(item.year) } : {}),
    ...(item.updated_at ? { dateModified: item.updated_at } : {}),
    ...(!isSeries && item.duration_minutes ? { duration: `PT${item.duration_minutes}M` } : {}),
    ...(item.age_rating ? { contentRating: item.age_rating } : {}),
    ...(item.country ? {
      countryOfOrigin: item.country.split('،').map(name => name.trim()).filter(Boolean)
        .map(name => ({ '@type': 'Country', name })),
    } : {}),
    ...(item.genres?.length ? { genre: item.genres.map(genre => genre.title) } : {}),
    ...(directorNames(item, 3).length ? {
      director: (item.crew || [])
        .filter(person => person.job === 'کارگردان' || person.job?.toLowerCase().includes('director'))
        .slice(0, 3)
        .map(person => personNode(siteUrl, person)),
    } : {}),
    ...(item.cast?.length ? { actor: item.cast.slice(0, 10).map(person => personNode(siteUrl, person)) } : {}),
    ...(item.has_subtitle ? { subtitleLanguage: 'fa' } : {}),
    ...(sameAs.length ? { sameAs } : {}),
    ...(isSeries && seasons.size ? { numberOfSeasons: seasons.size } : {}),
    ...(isSeries && item.episodes?.length ? { numberOfEpisodes: item.episodes.length } : {}),
    // One TVSeason per season, pointing at its anchor in the download section —
    // what «سریال X فصل ۲» searches resolve to.
    ...(isSeries && seasons.size ? {
      containsSeason: [...seasons].filter((n): n is number => typeof n === 'number').sort((a, b) => a - b).map(number => ({
        '@type': 'TVSeason',
        name: `فصل ${number}`,
        seasonNumber: number,
        numberOfEpisodes: (item.episodes || []).filter(episode => episode.season_number === number).length,
        url: `${url}#season-${number}`,
      })),
    } : {}),
    // Only this site's own user ratings — republishing IMDb/TMDB scores as our
    // aggregateRating violates Google's review-snippet policy.
    ...(site && site.voteCount ? {
      aggregateRating: {
        '@type': 'AggregateRating',
        ratingValue: site.value,
        bestRating: site.scale,
        worstRating: 1,
        ratingCount: site.voteCount,
      },
    } : {}),
  }
  const trailer = trailerNode(item)
  if (trailer) work.trailer = trailer

  return {
    '@context': 'https://schema.org',
    '@graph': [
      work,
      breadcrumbNode(siteUrl, detailCrumbs(item)),
    ],
  }
}

/**
 * useSeoMeta + JSON-LD for a movie/series detail page. The canonical is the
 * detail URL itself (app.vue emits it from the route path).
 */
export function useDetailSeo(item: Ref<Movie | null | undefined>) {
  const config = useRuntimeConfig()
  const title = computed(() => (item.value ? detailSeoTitle(item.value) : ''))
  const description = computed(() => (item.value ? detailSeoDescription(item.value) : ''))
  const image = computed(() => {
    const value = item.value
    if (!value) return ''
    return realImage(config.public.siteUrl, value.backdrop_url, value.has_backdrop)
      || realImage(config.public.siteUrl, value.poster_url, value.has_artwork)
  })

  useSeoMeta({
    title,
    description,
    ogTitle: title,
    ogDescription: description,
    ogType: () => (item.value?.type === 'series' ? 'video.tv_show' : 'video.movie'),
    ogImage: () => image.value || undefined,
    ogImageAlt: () => (item.value ? `پوستر ${kindWord(item.value)} ${item.value.title}` : undefined),
    twitterImage: () => image.value || undefined,
    twitterCard: 'summary_large_image',
    twitterTitle: title,
    twitterDescription: description,
    keywords: () => (item.value ? detailSeoKeywords(item.value) : undefined),
    robots: 'index, follow, max-image-preview:large, max-snippet:-1, max-video-preview:-1',
  })

  useHead(() => {
    const value = item.value
    if (!value) return {}
    return {
      script: [{
        key: 'detail-jsonld',
        type: 'application/ld+json',
        innerHTML: jsonLdString(detailJsonLd(value, config.public.siteUrl)),
      }],
    }
  })
}
