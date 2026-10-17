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

/** Dornatv/CDN signed URLs self-expire (~13 h) — has this one's token lapsed?
 *
 *  Mirrors `media_probe.signature_expired` on the backend. A lapsed token says
 *  nothing about the file: it is still on the origin and one re-crawl away from
 *  being playable. Treating it as death is what left viewers on «پخش ویدیو ممکن
 *  نشد» for films that were fine — so callers that are about to *play* pass
 *  `ignoreExpiry` and let `usePlaybackResolve` fetch a fresh signature instead.
 */
export function isExpiredPlaybackUrl(url?: string | null) {
  const match = String(url || '').match(/[?&]expires=(\d{9,})/i)
  if (!match) return false
  const expiresSeconds = Number(match[1])
  return Number.isFinite(expiresSeconds) && expiresSeconds * 1000 < Date.now()
}

/** URL is usable as an online progressive/HLS source (non-empty, not a dead Soft CDN, not expired). */
export function isPlayablePlaybackUrl(url?: string | null, options: { ignoreExpiry?: boolean } = {}) {
  const raw = String(url || '').trim()
  if (!raw || isDeadPlaybackHost(raw)) return false
  if (!options.ignoreExpiry && isExpiredPlaybackUrl(raw)) return false
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

interface MediaSourceLike {
  isTypeSupported(type: string): boolean
}

/**
 * Kill switch for the in-page MKV remuxer on Chromium. Chromium opens MKV
 * natively, so it does not need the remuxer and stays on `<video src>` (a
 * tester can opt one browser in with localStorage `revayato:remux` = '1').
 * Safari, every iOS browser and Firefox cannot open MKV at all and the stream
 * gateway cannot reach the provider CDNs, so for them the remuxer is the only
 * way the catalogue plays — switching it off there left them a black player.
 */
const REMUX_ENABLED = false

function remuxOptedIn(): boolean {
  if (REMUX_ENABLED) return true
  // Every iOS browser is WebKit underneath, whatever its UA says (CriOS too).
  if (isSafariLikePlayback() || !isChromiumLikePlayback()) return true
  try {
    return window.localStorage.getItem('revayato:remux') === '1'
  }
  catch {
    return false
  }
}

/**
 * Whether the in-page MKV remuxer (utils/remux/engine) can run here: Media
 * Source — ManagedMediaSource on iOS 17.1+ — with H.264, and streaming fetch.
 */
export function remuxSupported(): boolean {
  if (typeof window === 'undefined') return false
  if (!remuxOptedIn()) return false
  try {
    const w = window as unknown as { ManagedMediaSource?: MediaSourceLike, MediaSource?: MediaSourceLike }
    const ms = w.ManagedMediaSource || w.MediaSource
    if (!ms || typeof fetch !== 'function' || typeof ReadableStream === 'undefined') return false
    return ms.isTypeSupported('video/mp4; codecs="avc1.64001f"')
  }
  catch {
    return false
  }
}

/** Sources the remuxer can take: progressive MKV/WebM over http(s). */
export function isRemuxCandidate(url?: string | null): boolean {
  const raw = String(url || '').trim()
  if (!/^https?:\/\//i.test(raw)) return false
  const path = (raw.split(/[?#]/)[0] || '').toLowerCase()
  return /\.(mkv|webm)$/.test(path)
}

/** Chromium (outside iOS) opens MKV in a plain `<video>`; Safari, iOS and Firefox do not. */
export function browserOpensMkvNatively(): boolean {
  return isChromiumLikePlayback() && !isSafariLikePlayback()
}

/**
 * An Iran-only CDN file (backend `iran_only`: abrtech.top → mehracdn.com) that
 * this browser has no way to play. Those CDNs send no CORS headers, so the
 * in-page remuxer cannot read them, and the gateway sits outside Iran where
 * they answer with a «turn your VPN off» page — which leaves only the browser's
 * own `<video>`, and that cannot open MKV outside Chromium.
 */
export function geoLockedUnplayable(link?: { url?: string | null, iran_only?: boolean } | null): boolean {
  if (!link?.iran_only) return false
  return isRemuxCandidate(link.url) && !browserOpensMkvNatively()
}

/**
 * Browsers that cannot be trusted with an MKV source. Any browser with Media
 * Source can: the player remuxes MKV to MP4 in the page (utils/remux), which
 * covers Safari on macOS and iOS 17.1+ and Firefox. What is left is older iOS
 * and legacy WebViews, which still need MP4/HLS mirrors or the gateway.
 */
export function prefersBrowserSafeContainers() {
  if (!import.meta.client) return false
  try {
    if (remuxSupported()) return false
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

export type VideoCodecFamily = 'hevc' | 'av1' | 'h264' | ''

/**
 * Codec family read from a source URL + quality/label tokens ('' when unknown).
 * Provider filenames embed the codec directly (e.g. ``1080p.x265.10bit``), which
 * is the only reliable signal available before the media element loads.
 */
export function videoCodecFamily(url?: string | null, quality?: string | null, label?: string | null): VideoCodecFamily {
  const blob = `${url || ''} ${quality || ''} ${label || ''}`.toLowerCase()
  if (/(dolby[\s._-]*vision|dovi|\bdvhe\b|\bdvh1\b)/.test(blob)) return 'hevc'
  if (/(\bx265\b|\bh265\b|\bhevc\b|\bhev1\b|\bhvc1\b)/.test(blob)) return 'hevc'
  if (/(\bav1\b|\bav01\b)/.test(blob)) return 'av1'
  if (/(\bx264\b|\bh264\b|\bavc1\b|\bavc\b)/.test(blob)) return 'h264'
  // Standalone 10-bit encodes are virtually always HEVC in these providers.
  if (/\b10bit\b|\b10-bit\b/.test(blob)) return 'hevc'
  return ''
}

let hevcSupport: boolean | null = null
let hevc10Support: boolean | null = null

function probeVideoTypes(variants: string[]) {
  try {
    const probe = document.createElement('video')
    return variants.some((type) => {
      const result = probe.canPlayType(type)
      return result === 'probably' || result === 'maybe'
    })
  } catch {
    return false
  }
}

/**
 * Whether the current browser can decode HEVC/H.265 (Safari + HW-assisted
 * Chromium). `tenBit` asks for Main10: plenty of GPUs decode 8-bit HEVC only,
 * and the provider "x265.10bit" encodes then play sound over a black picture.
 */
export function browserSupportsHevc(tenBit = false): boolean {
  if (!import.meta.client) return false
  if (hevcSupport === null) {
    hevcSupport = probeVideoTypes([
      'video/mp4; codecs="hev1.1.6.L120.90"',
      'video/mp4; codecs="hev1.1.6.L93.B0"',
      'video/mp4; codecs="hvc1.1.6.L120.90"',
      'video/mp4; codecs="hvc1.1.6.L93.B0"',
    ])
  }
  if (!tenBit || !hevcSupport) return hevcSupport
  if (hevc10Support === null) {
    hevc10Support = probeVideoTypes([
      'video/mp4; codecs="hvc1.2.4.L120.90"',
      'video/mp4; codecs="hev1.2.4.L120.90"',
      'video/mp4; codecs="hvc1.2.4.L93.90"',
    ])
  }
  return hevc10Support
}

function isTenBitSource(blob: string) {
  return /\b10[\s._-]?bit\b|\bhdr(10)?\b|dolby[\s._-]*vision|\bdovi\b|\bmain10\b/.test(blob)
}

/**
 * Can this HEVC source actually show a picture here? The canPlayType answer is
 * for HEVC in MP4. Chromium's native player does not decode HEVC out of a
 * Matroska file — the audio plays, the video stays black and no error event
 * ever fires — so an HEVC MKV is only playable through the in-page remuxer.
 */
function hevcPlayable(url?: string | null, quality?: string | null, label?: string | null) {
  const blob = `${url || ''} ${quality || ''} ${label || ''}`.toLowerCase()
  if (!browserSupportsHevc(isTenBitSource(blob))) return false
  const path = (String(url || '').split(/[?#]/)[0] || '').toLowerCase()
  if (/\.(mkv|avi|wmv)$/.test(path)) return remuxSupported() && isRemuxCandidate(url) && mseDecodesHevc(isTenBitSource(blob))
  return true
}

/** The remuxer hands HEVC to Media Source, which has its own codec list. */
function mseDecodesHevc(tenBit: boolean) {
  try {
    const w = window as unknown as { ManagedMediaSource?: MediaSourceLike, MediaSource?: MediaSourceLike }
    const ms = w.ManagedMediaSource || w.MediaSource
    return Boolean(ms?.isTypeSupported(tenBit ? 'video/mp4; codecs="hvc1.2.4.L120.90"' : 'video/mp4; codecs="hvc1.1.6.L93.B0"'))
  }
  catch {
    return false
  }
}

let av1Support: boolean | null = null

/** Whether the current browser can decode AV1. */
export function browserSupportsAv1(): boolean {
  if (!import.meta.client) return false
  if (av1Support !== null) return av1Support
  try {
    const result = document.createElement('video').canPlayType('video/mp4; codecs="av01.0.05M.08"')
    av1Support = result === 'probably' || result === 'maybe'
  } catch {
    av1Support = false
  }
  return av1Support
}

/** True when this source's codec cannot be decoded by the current browser. */
export function codecLikelyUnsupported(url?: string | null, quality?: string | null, label?: string | null): boolean {
  if (!import.meta.client) return false
  const family = videoCodecFamily(url, quality, label)
  if (family === 'hevc') return !hevcPlayable(url, quality, label)
  if (family === 'av1') return !browserSupportsAv1()
  return false
}

function codecScore(url?: string | null, quality?: string | null, label?: string | null): number {
  if (!import.meta.client) return 0
  const family = videoCodecFamily(url, quality, label)
  if (family === 'hevc') return hevcPlayable(url, quality, label) ? 0 : -160
  if (family === 'av1') return browserSupportsAv1() ? 0 : -160
  if (family === 'h264') return 6
  return 0
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
export function pickStreamFriendlyLink<T extends { quality?: string, url: string, label?: string, iran_only?: boolean }>(
  links: readonly T[],
  preferLean: boolean | StreamNetworkProfile = false,
): T | null {
  if (!links.length) return null
  const liveLinks = links.filter(link => isPlayablePlaybackUrl(link.url))
  const pool = liveLinks.length ? liveLinks : links.filter(link => Boolean(String(link.url || '').trim()))
  const mediaLinks = pool.filter(link => !isSubtitleFile(link.url))
  const friendlyLinks = mediaLinks.filter(link => isBrowserFriendlyContainer(link.url))
  // Codec-safe mirrors first: never start on a HEVC/AV1 file the current
  // browser cannot decode (Safari can; Chrome/Firefox usually cannot).
  const codecSafeLinks = mediaLinks.filter(link => !codecLikelyUnsupported(link.url, link.quality, link.label))
  const strict = prefersBrowserSafeContainers()
  // Firefox/Safari: never pick MKV when any MP4/HLS mirror exists in the lane.
  const playableLinks = strict
    ? mediaLinks.filter(link => !progressiveUrlLikelyUnsupported(link.url))
    : mediaLinks
  const candidates = codecSafeLinks.length
    ? codecSafeLinks
    : (friendlyLinks.length ? friendlyLinks : (playableLinks.length ? playableLinks : (mediaLinks.length ? mediaLinks : pool)))
  const leanBias = strict
    ? 'lean'
    : (typeof preferLean === 'string' ? preferLean : (preferLean ? 'lean' : streamNetworkProfile()))
  return [...candidates].sort((a, b) => {
    let scoreA = streamQualityScore(a.quality, leanBias)
    let scoreB = streamQualityScore(b.quality, leanBias)
    scoreA += containerScore(a.url)
    scoreB += containerScore(b.url)
    scoreA += codecScore(a.url, a.quality, a.label)
    scoreB += codecScore(b.url, b.quality, b.label)
    // Prefer live hosts even when the only remaining candidates are dead.
    if (isDeadPlaybackHost(a.url)) scoreA -= 1000
    if (isDeadPlaybackHost(b.url)) scoreB -= 1000
    // Any other mirror beats an Iran-only MKV this browser cannot open.
    if (geoLockedUnplayable(a)) scoreA -= 500
    if (geoLockedUnplayable(b)) scoreB -= 500
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
