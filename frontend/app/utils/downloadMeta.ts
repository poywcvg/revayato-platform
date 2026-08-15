import type { DownloadLink } from '~/types'

function haystack(link: DownloadLink) {
  return [link.season, link.episode, link.label, link.url].filter(Boolean).join(' ')
}

function seasonEpisodeFromUrl(url?: string): { season: number | null, episode: number | null } {
  const raw = String(url || '')
  const sxx = raw.match(/[Ss](\d{1,2})[Ee](\d{1,3})/)
  if (sxx) return { season: Number(sxx[1]), episode: Number(sxx[2]) }
  const alt = raw.match(/(?<![A-Za-z0-9])(\d{1,2})[xX](\d{1,3})(?![A-Za-z0-9])/)
  if (alt) return { season: Number(alt[1]), episode: Number(alt[2]) }
  const pathSeason = raw.match(/(?:^|\/)(?:[Ss](?:eason)?)[._\-\s]?0*(\d{1,2})(?:\/|$)/i)
  return { season: pathSeason ? Number(pathSeason[1]) : null, episode: null }
}

/** Parse season number from structured fields or Persian/English labels. */
export function seasonNumberOf(link: DownloadLink): number | null {
  if (typeof link.season_number === 'number' && Number.isFinite(link.season_number) && link.season_number > 0) {
    return link.season_number
  }
  const fromSeason = String(link.season || '').match(/(?:فصل|season)\s*([0-9]{1,3})/i)?.[1]
    || String(link.season || '').match(/^([0-9]{1,3})$/)?.[1]
  if (fromSeason) return Number(fromSeason)
  const fromLabel = haystack(link).match(/(?:فصل|season)\s*([0-9]{1,3})/i)?.[1]
  if (fromLabel) return Number(fromLabel)
  return seasonEpisodeFromUrl(link.url).season
}

/** Parse episode number from structured fields or Persian/English labels. */
export function episodeNumberOf(link: DownloadLink): number {
  if (typeof link.episode_number === 'number' && Number.isFinite(link.episode_number) && link.episode_number > 0) {
    return link.episode_number
  }
  const fromEpisode = String(link.episode || '').match(/(?:قسمت|episode)\s*([0-9]{1,3})/i)?.[1]
    || String(link.episode || '').match(/^([0-9]{1,3})$/)?.[1]
  if (fromEpisode) return Number(fromEpisode)
  const fromLabel = haystack(link).match(/(?:قسمت|episode)\s*([0-9]{1,3})/i)?.[1]
  if (fromLabel) return Number(fromLabel)
  return seasonEpisodeFromUrl(link.url).episode || 0
}

export function linkMatchesEpisode(
  link: DownloadLink,
  seasonNumber: number | null | undefined,
  episodeNumber: number | null | undefined,
) {
  if (!episodeNumber) return true
  const season = seasonNumber ?? 1
  const linkSeason = seasonNumberOf(link) ?? 1
  const linkEpisode = episodeNumberOf(link)
  if (!linkEpisode) return false
  return linkSeason === season && linkEpisode === episodeNumber
}

export function qualityRank(quality?: string) {
  const raw = String(quality || '').toLowerCase()
  if (raw.includes('2160') || raw.includes('4k')) return 50
  if (raw.includes('1080') || raw.includes('fhd')) return 40
  if (raw.includes('720') || raw.includes('hd')) return 30
  if (raw.includes('480')) return 20
  if (raw.includes('360')) return 10
  return 5
}

export type StreamNetworkProfile = 'lean' | 'balanced' | 'fast'

/**
 * Score a progressive download link for online playback.
 * Lean → 360/480 first; balanced → ~480; fast (Wi‑Fi / strong 4G) → 720 for smoother HD start.
 * Avoid 1080/4K as the auto start rung — those come via buffer-health upgrade.
 */
