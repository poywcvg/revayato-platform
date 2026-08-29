<script setup lang="ts">
import type { ContentType, DownloadLink, Episode, PlaybackEpisodeOption, PlaybackQuality, PlaybackTextTrack, PlaybackVersion, PlaybackVersionKind } from '~/types'
import { episodeNumberOf, isPlayablePlaybackUrl, linkMatchesEpisode, pickStreamFriendlyLink, playbackOrigin, prefersBrowserSafeContainers, qualityHeightOf, seasonNumberOf, streamNetworkProfile, warmPlaybackOrigin } from '~/utils/downloadMeta'
import { buildPlaybackVersions, isDubLink, isSoftsubLink, linksForVersionKind, pairSubtitleTracksForSource, resolvePlaybackVersion } from '~/utils/playbackVersions'
import { classifyPlayerToast, type PlayerToastMeta } from '~/utils/playerToast'
import { pickDefaultPlaybackVersion, softsubBannerCopy, subtitleFindingNotice, subtitleReadyNotice, type SoftsubBannerTone } from '~/utils/subtitlePolicy'

definePageMeta({ layout: 'player', pageTransition: false })

const route = useRoute()
const router = useRouter()
const slug = computed(() => String(route.params.slug))
const { catalog, loadItemFromApi } = useCatalog()
const initialItem = catalog.value.find(candidate => candidate.slug === slug.value)
const requestedType = route.query.type === 'movie' || route.query.type === 'series'
  ? route.query.type as ContentType
  : initialItem?.type

if (requestedType) await loadItemFromApi(slug.value, requestedType)
else if (!await loadItemFromApi(slug.value, 'movie')) await loadItemFromApi(slug.value, 'series')

const item = computed(() => catalog.value.find(candidate => candidate.slug === slug.value) ?? null)
const { trackTrailerPlay, trackWatchProgress } = useAnalyticsEvent()
const watchProgress = useWatchProgress()
const { ensurePlaybackSubtitles, getPlaybackSubtitleStatus } = usePlaybackSubtitleEnsure()

if (!item.value) throw createError({ statusCode: 404, message: 'محتوا پیدا نشد' })

const mode = computed(() => route.query.mode === 'trailer' ? 'trailer' : 'full')
const restricted = computed(() => item.value?.age_rating === '18+')
const confirmed = ref(!restricted.value || route.query.confirmed === '1')
const modalOpen = ref(restricted.value && !confirmed.value)
const detailPath = computed(() => `/${item.value?.type === 'movie' ? 'movies' : 'series'}/${item.value?.slug}`)

const orderedEpisodes = computed(() => [...(item.value?.episodes || [])].sort(
  (a, b) => (a.season_number || 1) - (b.season_number || 1) || a.episode_number - b.episode_number,
))
const requestedEpisodeId = computed(() => Number(route.query.episode) || 0)

const sourceLink = computed(() => {
  const source = String(route.query.source || '').trim()
  if (!source) return null
  return (item.value?.download_links || []).find(link => String(link.url || '').trim() === source) || null
})

const currentEpisode = computed(() => {
  if (requestedEpisodeId.value) {
    const byId = orderedEpisodes.value.find(episode => episode.id === requestedEpisodeId.value)
    if (byId) return byId
  }
  const savedEpisodeId = watchProgress.entries.value.find(entry => (
    entry.content_type === 'series' && entry.object_id === item.value?.id
  ))?.episode_id
  if (savedEpisodeId) {
    const saved = orderedEpisodes.value.find(episode => episode.id === savedEpisodeId)
    if (saved) return saved
  }
  if (sourceLink.value) {
    const season = seasonNumberOf(sourceLink.value) ?? 1
    const episodeNo = episodeNumberOf(sourceLink.value)
    if (episodeNo) {
      const byMeta = orderedEpisodes.value.find(episode => (
        (episode.season_number || 1) === season && episode.episode_number === episodeNo
      ))
      if (byMeta) return byMeta
    }
  }
  return orderedEpisodes.value.find(episode => (episode.progress_percent || 0) > 0 && !episode.is_watched)
    || orderedEpisodes.value.find(episode => !episode.is_watched)
    || orderedEpisodes.value[0]
})

const streamLinks = computed<DownloadLink[]>(() => {
  const links = item.value?.download_links || []
  const seen = new Set<string>()
  const filtered = links.filter((link) => {
    const key = `${(link.quality || '').toLowerCase()}|${(link.kind || '').toLowerCase()}|${link.url}`
    if (!link.url || seen.has(key)) return false
    seen.add(key)
    return true
  })
  // Prefer live CDNs for online play; keep dead Soft mirrors only if nothing else exists.
  const live = filtered.filter(link => isPlayablePlaybackUrl(link.url))
  return live.length ? live : filtered
})

/** Keep playback/quality choices on the same episode so series never jumps mid-play. */
const episodeScopedLinks = computed(() => {
  if (item.value?.type !== 'series' || !currentEpisode.value) return streamLinks.value
  const season = currentEpisode.value.season_number || 1
  const episodeNo = currentEpisode.value.episode_number
  const scoped = streamLinks.value.filter(link => linkMatchesEpisode(link, season, episodeNo))
  if (scoped.length) return scoped
  // Prefer the episode's own stream over the full series pool (avoids cross-episode bleed).
  if (sourceLink.value && linkMatchesEpisode(sourceLink.value, season, episodeNo)) return [sourceLink.value]
  const episodeHls = String(currentEpisode.value.hls_url || '').trim()
  if (isPlayablePlaybackUrl(episodeHls)) {
    return [{
      label: `قسمت ${episodeNo}`,
      url: episodeHls,
      quality: '',
      season_number: season,
      episode_number: episodeNo,
    }]
  }
  return []
})

const fallbackUrl = computed(() => {
  // A series-level fallback often points to S01E01. Never let it bleed into a
  // different selected episode; only episode-scoped sources are safe there.
  const candidates = item.value?.type === 'series'
    ? [currentEpisode.value?.hls_url, episodeScopedLinks.value[0]?.url]
    : [
        item.value?.playback?.signed_playback_url,
        item.value?.playback?.hls_url,
        item.value?.hls_url,
      ]
  return candidates.find(url => isPlayablePlaybackUrl(url)) || ''
})

