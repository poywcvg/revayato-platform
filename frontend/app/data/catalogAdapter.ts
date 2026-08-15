import type { AgeRating, CastMember, ContentFormat, ContentType, CrewMember, DownloadLink, Genre, Movie, PlaybackTextTrack } from '~/types'
import { getCatalogGenre } from '~/data/genres'
import { localizeCountry } from '~/data/countries'
import { preferEnglishName } from '~/utils/displayNames'
import { isSoftsubLink, linksImplyDub, linksImplySubtitle } from '~/utils/playbackVersions'
import { normalizeMediaRatings, primaryCardRating, ratingsFromLegacyFields } from '~/utils/mediaRatings'

export interface ApiGenre {
  id: number
  title: string
  slug: string
  is_featured?: boolean
  movie_count?: number
  series_count?: number
  title_count?: number
}

interface ApiPerson {
  id: number
  name: string
  original_name?: string
  slug?: string
  photo?: string | null
  photo_external_url?: string | null
}

interface ApiEpisode {
  id: number
  title: string
  episode_number: number
  description?: string
  duration_minutes?: number | null
  poster?: string | null
  video_url?: string
  download_url?: string | null
  subtitle_tracks?: ApiSubtitleTrack[]
  is_published?: boolean
}

interface ApiSubtitleTrack {
  id?: string
  label?: string
  language?: string
  src?: string
  default?: boolean
  source_url?: string
  season_number?: number
  episode_number?: number
  provider?: string
  source_priority?: number
  sync_confidence?: string
}

interface ApiSeason {
  id: number
  title?: string
  season_number: number
  episode_count?: number
  episodes?: ApiEpisode[]
}

interface ApiCredit {
  id: number
  actor: ApiPerson
  role?: string
}

export interface ApiCatalogItem {
  id: number
  title: string
  slug: string
  original_title?: string
  /** English title from API — display under Persian primary title. */
  secondary_title?: string
  short_description?: string
  description?: string
  release_year?: number | null
  start_year?: number | null
  duration_minutes?: number | null
  genres?: ApiGenre[]
  countries?: Array<{ name: string; code?: string }>
  directors?: ApiPerson[]
  movie_actors?: ApiCredit[]
  series_actors?: ApiCredit[]
  poster?: string | null
  backdrop?: string | null
  trailer_url?: string
  video_url?: string
  download_url?: string | null
  download_links?: Array<{
    label?: string
    quality?: string
    size_label?: string
    url: string
    kind?: string
    subtitle_type?: string
    season?: string
    episode?: string
    season_number?: number
    episode_number?: number
  }>
  quality?: string
  has_downloads?: boolean
  download_qualities?: string[]
  seo_title?: string
  seo_description?: string
  seo_keywords?: string[]
  subtitle_tracks?: ApiSubtitleTrack[]
  imdb_rating?: number | string | null
  imdb_rank?: number | null
  rating_average?: number | string | null
  site_rating?: number | string | null
  ratings?: unknown[]
  imdb_id?: string | null
  tmdb_id?: number | null
  age_rating?: string
  language?: string
  content_format?: string
  is_dubbed?: boolean
  has_subtitle?: boolean
  is_published?: boolean
  is_featured?: boolean
  is_recommended?: boolean
  popularity?: number
  is_uncensored?: boolean
  content_warnings?: string[]
  view_count?: number
  like_count?: number
  created_at?: string
  updated_at?: string
  seasons?: ApiSeason[]
}

export interface ApiListResponse<T> {
  count?: number
  next?: string | null
  previous?: string | null
  results?: T[]
}

function normalizeAgeRating(value?: string): AgeRating {
  const rating = value?.replace(/[^0-9]/g, '')
  if (rating === '18') return '18+'
  if (rating === '15' || rating === '16' || rating === '17') return '15+'
  return '12+'
}

function normalizeGenres(genres: ApiGenre[] = []): Genre[] {
  return genres.map(adaptApiGenre)
}