export function streamQualityScore(
  quality?: string,
  preferLean: boolean | StreamNetworkProfile = false,
) {
  const profile: StreamNetworkProfile = preferLean === true
    ? 'lean'
    : preferLean === false
      ? 'balanced'
      : preferLean
  const rank = qualityRank(quality)
  if (profile === 'lean') {
    if (rank >= 50) return 6
    if (rank >= 40) return 12
    if (rank >= 30) return 22
    if (rank >= 20) return 40
    if (rank >= 10) return 34
    return 14
  }
  if (profile === 'fast') {
    // Strong networks: start at 720 for clearer picture with still-fast buffer fill.
    if (rank >= 50) return 12
    if (rank >= 40) return 22
    if (rank >= 30) return 44
    if (rank >= 20) return 36
    if (rank >= 10) return 20
    return 12
  }
  // Balanced: 480 first (fast download), then 720, then heavier rungs.
  if (rank >= 50) return 10
  if (rank >= 40) return 18
  if (rank >= 30) return 34
  if (rank >= 20) return 42
  if (rank >= 10) return 26
  return 12
}

function isSubtitleFile(url: string) {
  return /\.(vtt|webvtt|srt|ass|ssa)($|\?)/i.test(url)
}

/** Hosts that fail browser-compatible TLS/range probes — never select for online play. */
const DEAD_PLAYBACK_HOST_MARKERS = ['cdnhost.lol', 'dlyar.top'] as const

/** True when the CDN host is known-dead for progressive online playback. */
export function isDeadPlaybackHost(url?: string | null) {
  const raw = String(url || '').trim().toLowerCase()
  if (!raw) return false
  try {
    const host = new URL(raw, 'https://revayato.invalid').hostname
    return DEAD_PLAYBACK_HOST_MARKERS.some(marker => host === marker || host.endsWith(`.${marker}`))
  } catch {
    return DEAD_PLAYBACK_HOST_MARKERS.some(marker => raw.includes(marker))
  }
}