/** Episode SoftSub WebVTT first, then title-level tracks filtered to this episode. */
const activeSubtitleSourceTracks = computed(() => {
  const episodeTracks = currentEpisode.value?.subtitle_tracks || []
  if (episodeTracks.length) return episodeTracks

  // Standalone SoftSub sidecar files scoped to this episode (series) or any (movie).
  const sidecarTracks = episodeScopedLinks.value
    .filter(link => isSoftsubLink(link) && /\.(vtt|webvtt|srt|ass|ssa)($|\?)/i.test(String(link.url || '')))
    .map((link, index) => ({
      id: `fa-sidecar-${index}`,
      label: 'فارسی',
      language: 'fa',
      src: link.url,
      default: index === 0,
      source_url: link.url,
      season_number: typeof link.season_number === 'number' ? link.season_number : undefined,
      episode_number: typeof link.episode_number === 'number' ? link.episode_number : undefined,
    }))
  if (sidecarTracks.length) return sidecarTracks

  const all = item.value?.playback?.subtitle_tracks || []
  if (!all.length) return []

  const season = currentEpisode.value?.season_number
    ?? (sourceLink.value ? seasonNumberOf(sourceLink.value) : null)
    ?? null
  const episodeNo = currentEpisode.value?.episode_number
    ?? (sourceLink.value ? episodeNumberOf(sourceLink.value) : null)
    ?? null

  if (season != null && episodeNo) {
    const matched = all.filter(track => (
      Number(track.season_number || 0) === Number(season)
      && Number(track.episode_number || 0) === Number(episodeNo)
    ))
    if (matched.length) return matched
  }

  // Movies / single-title SoftSub only. Never reuse unlabeled series tracks
  // across episodes — that desyncs cue timelines.
  if (item.value?.type === 'movie') return all
  return []
})

const playbackVersions = computed(() =>
  buildPlaybackVersions(
    episodeScopedLinks.value,
    activeSubtitleSourceTracks.value,
    fallbackUrl.value,
  ),
)

/** Route sources are trusted only when they belong to the selected episode. */
const activeRouteSource = computed(() => {
  const queried = String(route.query.source || '').trim()
  if (!queried || !isPlayablePlaybackUrl(queried)) return ''
  if (item.value?.type !== 'series' || !currentEpisode.value) return queried
  return episodeScopedLinks.value.some(link => link.url === queried) ? queried : ''
})

const sourceMatchedKind = computed(() => {
  const matched = episodeScopedLinks.value.find(link => link.url === activeRouteSource.value)
  if (!matched) return ''
  if (isDubLink(matched)) return 'dub'
  if (isSoftsubLink(matched)) return 'softsub'
  return 'original'
})

const activeVersion = computed(() =>
  resolvePlaybackVersion(
    playbackVersions.value,
    activeRouteSource.value,
    String(route.query.version || sourceMatchedKind.value || ''),
  ),
)

const playerSource = computed(() => {
  if (mode.value === 'trailer') return item.value?.trailer_url || ''
  return activeVersion.value?.url
    || activeRouteSource.value
    || fallbackUrl.value
    || episodeScopedLinks.value[0]?.url
    || ''
})

const playerSourceQuality = computed(() => {
  const sourceLink = episodeScopedLinks.value.find(link => link.url === playerSource.value)
  const raw = sourceLink?.quality || activeVersion.value?.quality || ''
  const height = qualityHeightOf(raw, playerSource.value)
  return height ? `${height}p` : raw
})

const playerSourceOrigin = computed(() => playbackOrigin(playerSource.value))
useHead(() => {
  const origin = playerSourceOrigin.value
  if (!origin) return {}
  return {
    link: [
      { rel: 'preconnect', href: origin, crossorigin: 'anonymous' },
      { rel: 'dns-prefetch', href: origin },
    ],
  }
})

/** Re-pair SoftSub VTT against the exact URL being played (quality switches stay in sync). */
const activeSubtitleTracks = computed(() => {
  if (mode.value === 'trailer') return []
  const version = activeVersion.value
  // Burned-in HardSub with no sidecar VTT — nothing to attach as text tracks.
  // If WebVTT already exists on the version, keep serving it (HardSub-only catalogs).
  if (!version) return []
  if (version.burnedInSubtitles && !version.subtitleTracks.length) return []
  const softPool = linksForVersionKind(episodeScopedLinks.value, 'softsub')
  const pool = softPool.length ? softPool : episodeScopedLinks.value
  const paired = pairSubtitleTracksForSource(
    activeSubtitleSourceTracks.value,
    playerSource.value,
    pool,
  )
  if (paired.length) return paired
  // SoftSub lane: keep extracted WebVTT after CDN host/quality drift.
  if (version.kind === 'softsub' && activeSubtitleSourceTracks.value.length) {
    return [...activeSubtitleSourceTracks.value]
  }
  if (version.subtitleTracks.length) return [...version.subtitleTracks]
  // Dub-only catalogs (SubtitleStar / extracted VTT, no Soft encode): still show cues online.
  if (activeSubtitleSourceTracks.value.length && !softPool.length) {
    return [...activeSubtitleSourceTracks.value]
  }
  return []
})

const resumeProgress = computed(() => {
  if (mode.value === 'trailer' || !item.value) return 0
  const local = watchProgress.progressFor(item.value.id, item.value.type, currentEpisode.value?.id)
  const fromItem = currentEpisode.value?.progress_percent
    ?? (item.value.type === 'series' ? 0 : item.value.progress_percent)
    ?? 0
  return Math.min(95, Math.max(0, local || fromItem))
})
const resumeSeconds = computed(() => {
  if (mode.value === 'trailer' || !item.value) return 0
  return watchProgress.resumeFor(item.value.id, item.value.type, currentEpisode.value?.id)?.position_seconds || 0
})
const selectedQuality = ref<PlaybackQuality>('auto')
const playerToast = ref<(PlayerToastMeta & { id: number, message: string }) | null>(null)
const softsubBanner = ref<{ tone: SoftsubBannerTone, title: string, detail: string } | null>(null)
const shouldAutoplay = computed(() => route.query.player === '1' || Boolean(route.query.source) || confirmed.value)
let toastTimer: number | undefined
let softsubBannerTimer: number | undefined
let softsubPollTimer: number | undefined
let softsubRetryTimer: number | undefined
let softsubReportId: number | null = null
let softsubEnsureRounds = 0
const SOFTSUB_ENSURE_MAX_ROUNDS = 4
let autoUpgradeDone = false
let toastSeq = 0
const failedPlaybackSources = new Set<string>()

const playbackEpisodes = computed<PlaybackEpisodeOption[]>(() => orderedEpisodes.value.map(episode => ({
  id: episode.id,
  title: episode.title || `قسمت ${episode.episode_number.toLocaleString('fa-IR')}`,
  season_number: episode.season_number || 1,
  episode_number: episode.episode_number,
  duration_minutes: episode.duration_minutes || undefined,
  thumbnail_url: episode.thumbnail_url,
})))