export function adaptApiGenre(genre: ApiGenre): Genre {
  const canonical = getCatalogGenre(genre.slug)
  const movieCount = Number(genre.movie_count || 0)
  const seriesCount = Number(genre.series_count || 0)
  const titleCount = Number(
    genre.title_count != null ? genre.title_count : movieCount + seriesCount,
  )
  return {
    ...genre,
    title: canonical?.title || genre.title,
    icon: canonical?.icon || 'tag',
    is_featured: Boolean(genre.is_featured),
    movie_count: movieCount,
    series_count: seriesCount,
    title_count: titleCount,
  }
}

function normalizeContentFormat(value?: string): ContentFormat {
  return value === 'animation' || value === 'short' ? value : 'live_action'
}

function normalizeWarnings(value: unknown): string[] {
  return Array.isArray(value)
    ? value.filter((warning): warning is string => typeof warning === 'string' && warning.trim().length > 0)
    : []
}

function resolvePublicMediaUrl(value: string | null | undefined, mediaBase: string, fallback: string) {
  if (!value) return fallback
  if (value.startsWith('data:') || value.startsWith('blob:')) return value

  // Prefer same-origin /media paths so Caddy serves files directly (no IPX loop).
  try {
    if (value.startsWith('/media/')) return value
    if (/^(?:https?:)?\/\//.test(value)) {
      const url = new URL(value, 'https://revayato.com')
      if (url.pathname.startsWith('/media/')) return `${url.pathname}${url.search}`
      return value.startsWith('//') ? `https:${value}` : value
    }
  } catch {
    /* fall through */
  }

  if (!/^https?:\/\//.test(mediaBase)) return value.startsWith('/') ? value : `/media/${value}`
  try {
    const absolute = new URL(value.replace(/^\/+/, ''), `${mediaBase.replace(/\/$/, '')}/`).toString()
    const url = new URL(absolute)
    if (url.pathname.startsWith('/media/')) return `${url.pathname}${url.search}`
    return absolute
  } catch {
    return value
  }
}

function isPlaceholderMedia(url: string) {
  return /placeholder-poster|backdrop-orbit|poster-orbit/i.test(url)
}

function normalizeCast(item: ApiCatalogItem, mediaBase: string): CastMember[] {
  return [...(item.movie_actors || []), ...(item.series_actors || [])].map(credit => {
    const names = preferEnglishName(credit.actor.original_name, credit.actor.name)
    return {
      id: credit.id,
      name: names.primary,
      secondary_name: names.secondary || undefined,
      slug: credit.actor.slug || '',
      role: credit.role || 'بازیگر',
      photo_url: credit.actor.photo
        ? resolvePublicMediaUrl(credit.actor.photo, mediaBase, credit.actor.photo)
        : (credit.actor.photo_external_url || null),
    }
  })
}

function normalizeCrew(directors: ApiPerson[] = [], mediaBase = ''): CrewMember[] {
  return directors.map((person) => {
    const names = preferEnglishName(person.original_name, person.name)
    return {
      id: person.id,
      name: names.primary,
      secondary_name: names.secondary || undefined,
      slug: person.slug || '',
      job: 'کارگردان',
      photo_url: person.photo ? resolvePublicMediaUrl(person.photo, mediaBase, person.photo) : null,
    }
  })
}

export function unwrapApiList<T>(response: ApiListResponse<T> | T[]): T[] {
  return Array.isArray(response) ? response : response.results || []
}

export function adaptApiCatalogItem(item: ApiCatalogItem, type: ContentType, mediaBase = ''): Movie {
  const imdbRating = item.imdb_rating == null ? null : Number(item.imdb_rating)
  const tmdbRating = item.rating_average == null ? null : Number(item.rating_average)
  const siteRating = item.site_rating == null ? null : Number(item.site_rating)
  const normalizedRatings = normalizeMediaRatings(item.ratings)
  const ratings = normalizedRatings.length
    ? normalizedRatings
    : ratingsFromLegacyFields({
      imdb_rating: imdbRating !== null && Number.isFinite(imdbRating) ? imdbRating : null,
      tmdb_rating: tmdbRating !== null && Number.isFinite(tmdbRating) ? tmdbRating : null,
      site_rating: siteRating !== null && Number.isFinite(siteRating) ? siteRating : null,
      imdb_id: item.imdb_id,
      tmdb_id: item.tmdb_id,
      type,
    })
  const cardRating = primaryCardRating(ratings)
  // Compatibility scalar for filters/sort — never invent a score.
  const rating = cardRating?.value ?? 0
  // Trusted source-specific scalars (polluted IMDb copies filtered by ratings helper).
  const trustedImdb = ratings.find(entry => entry.source === 'imdb')?.value ?? null
  const trustedTmdb = ratings.find(entry => entry.source === 'tmdb')?.value ?? null
  const directors = item.directors || []
  const createdAt = item.created_at ? new Date(item.created_at).getTime() : 0
  const updatedAt = item.updated_at ? new Date(item.updated_at).getTime() : createdAt
  const isRecent = Math.max(createdAt, updatedAt) > Date.now() - (1000 * 60 * 60 * 24 * 30)
  const episodes = (item.seasons || []).flatMap(season => (season.episodes || []).map(episode => {
    const episodeTracks = (episode.subtitle_tracks || [])
      .filter(track => Boolean(track.src))
      .map((track, index) => ({
        id: track.id || `ep-${episode.id}-${track.language || 'fa'}-${index}`,
        label: track.label || track.language || 'فارسی',
        language: track.language || 'fa',
        src: resolvePublicMediaUrl(track.src, mediaBase, ''),
        default: Boolean(track.default ?? index === 0),
        source_url: track.source_url || undefined,
        season_number: season.season_number,
        episode_number: episode.episode_number,
        provider: track.provider || undefined,
        source_priority: track.source_priority || undefined,
        sync_confidence: track.sync_confidence || undefined,
      }))
    return {
      id: episode.id,
      title: episode.title,
      episode_number: episode.episode_number,
      duration_minutes: episode.duration_minutes || 0,
      description: episode.description || '',
      season_number: season.season_number,
      thumbnail_url: resolvePublicMediaUrl(episode.poster, mediaBase, '/placeholder-poster.svg'),
      hls_url: resolvePublicMediaUrl(episode.video_url, mediaBase, '')
        || resolvePublicMediaUrl(episode.download_url, mediaBase, ''),
      download_url: resolvePublicMediaUrl(episode.download_url, mediaBase, '') || null,
      subtitle_tracks: episodeTracks,
    }
  }))
  const firstPlayableEpisode = (item.seasons || []).flatMap(season => season.episodes || []).find(
    episode => episode.video_url || episode.download_url || (episode.subtitle_tracks || []).length,
  )
  const downloadLinks: DownloadLink[] = (item.download_links || [])
    .filter(link => Boolean(link?.url))
    .map(link => ({
      label: link.label || link.quality || 'دانلود',
      quality: link.quality || '',
      size_label: link.size_label || '',
      url: link.url,
      kind: link.kind || '',
      subtitle_type: link.subtitle_type || '',
      season: link.season || '',
      episode: link.episode || '',
      season_number: typeof link.season_number === 'number' ? link.season_number : undefined,
      episode_number: typeof link.episode_number === 'number' ? link.episode_number : undefined,
    }))
    .sort((a, b) => qualityRank(b.quality) - qualityRank(a.quality))
  if (!downloadLinks.length && item.download_url) {
    downloadLinks.push({
      label: item.quality || 'دانلود',
      quality: item.quality || '',
      size_label: '',
      url: item.download_url,
    })
  }
  const resolvedVideo = resolvePublicMediaUrl(
    item.video_url || firstPlayableEpisode?.video_url || firstPlayableEpisode?.download_url,
    mediaBase,
    '',
  )
  const hlsUrl = resolvedVideo || downloadLinks[0]?.url || ''
  let subtitleTracks: PlaybackTextTrack[] = (item.subtitle_tracks || [])
    .filter(track => Boolean(track.src))
    .map((track, index) => ({
      id: track.id || `${track.language || 'subtitle'}-${index}`,
      label: track.label || track.language || 'فارسی',
      language: track.language || 'fa',
      src: resolvePublicMediaUrl(track.src, mediaBase, ''),
      default: Boolean(track.default),
      source_url: track.source_url || undefined,
      season_number: typeof track.season_number === 'number' ? track.season_number : undefined,
      episode_number: typeof track.episode_number === 'number' ? track.episode_number : undefined,
      provider: track.provider || undefined,
      source_priority: track.source_priority || undefined,
      sync_confidence: track.sync_confidence || undefined,
    }))

  // Do NOT promote another episode's SoftSub to series-level — that desyncs
  // the player when episode N plays episode 1's cues. Episode tracks stay on episodes.

  // When API extraction is missing, infer subtitle tracks from standalone SoftSub files.
  if (!subtitleTracks.length) {
    const softFiles = downloadLinks
      .filter(link => isSoftsubLink(link))
      .filter(link => /\.(vtt|webvtt|srt|ass|ssa)($|\?)/i.test(String(link.url || '')))
      .sort((a, b) => qualityRank(b.quality) - qualityRank(a.quality))

    if (softFiles.length) {
      subtitleTracks = softFiles.map((link, index) => ({
        id: `fa-softsub-inferred-${index}`,
        label: 'فارسی',
        language: 'fa',
        src: link.url,
        default: index === 0,
        source_url: link.url,
        season_number: typeof link.season_number === 'number' ? link.season_number : undefined,
        episode_number: typeof link.episode_number === 'number' ? link.episode_number : undefined,
      }))
    }
  }

  const posterUrl = resolvePublicMediaUrl(item.poster, mediaBase, '/placeholder-poster.svg')
  const resolvedBackdrop = resolvePublicMediaUrl(item.backdrop, mediaBase, '')
  // Prefer a real still; if TMDB never shipped a backdrop, fall back to the poster
  // so hero/detail pages never render an empty plane.
  const backdropUrl = resolvedBackdrop || (isPlaceholderMedia(posterUrl) ? '/placeholder-poster.svg' : posterUrl)
  const hasArtwork = Boolean(item.poster) && !isPlaceholderMedia(posterUrl)
  const hasBackdrop = Boolean(resolvedBackdrop) && !isPlaceholderMedia(resolvedBackdrop)
  // Backend owns title resolution: title=Persian, original/secondary=English.
  const persianTitle = (item.title || '').trim()
  const englishTitle = (
    item.secondary_title
    || item.original_title
    || ''
  ).trim()
  const primaryDirector = normalizeCrew(directors.slice(0, 1), mediaBase)[0]
  // Prefer live link metadata when present (detail responses); else trust API flags from admin sync.
  const isDubbed = Boolean(item.is_dubbed || linksImplyDub(downloadLinks))
  const hasEpisodeSubtitles = episodes.some(episode => (episode.subtitle_tracks || []).length > 0)
  const hasSubtitle = Boolean(
    item.has_subtitle
    || subtitleTracks.length
    || hasEpisodeSubtitles
    || linksImplySubtitle(downloadLinks),
  )
  const spokenLanguage = (item.language || '').trim()
  const countryLabel = item.countries
    ?.map(country => localizeCountry(country.name, country.code))
    .filter(Boolean)
    .join('، ') || ''
  const directorName = primaryDirector?.name || directors[0]?.name || ''

  return {
    id: item.id,
    title: persianTitle || englishTitle,
    secondary_title: englishTitle && englishTitle !== persianTitle ? englishTitle : undefined,
    slug: item.slug,
    original_title: englishTitle || persianTitle,
    description: (item.description || item.short_description || '').trim(),
    year: item.release_year || item.start_year || 0,
    duration_minutes: item.duration_minutes || 0,
    genres: normalizeGenres(item.genres),
    country: countryLabel,
    language: spokenLanguage,
    director: directorName,
    poster_url: posterUrl,
    backdrop_url: backdropUrl,
    trailer_url: resolvePublicMediaUrl(item.trailer_url, mediaBase, ''),
    hls_url: hlsUrl,
    rating: Number.isFinite(rating) ? rating : 0,
    imdb_rating: trustedImdb,
    imdb_rank: (() => {
      const rank = Number(item.imdb_rank)
      return Number.isFinite(rank) && rank >= 1 && rank <= 250 ? Math.trunc(rank) : null
    })(),
    tmdb_rating: trustedTmdb,
    ratings,
    age_rating: normalizeAgeRating(item.age_rating),
    is_uncensored: Boolean(item.is_uncensored),
    has_subtitle: hasSubtitle,
    is_dubbed: isDubbed,
    format: normalizeContentFormat(item.content_format),
    content_warnings: normalizeWarnings(item.content_warnings),
    status: 'published',
    type,
    // Live badge: editorial feature OR recent traction — not every recommended title.
    is_trending: Boolean(item.is_featured)
      || (isRecent && (Number(item.view_count || 0) >= 15 || Number(item.like_count || 0) >= 3)),
    is_recommended: Boolean(item.is_recommended || item.is_featured),
    is_new: isRecent,
    has_artwork: hasArtwork,
    has_backdrop: hasBackdrop,
    progress_percent: 0,
    // Keep TMDB popularity pure; engagement stays on dedicated counters for ranking.
    popularity: Number(item.popularity || 0),
    view_count: Number(item.view_count || 0),
    like_count: Number(item.like_count || 0),
    cast: normalizeCast(item, mediaBase),
    crew: normalizeCrew(directors, mediaBase),
    download_url: downloadLinks[0]?.url || item.download_url || null,
    download_links: downloadLinks,
    quality: item.quality || downloadLinks[0]?.quality || '',
    has_downloads: Boolean(item.has_downloads ?? downloadLinks.length),
    download_qualities: item.download_qualities?.length
      ? item.download_qualities
      : [...new Set(downloadLinks.map(link => link.quality).filter(Boolean))],
    seo_title: item.seo_title || persianTitle || englishTitle,
    seo_description: item.seo_description || '',
    seo_keywords: item.seo_keywords || [],
    recommendation_reason: item.is_featured ? 'انتخاب ویژه تحریریه' : undefined,
    audio_languages: isDubbed
      ? ['دوبله فارسی', ...(spokenLanguage ? [spokenLanguage] : [])]
      : (spokenLanguage ? [spokenLanguage] : []),
    subtitle_languages: hasSubtitle ? ['فارسی'] : [],
    subtitle_tracks: subtitleTracks,
    playback: (hlsUrl || subtitleTracks.length) ? {
      hls_url: hlsUrl || undefined,
      poster_url: posterUrl,
      subtitle_tracks: subtitleTracks,
    } : undefined,
    seasons_count: item.seasons?.length,
    episodes,
    created_at: item.created_at || '',
    updated_at: item.updated_at || item.created_at || '',
  }
}

/**
 * Card/rail DTO — strips cast, episodes, download rows, SEO and playback so
 * home/list SSR payloads stay small and hydrate faster on the client.
 */
export function adaptApiCatalogListItem(
  item: ApiCatalogItem,
  type: ContentType,
  mediaBase = '',
): Movie {
  const ratings = normalizeMediaRatings(
    item.ratings?.length ? item.ratings : ratingsFromLegacyFields(item),
  )
  const cardRating = primaryCardRating(ratings)
  const rating = Number(cardRating?.value || item.imdb_rating || item.rating_average || item.site_rating || 0)
  const trustedImdb = ratings.find(entry => entry.source === 'imdb')?.value
  const trustedTmdb = ratings.find(entry => entry.source === 'tmdb')?.value
  const createdAt = item.created_at ? Date.parse(item.created_at) : 0
  const isRecent = Boolean(createdAt && (Date.now() - createdAt) < 1000 * 60 * 60 * 24 * 45)
  const posterUrl = resolvePublicMediaUrl(item.poster, mediaBase, '/placeholder-poster.svg')
  const resolvedBackdrop = resolvePublicMediaUrl(item.backdrop, mediaBase, '')
  const backdropUrl = resolvedBackdrop || (isPlaceholderMedia(posterUrl) ? '/placeholder-poster.svg' : posterUrl)
  const persianTitle = (item.title || '').trim()
  const englishTitle = (item.secondary_title || item.original_title || '').trim()
  const spokenLanguage = (item.language || '').trim()
  const countryLabel = item.countries
    ?.map(country => localizeCountry(country.name, country.code))
    .filter(Boolean)
    .join('، ') || ''
  const directors = item.directors || []
  const isDubbed = Boolean(item.is_dubbed)
  const hasSubtitle = Boolean(item.has_subtitle)

  return {
    id: item.id,
    title: persianTitle || englishTitle,
    secondary_title: englishTitle && englishTitle !== persianTitle ? englishTitle : undefined,
    slug: item.slug,
    original_title: englishTitle || persianTitle,
    description: (item.short_description || '').trim(),
    year: item.release_year || item.start_year || 0,
    duration_minutes: item.duration_minutes || 0,
    genres: normalizeGenres(item.genres),
    country: countryLabel,
    language: spokenLanguage,
    director: directors[0]?.name || '',
    poster_url: posterUrl,
    backdrop_url: backdropUrl,
    trailer_url: '',
    hls_url: '',
    rating: Number.isFinite(rating) ? rating : 0,
    imdb_rating: trustedImdb,
    imdb_rank: (() => {
      const rank = Number(item.imdb_rank)
      return Number.isFinite(rank) && rank >= 1 && rank <= 250 ? Math.trunc(rank) : null
    })(),
    tmdb_rating: trustedTmdb,
    ratings,
    age_rating: normalizeAgeRating(item.age_rating),
    is_uncensored: Boolean(item.is_uncensored),
    has_subtitle: hasSubtitle,
    is_dubbed: isDubbed,
    format: normalizeContentFormat(item.content_format),
    content_warnings: [],
    status: 'published',
    type,
    is_trending: Boolean(item.is_featured)
      || (isRecent && (Number(item.view_count || 0) >= 15 || Number(item.like_count || 0) >= 3)),
    is_recommended: Boolean(item.is_recommended || item.is_featured),
    is_new: isRecent,
    has_artwork: Boolean(item.poster) && !isPlaceholderMedia(posterUrl),
    has_backdrop: Boolean(resolvedBackdrop) && !isPlaceholderMedia(resolvedBackdrop),
    progress_percent: 0,
    popularity: Number(item.popularity || 0),
    view_count: Number(item.view_count || 0),
    like_count: Number(item.like_count || 0),
    cast: [],
    crew: [],
    download_url: null,
    download_links: [],
    quality: item.quality || '',
    has_downloads: Boolean(item.has_downloads),
    download_qualities: item.download_qualities || [],
    seo_title: item.seo_title || persianTitle || englishTitle,
    seo_description: '',
    seo_keywords: [],
    recommendation_reason: item.is_featured ? 'انتخاب ویژه تحریریه' : undefined,
    audio_languages: isDubbed
      ? ['دوبله فارسی', ...(spokenLanguage ? [spokenLanguage] : [])]
      : (spokenLanguage ? [spokenLanguage] : []),
    subtitle_languages: hasSubtitle ? ['فارسی'] : [],
    seasons_count: item.seasons?.length,
    episodes: [],
    created_at: item.created_at || '',
    updated_at: item.updated_at || item.created_at || '',
  }
}

function qualityRank(quality?: string) {
  const raw = String(quality || '').toLowerCase().replace(/\s+/g, '')
  const named: Record<string, number> = {
    '2160p': 60, '4k': 60, uhd: 60,
    '1440p': 50, '2k': 50,
    '1080p': 40, fhd: 40, fullhd: 40,
    '720p': 30, hd: 30,
    '480p': 20, sd: 20,
    '360p': 10, '240p': 5,
  }
  for (const [key, rank] of Object.entries(named)) {
    if (raw.includes(key)) return rank
  }
  const match = raw.match(/(\d{3,4})p?/)
  return match ? Math.max(1, Number(match[1]) / 36) : 0
}