/** URL is usable as an online progressive/HLS source (non-empty, not a dead Soft CDN). */
export function isPlayablePlaybackUrl(url?: string | null) {
  const raw = String(url || '').trim()
  if (!raw || isDeadPlaybackHost(raw)) return false
  try {
    const parsed = new URL(raw, 'https://revayato.invalid')
    if (!['http:', 'https:'].includes(parsed.protocol)) return false
  } catch {
    return false
  }
  const path = raw.split(/[?#]/, 1)[0]?.toLowerCase() || ''
  if (/\.(vtt|webvtt|srt|ass|ssa|sub|aac|mka|mp3|wav|flac|jpe?g|png|webp|gif|zip|rar|7z|pdf|txt|html?)$/i.test(path)) return false
  if (/\.(mp4|m4v|webm|mkv|m3u8).+$/i.test(path)) return false
  return true
}

function getUserAgent() {
  if (!import.meta.client) return ''
  try { return navigator.userAgent || '' } catch { return '' }
}

function getVendor() {
  if (!import.meta.client) return ''
  try { return navigator.vendor || '' } catch { return '' }
}

/**
 * Safari / iOS struggle with progressive MKV Soft/Hard encodes in ``<video>``.
 */
export function isSafariLikePlayback() {
  if (!import.meta.client) return false
  try {
    const ua = getUserAgent()
    const iOS = /iPad|iPhone|iPod/i.test(ua)
      || (navigator.platform === 'MacIntel' && (navigator.maxTouchPoints || 0) > 1)
    const safariDesktop = /Safari/i.test(ua)
      && !/Chrome|Chromium|CriOS|Edg|EdgiOS|OPR|Firefox|FxiOS|Android/i.test(ua)
    return iOS || safariDesktop
  } catch {
    return false
  }
}

/** Chromium-based browsers (Chrome, Edge, Opera, Brave, Samsung Internet) usually demux MKV. */
export function isChromiumLikePlayback() {
  const ua = getUserAgent()
  const vendor = getVendor()
  return /Chrome|Chromium|CriOS|Edg|EdgiOS|OPR/i.test(ua) || vendor.includes('Google')
}

/** Browsers whose engines are known to have incomplete MKV/AVI/WMV demux support. */
export function prefersBrowserSafeContainers() {
  if (!import.meta.client) return false
  try {
    if (isSafariLikePlayback()) return true
    if (/Firefox|FxiOS/i.test(getUserAgent())) return true
    // Conservative default for unknown/legacy UAs (e.g., old WebView, UC, Dolphin).
    if (!isChromiumLikePlayback()) return true
    return false
  } catch {
    return true
  }
}

/** True when this progressive URL is unlikely to play in the current browser. */
export function progressiveUrlLikelyUnsupported(url?: string | null) {
  if (!prefersBrowserSafeContainers()) return false
  const raw = String(url || '').split('?')[0]?.toLowerCase() || ''
  return /\.(mkv|avi|wmv)$/i.test(raw)
}

function isBrowserFriendlyContainer(url: string) {
  return /\.(m3u8|mp4|m4v|webm)($|[?#])/i.test(url)
}

function containerScore(url: string) {
  const strict = prefersBrowserSafeContainers()
  if (/\.m3u8($|[?#])/i.test(url)) return strict ? 48 : 24
  if (/\.mp4($|[?#])/i.test(url)) return strict ? 42 : 18
  if (/\.m4v($|[?#])/i.test(url)) return strict ? 36 : 14
  if (/\.webm($|[?#])/i.test(url)) return strict ? 20 : 8
  // Progressive MKV is the catalog default — fine on Chromium, weak on Firefox/Safari.
  if (/\.(mkv|avi|wmv)($|[?#])/i.test(url)) return strict ? -120 : -28
  return 0
}

/**
 * Pick the fastest browser-safe source for the current network profile.
 * When a native streaming container exists, avoid MKV/AVI even if its quality
 * label scores higher — codec probing and failed fallback cost more than a rung.
 * Known-dead Soft CDN hosts are skipped so Hard/Dub live mirrors win.
 */
export function pickStreamFriendlyLink<T extends { quality?: string, url: string }>(
  links: readonly T[],
  preferLean: boolean | StreamNetworkProfile = false,
): T | null {
  if (!links.length) return null
  const liveLinks = links.filter(link => isPlayablePlaybackUrl(link.url))
  const pool = liveLinks.length ? liveLinks : links.filter(link => Boolean(String(link.url || '').trim()))
  const mediaLinks = pool.filter(link => !isSubtitleFile(link.url))
  const friendlyLinks = mediaLinks.filter(link => isBrowserFriendlyContainer(link.url))
  const strict = prefersBrowserSafeContainers()
  // Firefox/Safari: never pick MKV when any MP4/HLS mirror exists in the lane.
  const playableLinks = strict
    ? mediaLinks.filter(link => !progressiveUrlLikelyUnsupported(link.url))
    : mediaLinks
  const candidates = friendlyLinks.length
    ? friendlyLinks
    : (playableLinks.length ? playableLinks : (mediaLinks.length ? mediaLinks : pool))
  const leanBias = strict
    ? 'lean'
    : (typeof preferLean === 'string' ? preferLean : (preferLean ? 'lean' : streamNetworkProfile()))
  return [...candidates].sort((a, b) => {
    let scoreA = streamQualityScore(a.quality, leanBias)
    let scoreB = streamQualityScore(b.quality, leanBias)
    scoreA += containerScore(a.url)
    scoreB += containerScore(b.url)
    // Prefer live hosts even when the only remaining candidates are dead.
    if (isDeadPlaybackHost(a.url)) scoreA -= 1000
    if (isDeadPlaybackHost(b.url)) scoreB -= 1000
    return scoreB - scoreA
  })[0] || null
}

/** Return an external playback origin suitable for resource hints. */
export function playbackOrigin(url?: string | null) {
  const raw = String(url || '').trim()
  if (!raw) return ''
  try {
    const parsed = new URL(raw, 'https://revayato.invalid')
    return parsed.hostname === 'revayato.invalid' ? '' : parsed.origin
  } catch {
    return ''
  }
}

/** Warm DNS/TLS before the media element starts following CDN redirects. */
export function warmPlaybackOrigin(url?: string | null) {
  if (!import.meta.client) return
  const origin = playbackOrigin(url)
  if (!origin || origin === window.location.origin) return
  const normalizedOrigin = origin.replace(/\/$/, '')
  const hasPreconnect = [...document.querySelectorAll<HTMLLinkElement>('link[rel="preconnect"]')]
    .some(link => link.href.replace(/\/$/, '') === normalizedOrigin)
  if (!hasPreconnect) {
    const preconnect = document.createElement('link')
    preconnect.rel = 'preconnect'
    preconnect.href = origin
    preconnect.crossOrigin = 'anonymous'
    preconnect.dataset.playbackOrigin = origin
    document.head.appendChild(preconnect)
  }
  const hasDnsPrefetch = [...document.querySelectorAll<HTMLLinkElement>('link[rel="dns-prefetch"]')]
    .some(link => link.href.replace(/\/$/, '') === normalizedOrigin)
  if (!hasDnsPrefetch) {
    const dns = document.createElement('link')
    dns.rel = 'dns-prefetch'
    dns.href = origin
    dns.dataset.playbackDns = origin
    document.head.appendChild(dns)
  }
}

/** Height parsed from quality label / URL (0 when unknown). */
export function qualityHeightOf(quality?: string, url?: string) {
  const fromLabel = String(quality || '').match(/(\d{3,4})/)
  const fromUrl = String(url || '').match(/(\d{3,4})p\b/i)
  const height = Number(fromLabel?.[1] || fromUrl?.[1] || 0)
  return height >= 240 && height <= 4320 ? height : 0
}

type NavigatorConnection = {
  saveData?: boolean
  effectiveType?: string
  downlink?: number
  rtt?: number
}

function readConnection(): NavigatorConnection | null {
  if (!import.meta.client) return null
  try {
    return (navigator as Navigator & { connection?: NavigatorConnection }).connection || null
  } catch {
    return null
  }
}

/** Network hint: lean start when the connection is constrained. */
export function prefersLeanStreamNetwork() {
  return streamNetworkProfile() === 'lean'
}

/**
 * Classify the client network for adaptive start quality.
 * lean → constrained; balanced → typical mobile; fast → Wi‑Fi / strong 4G+.
 */
export function streamNetworkProfile(): StreamNetworkProfile {
  const connection = readConnection()
  if (!connection) return 'balanced'
  if (connection.saveData) return 'lean'
  const type = connection.effectiveType || ''
  if (type === '2g' || type === 'slow-2g' || type === '3g') return 'lean'
  const downlink = typeof connection.downlink === 'number' ? connection.downlink : 0
  const rtt = typeof connection.rtt === 'number' ? connection.rtt : 0
  if (downlink > 0 && downlink < 2.5) return 'lean'
  if (rtt > 0 && rtt > 450) return 'lean'
  // Strong pipe: start closer to HD for fewer quality jumps and clearer picture.
  if (downlink >= 8 || (type === '4g' && downlink >= 5)) return 'fast'
  return 'balanced'
}

/** Rough ABR bandwidth estimate (bits/sec) from Network Information API. */
export function estimatedBandwidthBps() {
  const connection = readConnection()
  if (!connection) return 0
  const downlink = typeof connection.downlink === 'number' ? connection.downlink : 0
  if (downlink <= 0) return 0
  // downlink is Mbps; keep a safety margin so ABR does not overshoot.
  return Math.round(downlink * 1_000_000 * 0.7)
}