function kindForLink(link: DownloadLink | null | undefined, fallback: PlaybackVersionKind): PlaybackVersionKind {
  if (!link) return fallback
  if (isDubLink(link)) return 'dub'
  if (isSoftsubLink(link)) return 'softsub'
  return 'original'
}

function pickEpisodeSource(episode: Episode) {
  const season = episode.season_number || 1
  const episodeNo = episode.episode_number
  const links = streamLinks.value.filter(link => linkMatchesEpisode(link, season, episodeNo))
  const preferredKind = activeVersion.value?.kind || 'original'
  const sameVersion = linksForVersionKind(links, preferredKind)
  let candidates = sameVersion.length ? sameVersion : links

  const currentHeight = qualityHeightOf(playerSourceQuality.value, playerSource.value)
  const requestedHeight = selectedQuality.value === 'auto'
    ? currentHeight
    : qualityHeightOf(selectedQuality.value)
  if (requestedHeight) {
    const sameQuality = candidates.filter(link => qualityHeightOf(link.quality, link.url) === requestedHeight)
    if (sameQuality.length) candidates = sameQuality
  }

  const picked = pickBestLink(candidates)
  const fallbackUrl = isPlayablePlaybackUrl(episode.hls_url) ? String(episode.hls_url) : ''
  const fallbackLink = fallbackUrl
    ? (links.find(link => link.url === fallbackUrl) || ({ url: fallbackUrl, label: episode.title } as DownloadLink))
    : null
  const selected = picked || fallbackLink
  return {
    url: selected?.url || '',
    kind: kindForLink(selected, preferredKind),
  }
}

function selectEpisode(episode: Episode | PlaybackEpisodeOption, notice = '') {
  if (!item.value || item.value.type !== 'series') return
  const fullEpisode = orderedEpisodes.value.find(candidate => candidate.id === episode.id)
  if (!fullEpisode || fullEpisode.id === currentEpisode.value?.id) return
  const selected = pickEpisodeSource(fullEpisode)
  clearSoftsubPoll()
  clearSoftsubBanner()
  resetSoftsubRetry()
  failedPlaybackSources.clear()
  autoUpgradeDone = false
  void router.replace({
    query: {
      ...route.query,
      episode: String(fullEpisode.id),
      source: selected.url || undefined,
      version: selected.kind,
      player: '1',
    },
  })
  if (notice) showPlayerNotice(notice, 3600)
}

function confirmPlayback() {
  confirmed.value = true
  modalOpen.value = false
  void router.replace({ query: { ...route.query, confirmed: '1' } })
}

function leavePlayer() {
  modalOpen.value = false
  void navigateTo(detailPath.value)
}

function showPlayerNotice(message: string, durationMs = 2800) {
  const text = String(message || '').trim()
  if (!text) return
  const meta = classifyPlayerToast(text)
  toastSeq += 1
  playerToast.value = { id: toastSeq, message: text, ...meta }
  if (toastTimer) window.clearTimeout(toastTimer)
  if (durationMs <= 0) {
    toastTimer = undefined
    return
  }
  toastTimer = window.setTimeout(() => {
    if (playerToast.value?.id === toastSeq) playerToast.value = null
  }, durationMs)
}

function dismissPlayerToast() {
  if (toastTimer) window.clearTimeout(toastTimer)
  toastTimer = undefined
  playerToast.value = null
}

function showSoftsubBanner(tone: SoftsubBannerTone, durationMs = 0) {
  const copy = softsubBannerCopy(tone)
  softsubBanner.value = { tone, title: copy.title, detail: copy.detail }
  if (softsubBannerTimer) window.clearTimeout(softsubBannerTimer)
  if (durationMs <= 0) {
    softsubBannerTimer = undefined
    return
  }
  softsubBannerTimer = window.setTimeout(() => {
    softsubBanner.value = null
  }, durationMs)
}

function clearSoftsubBanner() {
  if (softsubBannerTimer) window.clearTimeout(softsubBannerTimer)
  softsubBannerTimer = undefined
  softsubBanner.value = null
}

function qualityMatches(linkQuality: string | undefined, target: PlaybackQuality) {
  if (target === 'auto') return false
  const raw = String(linkQuality || '').toLowerCase()
  return raw.includes(target.toLowerCase()) || raw.includes(target.replace('p', ''))
}

function versionScopedLinks() {
  const kind = activeVersion.value?.kind
  const pool = episodeScopedLinks.value
  if (!kind || !pool.length) return pool
  const scoped = linksForVersionKind(pool, kind)
  return scoped.length ? scoped : pool
}

const playerQualities = computed<PlaybackQuality[]>(() => {
  const qualities = new Set<PlaybackQuality>()
  for (const link of versionScopedLinks()) {
    const height = qualityHeightOf(link.quality, link.url)
    if (height) qualities.add(`${height}p`)
  }
  return [...qualities].sort((a, b) => Number.parseInt(b, 10) - Number.parseInt(a, 10))
})

function pickBestLink(links: DownloadLink[]) {
  return pickStreamFriendlyLink(links, streamNetworkProfile())
}

function pickUpgradeLink(links: DownloadLink[], currentUrl: string) {
  const currentHeight = qualityHeightOf(
    links.find(link => link.url === currentUrl)?.quality,
    currentUrl,
  ) || 0
  const profile = streamNetworkProfile()
  // After a healthy buffer, step up one rung. Fast networks may climb to 1080.
  let target = 0
  if (currentHeight > 0 && currentHeight < 720) target = 720
  else if (profile === 'fast' && currentHeight >= 700 && currentHeight < 1000) target = 1080
  if (!target) return null
  const min = target - 80
  const max = target + 80
  const candidates = links
    .map(link => ({ link, height: qualityHeightOf(link.quality, link.url) }))
    .filter(entry => entry.height >= min && entry.height <= max && entry.link.url !== currentUrl)
    .sort((a, b) => Math.abs(a.height - target) - Math.abs(b.height - target))
  return candidates[0]?.link || null
}

function applySource(url: string, notice?: string) {
  if (!url || url === playerSource.value) return
  void router.replace({
    query: {
      ...route.query,
      source: url,
      version: activeVersion.value?.kind || route.query.version,
      episode: currentEpisode.value?.id ? String(currentEpisode.value.id) : route.query.episode,
      player: '1',
    },
  })
  if (notice) showPlayerNotice(notice)
}

function ensureFastStartSource() {
  if (mode.value === 'trailer' || selectedQuality.value !== 'auto') return
  if (/\.m3u8(?:\?|$)/i.test(playerSource.value)) return
  const links = versionScopedLinks().filter(link => (
    !/\.(vtt|webvtt|srt|ass|ssa)($|\?)/i.test(link.url)
    && !failedPlaybackSources.has(link.url)
  ))
  if (!links.length) return
  const preferred = pickBestLink(links)
  if (!preferred?.url) return
  if (preferred.url === playerSource.value) return
  const currentHeight = qualityHeightOf(
    links.find(link => link.url === playerSource.value)?.quality,
    playerSource.value,
  )
  const preferredHeight = qualityHeightOf(preferred.quality, preferred.url)
  const profile = streamNetworkProfile()
  // Firefox/Safari: jump immediately to the friendliest container/quality.
  if (prefersBrowserSafeContainers()) {
    applySource(preferred.url)
    return
  }
  // Rewrite heavy deep-links to the network-aware fast-start rung while Auto is on.
  const heavyThreshold = profile === 'fast' ? 1100 : 900
  if (currentHeight >= heavyThreshold && preferredHeight && preferredHeight < currentHeight) {
    applySource(preferred.url)
  }
}

function handleSourceFailed(payload: { src: string, code: number }) {
  const failed = String(payload?.src || playerSource.value || '').trim()
  if (failed) failedPlaybackSources.add(failed)
  // A network timeout/stall is an origin-level failure. Cycling through six
  // qualities on the same unreachable CDN only turns a 10s deadline into a
  // minute-long spinner, so prefer another mirror immediately.
  if (failed && Number(payload?.code) === 2) {
    try {
      const failedHost = new URL(failed).host.toLowerCase()
      for (const link of episodeScopedLinks.value) {
        if (link.url && new URL(link.url).host.toLowerCase() === failedHost) {
          failedPlaybackSources.add(link.url)
        }
      }
    } catch { /* malformed URLs are already rejected by normal filtering */ }
  }
  const notFailed = (link: DownloadLink) => (
    Boolean(link.url)
    && !failedPlaybackSources.has(link.url)
    && !/\.(vtt|webvtt|srt|ass|ssa)($|\?)/i.test(link.url)
  )
  const scoped = versionScopedLinks().filter(notFailed)
  const broader = episodeScopedLinks.value.filter(notFailed)
  // Prefer browser-safe containers first (MP4/HLS), then any remaining mirror.
  const next = pickBestLink(scoped)
    || pickBestLink(broader)
    || pickStreamFriendlyLink(scoped, streamNetworkProfile())
    || pickStreamFriendlyLink(broader, streamNetworkProfile())
  if (next?.url && next.url !== playerSource.value) {
    applySource(next.url, 'منبع سازگارتر برای این مرورگر فعال شد')
    return
  }
  if (prefersBrowserSafeContainers() && /\.mkv(?:\?|$)/i.test(failed)) {
    showPlayerNotice('فایرفاکس/سافاری فایل MKV را پخش نمی‌کند. کیفیت MP4 را از تنظیمات بزن یا از Chrome استفاده کن.')
    return
  }
  showPlayerNotice('این مرورگر این فایل را پخش نکرد. کیفیت یا نسخه دیگری را از تنظیمات انتخاب کن.')
}

function handleBufferHealth(aheadSeconds: number) {
  if (autoUpgradeDone || selectedQuality.value !== 'auto' || mode.value === 'trailer') return
  if (/\.m3u8(?:\?|$)/i.test(playerSource.value)) return
  const profile = streamNetworkProfile()
  const threshold = profile === 'fast' ? 14 : profile === 'lean' ? 28 : 20
  if (aheadSeconds < threshold) return
  const links = versionScopedLinks().filter(link => !/\.(vtt|webvtt|srt|ass|ssa)($|\?)/i.test(link.url))
  const upgrade = pickUpgradeLink(links, playerSource.value)
  if (!upgrade?.url) return
  // Allow a second climb on fast networks (720 → 1080) after the first upgrade.
  const nextHeight = qualityHeightOf(upgrade.quality, upgrade.url)
  autoUpgradeDone = profile !== 'fast' || nextHeight >= 1000
  applySource(upgrade.url, `کیفیت بهتر فعال شد · ${upgrade.quality || 'HD'}`)
}

function selectQuality(quality: PlaybackQuality) {
  selectedQuality.value = quality
  autoUpgradeDone = quality !== 'auto'
  if (/\.m3u8(?:\?|$)/i.test(playerSource.value)) {
    showPlayerNotice(quality === 'auto' ? 'کیفیت خودکار و تطبیقی فعال شد' : `کیفیت ${quality} انتخاب شد`)
    return
  }
  const links = versionScopedLinks()
  if (!links.length) {
    showPlayerNotice(quality === 'auto' ? 'کیفیت خودکار فعال شد' : `کیفیت ${quality} انتخاب شد`)
    return
  }
  const match = quality === 'auto'
    ? pickBestLink(links)
    : links.find(link => qualityMatches(link.quality, quality)) || pickBestLink(links)
  if (match?.url && match.url !== playerSource.value) {
    applySource(
      match.url,
      quality === 'auto' ? `شروع سریع · ${match.quality || 'آماده'}` : `ادامه از همین‌جا · ${match.quality || quality}`,
    )
    return
  }
  showPlayerNotice(quality === 'auto' ? 'کیفیت خودکار فعال شد' : `کیفیت ${quality} انتخاب شد`)
}

function selectVersion(version: PlaybackVersion) {
  autoUpgradeDone = false
  void router.replace({
    query: {
      ...route.query,
      source: version.url,
      version: version.kind,
      episode: currentEpisode.value?.id ? String(currentEpisode.value.id) : route.query.episode,
      player: '1',
    },
  })
}

function handlePlaybackStart(progress: number) {
  if (!item.value) return
  if (mode.value === 'trailer') trackTrailerPlay(item.value)
  else {
    trackWatchProgress(item.value, progress, 'start')
    watchProgress.upsert(item.value, Math.max(progress, resumeProgress.value || progress), currentEpisode.value?.id)
  }
}

function handlePlaybackPause(progress: number) {
  if (item.value && mode.value === 'full') {
    trackWatchProgress(item.value, progress, 'pause')
    watchProgress.upsert(item.value, progress, currentEpisode.value?.id)
  }
}

function handlePlaybackProgress(progress: number) {
  if (item.value && mode.value === 'full') {
    trackWatchProgress(item.value, progress, 'progress')
    watchProgress.upsert(item.value, progress, currentEpisode.value?.id)
  }
}

function handlePlaybackPosition(snapshot: { position_seconds: number, duration_seconds: number }) {
  if (!item.value || mode.value !== 'full' || snapshot.duration_seconds <= 0) return
  const progress = snapshot.position_seconds / snapshot.duration_seconds * 100
  watchProgress.upsert(
    item.value,
    progress,
    currentEpisode.value?.id,
    snapshot.position_seconds,
    snapshot.duration_seconds,
  )
}

function handlePlaybackComplete(progress: number) {
  if (item.value && mode.value === 'full') {
    trackWatchProgress(item.value, progress, 'complete')
    watchProgress.remove(item.value.id, item.value.type)
    if (item.value.type === 'series' && currentEpisode.value) {
      const currentIndex = orderedEpisodes.value.findIndex(episode => episode.id === currentEpisode.value?.id)
      const next = currentIndex >= 0 ? orderedEpisodes.value[currentIndex + 1] : undefined
      if (next) {
        selectEpisode(
          next,
          `پخش خودکار · فصل ${(next.season_number || 1).toLocaleString('fa-IR')} قسمت ${next.episode_number.toLocaleString('fa-IR')}`,
        )
      }
    }
  }
}

watch(playerSource, (url) => {
  warmPlaybackOrigin(url)
}, { immediate: true })

function clearSoftsubPoll() {
  if (softsubPollTimer) {
    window.clearInterval(softsubPollTimer)
    softsubPollTimer = undefined
  }
}

function clearSoftsubRetry() {
  if (softsubRetryTimer) {
    window.clearTimeout(softsubRetryTimer)
    softsubRetryTimer = undefined
  }
}

/** After a poll window expires, re-run the sync ensure with growing backoff so
 *  cues that landed late still reach the open player without a page reload. */
function scheduleSoftsubRetry() {
  if (softsubEnsureRounds >= SOFTSUB_ENSURE_MAX_ROUNDS) return
  softsubEnsureRounds += 1
  const backoffMs = [20_000, 40_000, 70_000, 120_000][softsubEnsureRounds - 1] ?? 120_000
  clearSoftsubRetry()
  softsubRetryTimer = window.setTimeout(() => {
    softsubRetryTimer = undefined
    if (!item.value || activeSubtitleSourceTracks.value.length) return
    void runPlaybackSubtitleEnsure({ showBanner: false })
  }, backoffMs)
}

function resetSoftsubRetry() {
  softsubEnsureRounds = 0
  clearSoftsubRetry()
}

function handleSoftsubVisibility() {
  if (document.visibilityState !== 'visible') return
  if (!item.value || mode.value === 'trailer') return
  if (activeSubtitleSourceTracks.value.length || softsubEnsureRounds >= SOFTSUB_ENSURE_MAX_ROUNDS) return
  if (softsubPollTimer || softsubRetryTimer) return
  void runPlaybackSubtitleEnsure({ showBanner: false })
}

function normalizeEnsuredTracks(tracks: PlaybackTextTrack[] | undefined | null): PlaybackTextTrack[] {
  return (tracks || [])
    .filter(track => Boolean(track?.src))
    .map((track, index) => ({
      id: track.id || `fa-ensured-${index}`,
      label: track.label || track.language || 'فارسی',
      language: track.language || 'fa',
      src: track.src,
      default: Boolean(track.default ?? index === 0),
      source_url: track.source_url || undefined,
      season_number: track.season_number,
      episode_number: track.episode_number,
      provider: track.provider,
    }))
}

/** Instantly attach ensure-response cues so the player does not wait on a stale catalog poll. */
function injectEnsuredSubtitleTracks(tracks: PlaybackTextTrack[] | undefined | null) {
  const usable = normalizeEnsuredTracks(tracks)
  if (!usable.length || !item.value) return false
  const catalogState = useState<import('~/types').Movie[]>('catalog-items')
  const type = item.value.type
  const episodeId = currentEpisode.value?.id
  catalogState.value = catalogState.value.map((candidate) => {
    if (candidate.slug !== slug.value || candidate.type !== type) return candidate
    if (type === 'movie') {
      return {
        ...candidate,
        playback: {
          ...(candidate.playback || { hls_url: candidate.hls_url || '' }),
          hls_url: candidate.playback?.hls_url || candidate.hls_url || '',
          subtitle_tracks: usable,
        },
      }
    }
    return {
      ...candidate,
      episodes: (candidate.episodes || []).map(episode => (
        episode.id === episodeId
          ? { ...episode, subtitle_tracks: usable }
          : episode
      )),
      playback: {
        ...(candidate.playback || { hls_url: candidate.hls_url || '' }),
        hls_url: candidate.playback?.hls_url || candidate.hls_url || '',
        subtitle_tracks: usable,
      },
    }
  })
  return true
}

function startSoftsubPoll(options: { maxAttempts?: number, intervalMs?: number, retryAt?: number } = {}) {
  clearSoftsubPoll()
  let attempts = 0
  // Keep polling light so SoftSub backfill never competes with the video CDN.
  const maxAttempts = options.maxAttempts ?? 12
  const intervalMs = options.intervalMs ?? 4_000
  const retryAt = options.retryAt ?? 4
  softsubPollTimer = window.setInterval(() => {
    attempts += 1
    if (attempts > maxAttempts || activeSubtitleSourceTracks.value.length) {
      clearSoftsubPoll()
      if (activeSubtitleSourceTracks.value.length) {
        applySoftsubWhenReady()
      } else if (softsubEnsureRounds < SOFTSUB_ENSURE_MAX_ROUNDS) {
        showSoftsubBanner('retrying', 0)
        scheduleSoftsubRetry()
      } else {
        showSoftsubBanner('failed', 0)
      }
      return
    }
    if (attempts === retryAt) showSoftsubBanner('retrying', 0)
    void pollSoftsubOnce()
  }, intervalMs)
}

function applySoftsubWhenReady() {
  showSoftsubBanner('ready', 6500)
  dismissPlayerToast()
  showPlayerNotice(subtitleReadyNotice(true), 3200)
  clearSoftsubPoll()
  // Prefer keeping the stream already playing — source switches stall the buffer.
  const currentUrl = String(route.query.source || activeVersion.value?.url || playerSource.value || '')
  const pairedHere = pairSubtitleTracksForSource(
    activeSubtitleSourceTracks.value,
    currentUrl,
    episodeScopedLinks.value,
  )
  if (pairedHere.length) return

  const softReady = buildPlaybackVersions(
    episodeScopedLinks.value,
    activeSubtitleSourceTracks.value,
    fallbackUrl.value,
  ).find(version => (
    version.kind === 'softsub'
    && version.subtitleTracks.length > 0
    && isPlayablePlaybackUrl(version.url)
  ))
  if (softReady && String(route.query.version || '') !== 'dub') {
    void router.replace({
      query: {
        ...route.query,
        source: softReady.url,
        version: 'softsub',
        player: '1',
      },
    })
  }
}

async function pollSoftsubOnce() {
  if (!item.value) return false
  // Read-only status check: never re-queues extraction, calls providers, or
  // increments the viewer report while the video buffer is filling.
  try {
    const result = await getPlaybackSubtitleStatus({
      type: item.value.type,
      slug: slug.value,
      episodeId: currentEpisode.value?.id || 0,
      reportId: softsubReportId,
    })
    if (result?.subtitle_tracks?.length && injectEnsuredSubtitleTracks(result.subtitle_tracks)) {
      applySoftsubWhenReady()
      return true
    }
    if (result?.has_subtitle_tracks || result?.status === 'ready') {
      // Tracks exist server-side but weren't inlined — one targeted detail fetch.
      const adapted = await loadItemFromApi(slug.value, item.value.type, { softsubPoll: true })
      if (!adapted) return false
      const episodeId = currentEpisode.value?.id
      const tracks = item.value.type === 'movie'
        ? (adapted.playback?.subtitle_tracks || [])
        : (
          (episodeId
            ? adapted.episodes?.find(episode => episode.id === episodeId)?.subtitle_tracks
            : null)
          || adapted.playback?.subtitle_tracks
          || []
        )
      if (tracks?.length && injectEnsuredSubtitleTracks(tracks)) {
        applySoftsubWhenReady()
        return true
      }
    }
  } catch {
    // Keep the player streaming; the next poll retries.
  }
  return false
}

async function runPlaybackSubtitleEnsure(options: { showBanner?: boolean } = {}) {
  if (!item.value) return
  const showBanner = options.showBanner !== false
  if (showBanner) {
    showSoftsubBanner('finding', 0)
    showPlayerNotice(subtitleFindingNotice(), 0)
  }
  try {
    const result = await ensurePlaybackSubtitles({
      type: item.value.type,
      slug: slug.value,
      episodeId: currentEpisode.value?.id || 0,
      version: String(activeVersion.value?.kind || route.query.version || ''),
      sourceUrl: String(route.query.source || activeVersion.value?.url || playerSource.value || ''),
      sync: true,
    })
    softsubReportId = result?.report_id || softsubReportId
    if (result?.subtitle_tracks?.length && injectEnsuredSubtitleTracks(result.subtitle_tracks)) {
      applySoftsubWhenReady()
      return
    }
    if (result?.has_subtitle_tracks || result?.status === 'ready') {
      const ready = await pollSoftsubOnce()
      if (ready) return
    }
    if (result?.status === 'burned_in' && !result?.queued) {
      clearSoftsubPoll()
      clearSoftsubBanner()
      dismissPlayerToast()
      return
    }
    if (result?.status === 'unavailable') {
      // Transient queue/broker failures must not end the hunt: the beat drain
      // re-enqueues server-side, and one bounded local retry covers restarts.
      clearSoftsubPoll()
      showSoftsubBanner('retrying', 0)
      scheduleSoftsubRetry()
      return
    }
    // Only poll after the sync call when the worker still needs time —
    // never stack API traffic on top of the opening video buffer.
    if (result?.queued || result?.status === 'queued' || result?.status === 'loading') {
      // Remote container demux can outlive the short provider path; keep polling
      // long enough for a complete (never partial) WebVTT to be persisted.
      startSoftsubPoll({ maxAttempts: 40, intervalMs: 3_000, retryAt: 6 })
      if (showBanner) showSoftsubBanner('finding', 0)
      return
    }
    if (showBanner) showSoftsubBanner('finding', 0)
  } catch {
    if (showBanner) showSoftsubBanner('retrying', 0)
    startSoftsubPoll({ maxAttempts: 24, intervalMs: 5_000, retryAt: 2 })
  }
}

onMounted(() => {
  ensureFastStartSource()
  // Prefer Soft/Hard subtitle playback so Persian text is always visible:
  // 1) SoftSub with WebVTT cues, or 2) HardSub burned-in when no VTT yet.
  // Also rewrite empty Dub deep-links when SubtitleStar cues exist on a SoftSub lane.
  const softOrHard = pickDefaultPlaybackVersion(playbackVersions.value)
  const requestedVersion = String(route.query.version || '')
  if (
    softOrHard
    && softOrHard.subtitleTracks.length
    && (!requestedVersion || requestedVersion === 'dub')
  ) {
    void router.replace({
      query: {
        ...route.query,
        source: softOrHard.url,
        version: softOrHard.kind === 'hardsub' ? 'hardsub' : softOrHard.kind,
        player: '1',
      },
    })
  } else if (
    softOrHard
    && softOrHard.burnedInSubtitles
    && (!requestedVersion || requestedVersion === 'dub')
  ) {
    void router.replace({
      query: {
        ...route.query,
        source: softOrHard.url,
        version: softOrHard.kind === 'hardsub' ? 'hardsub' : 'softsub',
        player: '1',
      },
    })
  }

  // Always try SubtitleStar/Soft ensure when the open player has no cues —
  // HardSub-only rows still often need a sidecar (burned-in is unreliable).
  const needsSoftsubEnsure = mode.value === 'full'
    && import.meta.client
    && !activeSubtitleSourceTracks.value.length

  if (needsSoftsubEnsure) {
    void runPlaybackSubtitleEnsure({ showBanner: true })
  }
  document.addEventListener('visibilitychange', handleSoftsubVisibility)
})

watch([() => currentEpisode.value?.id, () => activeVersion.value?.id], () => {
  autoUpgradeDone = false
  failedPlaybackSources.clear()
  ensureFastStartSource()
})

// When the viewer switches episode and SoftSub is still missing, re-trigger ensure.
watch(() => confirmed.value, (isConfirmed, wasConfirmed) => {
  if (!import.meta.client || mode.value !== 'full') return
  if (!isConfirmed || wasConfirmed) return
  if (activeSubtitleSourceTracks.value.length) return
  void runPlaybackSubtitleEnsure({ showBanner: true })
})

watch(() => currentEpisode.value?.id, (episodeId, previousId) => {
  if (!import.meta.client || mode.value !== 'full') return
  if (!episodeId || episodeId === previousId) return
  softsubReportId = null
  resetSoftsubRetry()
  if (activeSubtitleSourceTracks.value.length) return
  void runPlaybackSubtitleEnsure({ showBanner: true })
})

onBeforeUnmount(() => {
  if (toastTimer) window.clearTimeout(toastTimer)
  if (softsubBannerTimer) window.clearTimeout(softsubBannerTimer)
  clearSoftsubPoll()
  clearSoftsubRetry()
  document.removeEventListener('visibilitychange', handleSoftsubVisibility)
})

useSeoMeta({
  title: () => item.value ? `${mode.value === 'trailer' ? 'تریلر' : 'تماشای'} ${item.value.title}` : 'پخش',
  description: () => item.value?.description || '',
})
</script>

<template>
  <div
    v-if="item"
    class="watch-root theme-media-dark fixed inset-0 z-10 overflow-hidden bg-black text-white"
    dir="rtl"
    lang="fa"
  >
    <template v-if="confirmed">
      <NuxtLink
        :to="detailPath"
        class="watch-back absolute z-30 inline-flex size-11 items-center justify-center rounded-full bg-black/55 text-white ring-1 ring-white/15 backdrop-blur-sm transition hover:bg-black/75"
        aria-label="بازگشت به صفحه عنوان"
      >
        <CinematicIcon name="arrow-right" class="size-5" />
      </NuxtLink>

      <div class="watch-stage absolute inset-0">
        <VideoPlayer
          :key="`${item.slug}-${currentEpisode?.id || 'movie'}-${mode}-${activeVersion?.kind || 'play'}`"
          fill
          :src="playerSource"
          :poster="currentEpisode?.thumbnail_url || item.playback?.poster_url || item.backdrop_url"
          :title="currentEpisode ? `${item.title} · فصل ${(currentEpisode.season_number || 1).toLocaleString('fa-IR')} · ${currentEpisode.title}` : item.title"
          :start-at-percent="resumeProgress"
          :start-at-seconds="resumeSeconds"
          :quality="selectedQuality"
          :source-quality="playerSourceQuality"
          :available-qualities="playerQualities"
          :autoplay="shouldAutoplay"
          :subtitle-tracks="activeSubtitleTracks"
          :playback-versions="playbackVersions"
          :active-version-id="activeVersion?.id || ''"
          :episodes="mode === 'full' && item.type === 'series' ? playbackEpisodes : []"
          :active-episode-id="currentEpisode?.id || 0"
          @play="handlePlaybackStart"
          @pause="handlePlaybackPause"
          @progress="handlePlaybackProgress"
          @position-snapshot="handlePlaybackPosition"
          @complete="handlePlaybackComplete"
          @buffer-health="handleBufferHealth"
          @quality-request="selectQuality"
          @version-request="selectVersion"
          @episode-request="selectEpisode"
          @notice="showPlayerNotice"
          @source-failed="handleSourceFailed"
        />
      </div>

      <div class="watch-message-stack absolute inset-x-0 z-40 mx-auto flex flex-col gap-2">
        <Transition
          enter-active-class="watch-msg-enter"
          leave-active-class="watch-msg-leave"
        >
          <aside
            v-if="softsubBanner"
            class="watch-msg overflow-hidden text-white"
            role="status"
            aria-live="polite"
          >
            <div class="watch-msg__row">
              <span class="watch-msg__icon" aria-hidden="true">
                <span
                  v-if="softsubBanner.tone === 'finding' || softsubBanner.tone === 'retrying'"
                  class="watch-msg__spinner"
                />
                <CinematicIcon
                  v-else-if="softsubBanner.tone === 'ready'"
                  name="check"
                  class="size-4"
                />
                <CinematicIcon
                  v-else
                  name="info"
                  class="size-4"
                />
              </span>
              <div class="watch-msg__body">
                <p class="watch-msg__title">{{ softsubBanner.title }}</p>
                <p class="watch-msg__detail">{{ softsubBanner.detail }}</p>
              </div>
              <button
                type="button"
                class="watch-msg__dismiss"
                aria-label="بستن"
                @click="clearSoftsubBanner"
              >
                بستن
              </button>
            </div>
            <div
              v-if="softsubBanner.tone === 'finding' || softsubBanner.tone === 'retrying'"
              class="watch-msg__track"
              aria-hidden="true"
            >
              <div class="watch-msg__progress" />
            </div>
          </aside>
        </Transition>

        <Transition
          enter-active-class="watch-msg-enter"
          leave-active-class="watch-msg-leave"
        >
          <div
            v-if="playerToast"
            :key="playerToast.id"
            class="watch-msg overflow-hidden text-white"
            role="status"
            aria-live="polite"
          >
            <div class="watch-msg__row watch-msg__row--toast">
              <span class="watch-msg__icon" aria-hidden="true">
                <CinematicIcon :name="playerToast.icon" class="size-4 sm:size-5" />
              </span>
              <div class="watch-msg__body">
                <p v-if="playerToast.label" class="watch-msg__label">{{ playerToast.label }}</p>
                <p class="watch-msg__title">{{ playerToast.message }}</p>
              </div>
              <button
                type="button"
                class="watch-msg__dismiss"
                aria-label="بستن پیام"
                @click="dismissPlayerToast"
              >
                بستن
              </button>
            </div>
            <span class="watch-msg__ttl" aria-hidden="true" />
          </div>
        </Transition>
      </div>
    </template>

    <section
      v-else
      class="watch-restricted relative grid place-items-center overflow-hidden bg-slate-950"
    >
      <CinematicImage
        :src="item.backdrop_url || item.poster_url"
        alt=""
        ratio="backdrop"
        class="absolute inset-0 h-full w-full opacity-20"
      />
      <div class="relative max-w-md p-6 text-center">
        <span class="mx-auto grid size-14 place-items-center rounded-2xl bg-error/15 text-error ring-1 ring-error/25">
          <CinematicIcon name="lock" class="size-7" />
        </span>
        <h2 class="mt-4 text-xl font-black">پخش تا زمان تأیید متوقف است</h2>
        <p class="mt-2 text-sm leading-7 text-secondary">این عنوان برای رده سنی بزرگسال است و پیش از پخش به تأیید نیاز دارد.</p>
        <button
          type="button"
          class="mt-5 rounded-xl bg-primary-500 px-5 py-3 text-sm font-black text-night-950 hover:bg-primary-400"
          @click="modalOpen = true"
        >
          بررسی و ادامه
        </button>
      </div>
    </section>

    <ConfirmAdultContentModal :open="modalOpen" :title="item.title" @confirm="confirmPlayback" @close="leavePlayer" />
  </div>
</template>

<style scoped>
.watch-stage {
  inset: 0;
  width: 100%;
  height: 100%;
  min-height: 100dvh;
  min-height: 100svh;
}

.watch-back {
  inset-inline-start: max(0.75rem, env(safe-area-inset-inline-start, 0px));
  top: max(0.75rem, env(safe-area-inset-top, 0px));
  z-index: 45;
}

/* Top stack — clear of back button, bottom controls, and captions. */
.watch-message-stack {
  top: calc(3.5rem + env(safe-area-inset-top, 0px));
  width: min(26rem, calc(100% - 1.5rem));
  max-width: calc(100vw - 1.5rem);
  pointer-events: none;
  padding-inline: env(safe-area-inset-inline-start, 0px) env(safe-area-inset-inline-end, 0px);
}

.watch-message-stack > * {
  pointer-events: auto;
}

.watch-msg {
  position: relative;
  isolation: isolate;
  border: 0;
  border-radius: 1rem;
  background: #000;
  box-shadow: 0 12px 32px rgba(0, 0, 0, 0.55);
}

.watch-msg__row {
  display: flex;
  align-items: flex-start;
  gap: 0.75rem;
  padding: 0.85rem 0.95rem;
}

.watch-msg__row--toast {
  align-items: center;
}

.watch-msg__icon {
  display: grid;
  place-items: center;
  flex-shrink: 0;
  width: 2.15rem;
  height: 2.15rem;
  margin-top: 0.1rem;
  border-radius: 0.65rem;
  background: #111;
  color: #fff;
}

.watch-msg__row--toast .watch-msg__icon {
  margin-top: 0;
}

.watch-msg__spinner {
  width: 0.95rem;
  height: 0.95rem;
  border-radius: 999px;
  border: 2px solid #333;
  border-top-color: #fff;
  animation: watch-msg-spin 0.75s linear infinite;
}

.watch-msg__body {
  min-width: 0;
  flex: 1;
  text-align: start;
}

.watch-msg__label {
  margin: 0;
  font-size: 0.625rem;
  font-weight: 700;
  letter-spacing: 0.06em;
  color: rgba(255, 255, 255, 0.5);
}

.watch-msg__title {
  margin: 0;
  font-size: 0.875rem;
  font-weight: 900;
  line-height: 1.45;
  color: #fff;
}

.watch-msg__detail {
  margin: 0.2rem 0 0;
  font-size: 0.75rem;
  line-height: 1.5;
  color: rgba(255, 255, 255, 0.72);
}

.watch-msg__dismiss {
  flex-shrink: 0;
  border: 0;
  border-radius: 0.5rem;
  background: transparent;
  padding: 0.3rem 0.45rem;
  font-size: 0.6875rem;
  font-weight: 700;
  color: rgba(255, 255, 255, 0.55);
  transition: background 0.15s ease, color 0.15s ease;
}

.watch-msg__dismiss:hover,
.watch-msg__dismiss:focus-visible {
  background: #171717;
  color: #fff;
  outline: none;
}

.watch-msg__track {
  height: 2px;
  overflow: hidden;
  background: #111;
}

.watch-msg__progress {
  width: 35%;
  height: 100%;
  background: #2a2a2a;
  animation: watch-msg-progress 1.35s ease-in-out infinite;
}

.watch-msg__ttl {
  position: absolute;
  inset-inline: 0;
  bottom: 0;
  height: 2px;
  transform-origin: right center;
  background: #222;
  animation: watch-msg-ttl 2.8s linear forwards;
}

.watch-msg-enter {
  animation: watch-msg-in 0.32s cubic-bezier(0.22, 1, 0.36, 1);
}

.watch-msg-leave {
  animation: watch-msg-out 0.2s ease-in forwards;
}

@keyframes watch-msg-in {
  from {
    opacity: 0;
    transform: translateY(-8px) scale(0.98);
  }
  to {
    opacity: 1;
    transform: translateY(0) scale(1);
  }
}

@keyframes watch-msg-out {
  to {
    opacity: 0;
    transform: translateY(-5px) scale(0.99);
  }
}

@keyframes watch-msg-spin {
  to { transform: rotate(360deg); }
}

@keyframes watch-msg-progress {
  0% { transform: translateX(-120%); }
  100% { transform: translateX(320%); }
}

@keyframes watch-msg-ttl {
  from { transform: scaleX(1); }
  to { transform: scaleX(0); }
}

@media (max-width: 420px) {
  .watch-message-stack {
    top: calc(3.1rem + env(safe-area-inset-top, 0px));
    width: calc(100% - 0.85rem);
    max-width: calc(100vw - 0.85rem);
    gap: 0.4rem;
  }

  .watch-msg {
    border-radius: 0.75rem;
  }

  .watch-msg__row {
    gap: 0.5rem;
    padding: 0.6rem 0.65rem;
  }

  .watch-msg__icon {
    width: 1.7rem;
    height: 1.7rem;
    border-radius: 0.45rem;
  }

  .watch-msg__title {
    font-size: 0.78rem;
    line-height: 1.35;
  }

  .watch-msg__detail {
    font-size: 0.65rem;
    line-height: 1.4;
  }

  .watch-msg__dismiss {
    padding: 0.2rem 0.3rem;
    font-size: 0.6rem;
  }
}

@media (orientation: landscape) and (max-height: 500px) {
  .watch-back {
    top: max(0.35rem, env(safe-area-inset-top, 0px));
    inset-inline-start: max(0.5rem, env(safe-area-inset-inline-start, 0px));
    width: 2.35rem;
    height: 2.35rem;
  }

  .watch-message-stack {
    top: calc(2.5rem + env(safe-area-inset-top, 0px));
    width: min(20rem, calc(100% - 0.85rem));
  }

  .watch-msg__row {
    padding: 0.45rem 0.6rem;
  }

  .watch-msg__detail {
    display: -webkit-box;
    -webkit-line-clamp: 1;
    -webkit-box-orient: vertical;
    overflow: hidden;
  }
}

@media (min-width: 768px) {
  .watch-message-stack {
    width: min(28rem, calc(100% - 2rem));
  }

  .watch-msg__row {
    padding: 0.95rem 1.05rem;
  }
}

@media (max-width: 379px) {
  .watch-back {
    width: 2.5rem;
    height: 2.5rem;
  }
}

/* Viewport-unit fallbacks for older browsers that do not support dvh/dvw. */
.watch-root {
  width: 100%;
  width: 100dvw;
  max-width: 100%;
  max-width: 100dvw;
  height: 100%;
  height: 100dvh;
  max-height: 100%;
  max-height: 100dvh;
}

.watch-restricted {
  height: 100vh;
  height: 100dvh;
}
</style>
