<script setup lang="ts">
import { reportClientDiag } from '~/utils/clientDiag'
import type { ContentType, DownloadLink, Episode, PlaybackEpisodeOption, PlaybackQuality, PlaybackTextTrack, PlaybackVersion, PlaybackVersionKind, SubtitleSyncFeedback } from '~/types'
import { codecLikelyUnsupported, episodeNumberOf, isExpiredPlaybackUrl, isPlayablePlaybackUrl, linkMatchesEpisode, pickStreamFriendlyLink, playbackOrigin, prefersBrowserSafeContainers, qualityHeightOf, seasonNumberOf, streamNetworkProfile, videoCodecFamily, warmPlaybackOrigin } from '~/utils/downloadMeta'
import { buildPlaybackVersions, isDubLink, isSoftsubLink, linksForVersionKind, pairSubtitleTracksForSource, resolvePlaybackVersion } from '~/utils/playbackVersions'
import { classifyPlayerToast, type PlayerToastMeta } from '~/utils/playerToast'
import type { ReportProblemType } from '~/composables/useContentReport'
import type { StreamGatewaySession } from '~/composables/useStreamGateway'
import { pickDefaultPlaybackVersion, softsubBannerCopy, subtitleFindingNotice, subtitleReadyNotice, type SoftsubBannerTone } from '~/utils/subtitlePolicy'

definePageMeta({ layout: 'player', pageTransition: false, ssr: false })

const route = useRoute()
const router = useRouter()
const slug = computed(() => decodeRouteSlug(route.params.slug))
const { catalog, loadItemFromApi } = useCatalog()
const initialItem = catalog.value.find(candidate => candidate.slug === slug.value)
const requestedType = route.query.type === 'movie' || route.query.type === 'series'
  ? route.query.type as ContentType
  : initialItem?.type

const loadedItem = requestedType
  ? await loadItemFromApi(slug.value, requestedType)
  : (await loadItemFromApi(slug.value, 'movie')) || await loadItemFromApi(slug.value, 'series')
// An old (Persian) address resolves to the row's current English slug: move the
// player onto it so every later lookup by ``slug`` finds the item.
if (loadedItem?.slug && loadedItem.slug !== slug.value) {
  await navigateTo({ path: `/watch/${loadedItem.slug}`, query: route.query, hash: route.hash }, { replace: true })
}

const item = computed(() => catalog.value.find(candidate => candidate.slug === slug.value)
  ?? (loadedItem ? catalog.value.find(candidate => candidate.slug === loadedItem.slug && candidate.type === loadedItem.type) : undefined)
  ?? null)
const { trackTrailerPlay, trackWatchProgress } = useAnalyticsEvent()
const watchProgress = useWatchProgress()
const { ensurePlaybackSubtitles, getPlaybackSubtitleStatus } = usePlaybackSubtitleEnsure()
const { reportSubtitleSync } = useSubtitleSyncReport()
const { reportIssue } = useContentReport()
const { openGatewayStream, isGatewayUrl, gatewayMessageFor } = useStreamGateway()

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

// Dubbed («دوبله») playback carries Persian in the audio, so the SubtitleStar/Soft
// importer must NOT run for it — importing here would attach an unwanted subtitle to
// a dub. Softsub/Hardsub/Original lanes still ensure a sidecar when cues are missing.
const activeVersionIsDub = computed(() => {
  const kind = activeVersion.value?.kind || String(route.query.version || '')
  return kind === 'dub' || kind === 'dubbed'
})

// --- playback gateway ------------------------------------------------------
// When a browser cannot open a file directly, the backend rewraps it into HLS
// on demand. This is a fallback, not a mode: it is only ever reached from
// handleSourceFailed, and the direct CDN URL stays the first thing tried.
/** True while a session is being opened, so the player can show progress. */
const gatewayPending = ref(false)
/** The session being played. Holds the film's true start/duration, which the
 *  session's own media timeline does not carry — it always begins at zero. */
const gatewaySession = ref<StreamGatewaySession | null>(null)
/** The original CDN URL the running session was opened from. */
let gatewayOriginUrl = ''
/** Sources already offered to the gateway, so a failure cannot loop. */
const gatewayAttempted = new Set<string>()
/** Live playhead in *film* seconds — where a reopened session resumes. */
let lastPositionSeconds = 0

/** A URL the backend handed back that beats what the link list can offer. */
const resolvedSource = ref('')

const playerSource = computed(() => {
  if (mode.value === 'trailer') return item.value?.trailer_url || ''
  // A gateway session outranks every direct mirror. It is only ever opened
  // after a direct source has already failed in this browser, so falling back
  // to the link list here would put us straight back on the file that broke.
  // It deliberately does not travel through ?source=: that query parameter is
  // validated against the title's own link list, which a gateway URL is not in.
  if (gatewaySession.value?.playlist) return gatewaySession.value.playlist
  const picked = activeVersion.value?.url
    || activeRouteSource.value
    || fallbackUrl.value
    || episodeScopedLinks.value[0]?.url
    || ''
  // A re-signed URL only outranks the viewer's own pick when that pick cannot
  // play: either there is nothing to play, or its token has lapsed and this one
  // has not. Otherwise the link list wins, so choosing a quality still means
  // something. See ensureFreshSource.
  const resigned = resolvedSource.value
  if (resigned && (!picked || (isExpiredPlaybackUrl(picked) && !isExpiredPlaybackUrl(resigned)))) {
    return resigned
  }
  return picked
})

/**
 * Detect when all download links exist but are expired (CDN signature timeout).
 * Shows a dedicated "refreshing" banner and auto-reloads after the backend
 * re-crawls fresh links via the periodic playback refresh task.
 */
const expiredLinksNotice = computed(() => {
  if (mode.value === 'trailer') return null
  if (playerSource.value) return null
  const links = item.value?.download_links || []
  if (!links.length) return null
  const hasAnyLink = links.some(link => link.url && isPlayablePlaybackUrl(link.url))
  if (hasAnyLink) return null
  // All links present but none playable = expired CDN signatures
  return {
    title: 'لینک‌ها منقضی شده‌اند',
    detail: 'لینک‌های پخش به‌روزرسانی می‌شوند… لطفاً چند لحظه صبر کنید.',
  }
})
let expiredRefreshTimer: ReturnType<typeof setTimeout> | undefined
watch(expiredLinksNotice, (notice) => {
  if (expiredRefreshTimer) clearTimeout(expiredRefreshTimer)
  if (notice && item.value) {
    // Backstop only. The real repair is `ensureFreshSource` below, which asks
    // the backend to re-sign on demand; this re-read just picks up a refresh
    // that landed from somewhere else (the sweep, or a hand-off that finished
    // after we had already been answered).
    expiredRefreshTimer = setTimeout(() => {
      if (expiredLinksNotice.value && item.value) {
        loadItemFromApi(slug.value, item.value.type)
      }
    }, 60_000)
  }
})

// --- re-signing the source at play time ------------------------------------
// A signed CDN URL lapses in ~13 h, and until now nothing re-signed it between
// the crawl and the player, so any title opened half a day after it was crawled
// failed on a file that was never actually missing. See usePlaybackResolve.
const {
  resolve: resolvePlaybackSource,
  resolving: sourceResolving,
  resolution: sourceResolution,
} = usePlaybackResolve()
/** Sources already sent for re-signing, so a title cannot loop on one failure. */
const resolveAttempted = new Set<string>()

/** Shown while the backend re-crawls: a wait with a reason, not a dead player. */
const preparingSource = computed(() => sourceResolving.value && !gatewaySession.value)

/**
 * One status line for the whole "the source is not ready yet" family.
 *
 * The wording matters here: the old copy promised that links "are being
 * refreshed" whenever none were playable, which pointed at a background task
 * that could not keep up, so the promise expired with the viewer still staring
 * at it. Each branch below now says only what is actually true — a re-crawl is
 * running, a re-crawl ran and did not help, or there is nothing to play.
 */
const sourceNotice = computed(() => {
  if (mode.value === 'trailer') return null
  if (preparingSource.value) {
    return {
      title: 'در حال آماده‌سازی پخش…',
      detail: 'لینک پخش این عنوان منقضی شده و همین حالا تازه‌سازی می‌شود.',
    }
  }
  const resolution = sourceResolution.value
  if (resolution && resolution.stale && !resolution.refreshed && playerSource.value) {
    return {
      title: 'کیفیت پخش ممکن است پایین‌تر باشد',
      detail: 'لینک تازه‌ای از سرویس‌دهنده گرفته نشد؛ پخش با آخرین لینک موجود ادامه پیدا می‌کند.',
    }
  }
  return expiredLinksNotice.value
})

/**
 * Make sure the URL we are about to play still has a valid signature.
 *
 * Cheap and silent in the common case: a URL whose token is still good is not
 * sent anywhere. Only a lapsed one — or a title with no playable source at all —
 * costs a round trip.
 *
 * On success the *item* is re-read rather than just swapping in the one URL the
 * backend returned. The re-crawl re-signs every quality, and the viewer may have
 * chosen one that is not the backend's pick; re-reading keeps their choice and
 * makes all the other lanes work too.
 */
async function ensureFreshSource() {
  if (mode.value === 'trailer') return
  const target = item.value
  if (!target?.id) return
  if (gatewaySession.value) return

  const current = playerSource.value
  // A source that is present and unlapsed is the whole point of the fast path.
  if (current && !isExpiredPlaybackUrl(current)) return

  const key = `${target.type}:${target.id}:${currentEpisode.value?.id || 0}:${current}`
  if (resolveAttempted.has(key)) return
  resolveAttempted.add(key)

  const resolved = await resolvePlaybackSource({
    kind: target.type,
    id: target.id,
    episodeId: currentEpisode.value?.id || null,
  })
  if (!resolved) return

  if (resolved.refreshed) {
    // Fresh signatures for every quality, not just the one we asked about.
    await loadItemFromApi(slug.value, target.type)
    return
  }

  // Not refreshed. The backend still handed back a URL — the stale one, or one
  // a hand-off is still working on. Playing it and failing is no worse than
  // refusing to try, and it frequently just works: `stale` means the token
  // lapsed, not that the file is gone.
  if (resolved.videoUrl && resolved.videoUrl !== current) {
    resolvedSource.value = resolved.videoUrl
  }
}

watch(
  () => [item.value?.id, currentEpisode.value?.id, mode.value] as const,
  () => { void ensureFreshSource() },
  { immediate: true },
)

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
// Invalidates late ensure/status responses after an episode or playback-version
// switch. Without this guard, tracks fetched for the previous episode could be
// injected into the newly selected episode.
let softsubRequestEpoch = 0
const SOFTSUB_ENSURE_MAX_ROUNDS = 4
// The player reads subtitle tracks muxed inside the MKV it is already
// streaming. When one is Persian the server hunt is pointless, so the first
// ensure waits briefly for that probe instead of racing it.
const EMBEDDED_PROBE_WAIT_MS = 4_000
let embeddedPersianAvailable = false
let embeddedProbeSettled = false
let embeddedProbeTimer: number | undefined
let pendingSoftsubEnsure: { showBanner?: boolean } | null = null
// The server already searched every source for this title and found nothing;
// it answers 'exhausted' until its cooldown ends, so polling would be noise.
let softsubExhausted = false
let autoUpgradeDone = false
let toastSeq = 0
const failedPlaybackSources = new Set<string>()

// Self-heal guard: once every mirror is unplayable in this browser we ask the
// backend (once per episode/version) to re-crawl a browser-safe H.264 encode.
let reportedPlaybackGap = false

// Persistent "this browser can't decode any available encode" panel. Set only
// when every mirror has been exhausted on a definitively in-browser-unplayable
// reason (HEVC/AV1 codec, or MKV on Safari/Firefox), so the viewer sees a clear
// app/download CTA instead of a silent black frame. Transient/network failures
// keep using the auto-dismissing toast.
const playbackBlocked = ref<{ family: string, container: string } | null>(null)

const { blocked: regionBlocked, countryName: regionCountryName, dismissed: regionNoticeDismissed, dismissRegionNotice, resolveRegion } = useViewerRegion()
/**
 * Hidden for this tab, seeded from the session so a second episode does not
 * repeat a notice the viewer already read and closed.
 */
const regionNoticeHidden = ref(regionNoticeDismissed.value)
// Not on a trailer: those are served from our own media host, which answers
// everyone, so a viewer abroad watching one has nothing to fix.
const regionModalOpen = computed(() => (
  confirmed.value && mode.value !== 'trailer' && regionBlocked.value && !regionNoticeHidden.value
))

function closeRegionNotice() {
  regionNoticeHidden.value = true
  dismissRegionNotice()
}

/**
 * Bring the notice back after a failure the region explains. Playback failing
 * is new information even to a viewer who dismissed the warning on arrival —
 * it is the moment the warning turns out to have been about their session.
 */
function revealRegionNotice() {
  if (!regionBlocked.value) return false
  regionNoticeHidden.value = false
  return true
}

/** Highest-quality directly-downloadable mirror for the current episode, so the
 *  fallback panel can offer "download and play in a local app". */
const directDownloadLink = computed(() => {
  const links = episodeScopedLinks.value.filter(link => (
    Boolean(link.url)
    && isPlayablePlaybackUrl(link.url)
    && !/\.(vtt|webvtt|srt|ass|ssa)($|\?)/i.test(link.url)
    && !/\.m3u8(?:\?|$)/i.test(link.url)
  ))
  if (!links.length) return null
  return [...links]
    .sort((a, b) => qualityHeightOf(b.quality, b.url) - qualityHeightOf(a.quality, a.url))[0] || null
})

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
  reportedPlaybackGap = false
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
    .filter(entry => (
      entry.height >= min
      && entry.height <= max
      && entry.link.url !== currentUrl
      && !codecLikelyUnsupported(entry.link.url, entry.link.quality, entry.link.label)
    ))
    .sort((a, b) => Math.abs(a.height - target) - Math.abs(b.height - target))
  return candidates[0]?.link || null
}

function applySource(url: string, notice?: string) {
  if (!url || url === playerSource.value) return
  // A fresh source is being tried — retire the "unplayable" panel until (and
  // unless) this one also fails.
  playbackBlocked.value = null
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

function handleSubtitleSyncFeedback(feedback: SubtitleSyncFeedback) {
  const type = item.value?.type
  if (type !== 'movie' && type !== 'series') return
  void reportSubtitleSync({
    type: type as ContentType,
    objectId: item.value?.id || 0,
    episodeId: currentEpisode.value?.id || 0,
    feedback,
  })
}

function handleReportIssue(payload: { problemType: ReportProblemType, detail: string }) {
  const type = item.value?.type
  if (type !== 'movie' && type !== 'series') return
  void reportIssue({
    type: type as ContentType,
    objectId: item.value?.id || 0,
    slug: item.value?.slug || slug.value,
    episodeId: currentEpisode.value?.id || 0,
    problemType: payload.problemType,
    version: activeVersion.value?.kind || String(route.query.version || ''),
    sourceUrl: String(route.query.source || activeVersion.value?.url || playerSource.value || ''),
    detail: payload.detail,
  })
}

/**
 * No browser-decodable mirror exists for this title in the current browser. Ask
 * the backend to re-crawl a browser-safe (H.264 MP4/HLS) source so the next
 * viewer — and this viewer after a refresh — gets a playable encode. Silent and
 * best-effort; fired at most once per episode/version.
 */
function selfHealPlaybackGap() {
  if (reportedPlaybackGap) return
  const type = item.value?.type
  if (type !== 'movie' && type !== 'series') return
  reportedPlaybackGap = true
  void reportIssue({
    type: type as ContentType,
    objectId: item.value?.id || 0,
    slug: item.value?.slug || slug.value,
    episodeId: currentEpisode.value?.id || 0,
    problemType: 'playback',
    version: activeVersion.value?.kind || String(route.query.version || ''),
    sourceUrl: String(route.query.source || playerSource.value || ''),
    detail: 'auto: no browser-decodable source; requesting H.264 re-crawl',
  })
}

/**
 * Ask the backend to rewrap the failed source into HLS and play that instead.
 *
 * Resolves true once a session is playing. Every caller is a dead end in
 * handleSourceFailed — a file this browser has definitively refused — so a
 * false here means there really is nothing left to try.
 */
async function tryGatewayPlayback(
  failedUrl: string,
  options: { position?: number, silent?: boolean, force?: boolean } = {},
) {
  if (mode.value === 'trailer' || gatewayPending.value) return false
  const type = item.value?.type
  if (!item.value || (type !== 'movie' && type !== 'series')) return false
  const source = String(failedUrl || '').trim()
  // A gateway URL must never be fed back into the gateway.
  if (!source || isGatewayUrl(source)) return false

  const episodeId = type === 'series' ? currentEpisode.value?.id || 0 : 0
  const kind: ContentType | 'episode' = episodeId ? 'episode' : type
  const id = episodeId || item.value.id
  if (!id) return false

  // One attempt per source, or a failing gateway would be retried forever.
  // Reopening a *working* session at a chunk boundary passes force.
  const key = `${kind}:${id}:${source}`
  if (!options.force && gatewayAttempted.has(key)) return false
  gatewayAttempted.add(key)

  gatewayPending.value = true
  if (!options.silent) {
    showPlayerNotice('در حال آماده‌سازی پخش سازگار با این مرورگر…', 15_000)
  }
  try {
    const session = await openGatewayStream({
      kind,
      id,
      url: source,
      // Nothing has played yet on a first failure, so fall back to the saved
      // resume point rather than restarting a half-watched film from zero.
      position: Math.max(0, Math.floor(options.position || resumeSeconds.value || 0)),
    })
    gatewayOriginUrl = source
    gatewaySession.value = session
    playbackBlocked.value = null
    if (!options.silent) showPlayerNotice('پخش سازگار با این مرورگر فعال شد.')
    return true
  }
  catch (error) {
    gatewaySession.value = null
    showPlayerNotice(gatewayMessageFor((error as { code?: string })?.code || ''))
    return false
  }
  finally {
    gatewayPending.value = false
  }
}

/**
 * The backend's verdict for the source it actually tested, with that source.
 *
 * ``playback_gate`` probes every published link and records what it found, so
 * for most titles the answer is already known before this page loads. Null
 * when the player is on something the backend never ruled on — a trailer, a
 * hand-picked ``?source=``, a mirror chosen after a failure — because a verdict
 * about one file says nothing about another.
 */
const gatedPlayback = computed(() => {
  if (mode.value === 'trailer') return null
  const target = item.value?.type === 'series' ? currentEpisode.value : item.value
  const url = String(target?.hls_url || '').trim()
  const verdict = target?.playback_mode
  if (!url || !verdict) return null
  return { url, verdict }
})

/**
 * Should this browser go through the gateway before the first frame?
 *
 * Until now the gateway was only ever reached from handleSourceFailed, so a
 * viewer whose file was never going to play watched the player try, stall and
 * fail first. When the backend has already proved the file needs a rewrap,
 * there is nothing to learn from repeating that.
 */
function shouldPrerouteGateway() {
  const gated = gatedPlayback.value
  if (!gated || gated.verdict !== 'gateway') return false
  if (gatewaySession.value || gatewayPending.value) return false
  // The verdict is about the file, not about this browser. Chromium with
  // hardware HEVC plays plenty of what Safari refuses, and remuxing for it
  // would buy nothing and cost a session.
  if (!prefersBrowserSafeContainers() && !codecLikelyUnsupported(gated.url)) return false
  return playerSource.value === gated.url
}

watch([playerSource, gatedPlayback], () => {
  if (!import.meta.client || !shouldPrerouteGateway()) return
  void tryGatewayPlayback(gatedPlayback.value!.url, { silent: true })
}, { immediate: true })

/**
 * A gateway session covers a bounded stretch of film, so reaching its end is
 * usually a chunk boundary rather than the end of the title. Reopening at the
 * playhead is the same call a seek makes.
 */
async function continueGatewaySession() {
  const session = gatewaySession.value
  if (!session || !gatewayOriginUrl) return false
  // Genuinely finished — within a segment's slack of the real runtime.
  if (session.duration > 0 && lastPositionSeconds >= session.duration - 10) return false
  return tryGatewayPlayback(gatewayOriginUrl, {
    position: lastPositionSeconds,
    silent: true,
    force: true,
  })
}

/** The viewer aimed at a moment this session does not contain: reopen there. */
async function handleSeekBeyondWindow(filmSeconds: number) {
  if (!gatewayOriginUrl) return
  lastPositionSeconds = filmSeconds
  showPlayerNotice('در حال انتقال به این لحظه…', 15_000)
  const moved = await tryGatewayPlayback(gatewayOriginUrl, {
    position: filmSeconds,
    silent: true,
    force: true,
  })
  if (!moved) showPlayerNotice('انتقال به این لحظه ممکن نشد. کمی بعد دوباره تلاش کن.')
}

// A paused viewer stops pulling segments, and a session nobody is requesting is
// reaped as "viewer left". Re-reading the playlist is the cheapest thing that
// counts as presence, and it costs one small request a minute.
let gatewayHeartbeat: ReturnType<typeof setInterval> | undefined

watch(() => gatewaySession.value?.playlist || '', (playlist) => {
  if (gatewayHeartbeat) clearInterval(gatewayHeartbeat)
  gatewayHeartbeat = undefined
  if (!playlist || !import.meta.client) return
  gatewayHeartbeat = setInterval(() => {
    fetch(playlist, { method: 'GET', cache: 'no-store', credentials: 'omit' }).catch(() => {})
  }, 30_000)
})

function handleSourceFailed(payload: { src: string, code: number }) {
  const failed = String(payload?.src || playerSource.value || '').trim()
  // The gateway stream itself broke — nearly always a session reaped while the
  // viewer sat paused. Reopening at the playhead is cheap and invisible. Note
  // the session has to be cleared before any fallback, or playerSource would
  // go on preferring the dead playlist over whatever we pick instead.
  if (failed && isGatewayUrl(failed)) {
    // A reopen is already in flight for this stream — a chunk boundary or a
    // seek — and it can legitimately take tens of seconds while ffmpeg warms
    // up. The player's stall watchdog will have fired by then on a playlist
    // that is deliberately dead. Leave the session alone: tearing it down here
    // would cancel nothing (the request is already out) and would drop the
    // viewer onto a mirror the moment the gateway was about to answer.
    if (gatewayPending.value) return
    const origin = gatewayOriginUrl
    gatewaySession.value = null
    if (origin) {
      void tryGatewayPlayback(origin, { position: lastPositionSeconds, silent: true, force: true })
        .then((ok) => {
          // Reopening failed: hand the *original* file back to the normal
          // mirror logic. It cannot recurse here — origin is not a gateway URL.
          if (!ok) handleSourceFailed({ src: origin, code: Number(payload?.code) || 0 })
        })
      return
    }
  }
  if (failed) failedPlaybackSources.add(failed)
  const failedCode = Number(payload?.code) || 0
  const failedFamily = videoCodecFamily(failed)
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
  // Decode/unsupported failures: retire every mirror with the same codec so the
  // next pick jumps straight to a decodable encode instead of churning HEVC files.
  if (failed && failedFamily && (failedCode === 3 || failedCode === 4)) {
    for (const link of episodeScopedLinks.value) {
      if (link.url && videoCodecFamily(link.url, link.quality, link.label) === failedFamily) {
        failedPlaybackSources.add(link.url)
      }
    }
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
  // Every mirror is spent. When the viewer is somewhere these CDNs do not
  // serve, that is the likeliest reason and the only one they can act on, so
  // it is said again here even if they closed the notice on arrival.
  revealRegionNotice()
  // Before giving up on this browser, let the backend rewrap the file into
  // HLS — that is the whole point of the gateway, and it is only reached here,
  // after a real failure on a real file.
  if (failedFamily === 'hevc' || failedFamily === 'av1') {
    showPlayerNotice('این فایل با کُدک HEVC/AV1 انکود شده؛ در حال آماده‌سازی نسخهٔ سازگار با این مرورگر…', 15_000)
    void tryGatewayPlayback(failed, { position: lastPositionSeconds, silent: true }).then((ok) => {
      if (ok) return
      playbackBlocked.value = { family: failedFamily, container: '' }
      showPlayerNotice('این مرورگر نمی‌تواند این فایل را رمزگشایی کند. نسخهٔ سازگار در حال آماده‌سازی است.')
      selfHealPlaybackGap()
    })
    return
  }
  if (prefersBrowserSafeContainers() && /\.mkv(?:\?|$)/i.test(failed)) {
    showPlayerNotice('این مرورگر فایل MKV را پخش نمی‌کند؛ در حال آماده‌سازی نسخهٔ سازگار…', 15_000)
    void tryGatewayPlayback(failed, { position: lastPositionSeconds, silent: true }).then((ok) => {
      if (ok) return
      playbackBlocked.value = { family: failedFamily, container: 'mkv' }
      showPlayerNotice('این نسخه از مرورگر فایل MKV را پخش نمی‌کند. نسخهٔ سازگار در حال آماده‌سازی است؛ به‌روزرسانی مرورگر یا iOS هم مشکل را حل می‌کند.')
      selfHealPlaybackGap()
    })
    return
  }
  showPlayerNotice('این مرورگر این فایل را پخش نکرد؛ در حال آماده‌سازی نسخهٔ سازگار…', 15_000)
  void tryGatewayPlayback(failed, { position: lastPositionSeconds, silent: true }).then((ok) => {
    if (ok) return
    showPlayerNotice('این مرورگر این فایل را پخش نکرد. نسخهٔ سازگار به‌صورت خودکار در حال آماده‌سازی است؛ کمی بعد دوباره تلاش کن.')
    selfHealPlaybackGap()
  })
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
    : pickBestLink(links.filter(link => qualityMatches(link.quality, quality))) || pickBestLink(links)
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
  playbackBlocked.value = null
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
  // The player already reports film time, so a gateway session needs no
  // translation here — it only means this number can outrun the media's own
  // duration, which is exactly what we want recorded.
  const position = Math.max(0, Number(snapshot?.position_seconds) || 0)
  const duration = Math.max(0, Number(snapshot?.duration_seconds) || 0)
  // Recorded before the guards below, so a gateway reopen always resumes from
  // where the viewer actually was.
  lastPositionSeconds = position
  if (!item.value || mode.value !== 'full' || duration <= 0) return
  watchProgress.upsert(item.value, position / duration * 100, currentEpisode.value?.id, position, duration)
}

function handlePlaybackComplete(progress: number) {
  // A gateway session ends at its chunk boundary, not at the end of the film.
  // Treating that as "watched" would wipe the progress and auto-advance to the
  // next episode mid-film, so reopen at the playhead instead.
  if (gatewaySession.value) {
    void continueGatewaySession().then((reopened) => {
      if (!reopened) finishPlayback(progress)
    })
    return
  }
  finishPlayback(progress)
}

function finishPlayback(progress: number) {
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
    if (!item.value || activeSubtitleSourceTracks.value.length || activeVersionIsDub.value) return
    if (embeddedPersianAvailable || softsubExhausted) return
    void runPlaybackSubtitleEnsure({ showBanner: false })
  }, backoffMs)
}

function clearEmbeddedProbeWait() {
  if (embeddedProbeTimer) window.clearTimeout(embeddedProbeTimer)
  embeddedProbeTimer = undefined
}

function resetEmbeddedSubtitleProbe() {
  clearEmbeddedProbeWait()
  embeddedPersianAvailable = false
  embeddedProbeSettled = false
  pendingSoftsubEnsure = null
}

function flushPendingSoftsubEnsure() {
  clearEmbeddedProbeWait()
  const pending = pendingSoftsubEnsure
  pendingSoftsubEnsure = null
  if (!pending || embeddedPersianAvailable) return
  if (!item.value || activeSubtitleSourceTracks.value.length || activeVersionIsDub.value) return
  void runPlaybackSubtitleEnsure(pending)
}

/** Entry point for the automatic subtitle hunt: holds it until the player has
 *  looked inside the file (or a short timeout), then runs it only if needed. */
function requestPlaybackSubtitleEnsure(options: { showBanner?: boolean } = {}) {
  if (embeddedPersianAvailable) return
  if (embeddedProbeSettled) {
    void runPlaybackSubtitleEnsure(options)
    return
  }
  pendingSoftsubEnsure = options
  if (!embeddedProbeTimer) {
    embeddedProbeTimer = window.setTimeout(() => {
      embeddedProbeTimer = undefined
      embeddedProbeSettled = true
      flushPendingSoftsubEnsure()
    }, EMBEDDED_PROBE_WAIT_MS)
  }
}

function handleEmbeddedSubtitles(payload: { src: string, probed: boolean, count: number, persian: boolean }) {
  embeddedProbeSettled = true
  if (!payload.persian) {
    // Fell back to a file without the Persian track (mirror/gateway): the
    // cues left with the old file, so the server hunt is needed again.
    if (embeddedPersianAvailable && mode.value === 'full') pendingSoftsubEnsure ??= { showBanner: false }
    embeddedPersianAvailable = false
    flushPendingSoftsubEnsure()
    return
  }
  embeddedPersianAvailable = true
  pendingSoftsubEnsure = null
  clearEmbeddedProbeWait()
  // Late probe: an ensure may already be polling — stop it, the file has cues.
  softsubRequestEpoch += 1
  clearSoftsubPoll()
  clearSoftsubRetry()
  clearSoftsubBanner()
  dismissPlayerToast()
}

function resetSoftsubRetry() {
  softsubEnsureRounds = 0
  clearSoftsubRetry()
}

function handleSoftsubVisibility() {
  if (document.visibilityState !== 'visible') return
  if (!item.value || mode.value === 'trailer') return
  if (activeVersionIsDub.value) return
  if (activeSubtitleSourceTracks.value.length || softsubEnsureRounds >= SOFTSUB_ENSURE_MAX_ROUNDS) return
  if (softsubPollTimer || softsubRetryTimer || pendingSoftsubEnsure) return
  if (embeddedPersianAvailable || softsubExhausted) return
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
    void pollSoftsubOnce(softsubRequestEpoch)
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

async function pollSoftsubOnce(requestEpoch = softsubRequestEpoch) {
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
    if (requestEpoch !== softsubRequestEpoch) return false
    if (result?.subtitle_tracks?.length && injectEnsuredSubtitleTracks(result.subtitle_tracks)) {
      applySoftsubWhenReady()
      return true
    }
    if (result?.status === 'exhausted') {
      stopSoftsubHuntExhausted(true)
      return false
    }
    if (result?.has_subtitle_tracks || result?.status === 'ready') {
      // Tracks exist server-side but weren't inlined — one targeted detail fetch.
      const adapted = await loadItemFromApi(slug.value, item.value.type, { softsubPoll: true })
      if (requestEpoch !== softsubRequestEpoch) return false
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

function stopSoftsubHuntExhausted(showBanner: boolean) {
  softsubExhausted = true
  clearSoftsubPoll()
  clearSoftsubRetry()
  dismissPlayerToast()
  if (showBanner) showSoftsubBanner('failed', 6000)
  else clearSoftsubBanner()
}

async function runPlaybackSubtitleEnsure(options: { showBanner?: boolean } = {}) {
  if (!item.value) return
  // Never import subtitles onto a Farsi dub — the audio already carries Persian.
  if (activeVersionIsDub.value) return
  if (embeddedPersianAvailable || softsubExhausted) return
  const requestEpoch = softsubRequestEpoch
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
    if (requestEpoch !== softsubRequestEpoch) return
    softsubReportId = result?.report_id || softsubReportId
    if (result?.subtitle_tracks?.length && injectEnsuredSubtitleTracks(result.subtitle_tracks)) {
      applySoftsubWhenReady()
      return
    }
    if (result?.has_subtitle_tracks || result?.status === 'ready') {
      const ready = await pollSoftsubOnce(requestEpoch)
      if (requestEpoch !== softsubRequestEpoch) return
      if (ready) return
    }
    if (result?.status === 'exhausted') {
      stopSoftsubHuntExhausted(showBanner)
      return
    }
    if (result?.status === 'not_needed') {
      // Dubbed stream or a Persian-language title: nothing to find, stay quiet.
      softsubExhausted = true
      clearSoftsubPoll()
      clearSoftsubBanner()
      dismissPlayerToast()
      return
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

// A throw inside the player (or its handlers) must never escalate to Nuxt's
// hydration error handler — before app:suspense:resolve that swaps the whole
// page for the 500 screen. Log it and keep the page; the player's own
// fallbacks (native src, mirrors, gateway) still run.
onErrorCaptured((error, _instance, info) => {
  console.error('[watch] player error contained:', info, error)
  reportClientDiag('contained-error', { info: String(info || '') }, error)
  return false
})

onMounted(() => {
  // Answered by the CDN edge, so it costs no origin round-trip and never
  // delays playback: the player starts while this is still in flight.
  void resolveRegion()
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
    && !activeVersionIsDub.value

  if (needsSoftsubEnsure) {
    requestPlaybackSubtitleEnsure({ showBanner: true })
  }
  document.addEventListener('visibilitychange', handleSoftsubVisibility)
})

watch([() => currentEpisode.value?.id, () => activeVersion.value?.id], (current, previous) => {
  autoUpgradeDone = false
  failedPlaybackSources.clear()
  reportedPlaybackGap = false
  // A session belongs to one file. Carrying it into another episode or version
  // would keep playing the old one, since it outranks every direct source.
  gatewaySession.value = null
  gatewayOriginUrl = ''
  gatewayAttempted.clear()
  lastPositionSeconds = 0
  ensureFastStartSource()
  if (!import.meta.client || mode.value !== 'full') return
  const episodeChanged = current[0] !== previous?.[0]
  const versionChanged = current[1] !== previous?.[1]
  if (!episodeChanged && !versionChanged) return

  softsubRequestEpoch += 1
  clearSoftsubPoll()
  clearSoftsubBanner()
  resetSoftsubRetry()
  // New file: its embedded tracks and the server verdict are unknown again.
  resetEmbeddedSubtitleProbe()
  softsubExhausted = false
  if (episodeChanged) softsubReportId = null
  if (activeSubtitleSourceTracks.value.length) return
  if (activeVersionIsDub.value) return
  requestPlaybackSubtitleEnsure({ showBanner: true })
})

// When the viewer switches episode and SoftSub is still missing, re-trigger ensure.
watch(() => confirmed.value, (isConfirmed, wasConfirmed) => {
  if (!import.meta.client || mode.value !== 'full') return
  if (!isConfirmed || wasConfirmed) return
  if (activeSubtitleSourceTracks.value.length) return
  if (activeVersionIsDub.value) return
  requestPlaybackSubtitleEnsure({ showBanner: true })
})

onBeforeUnmount(() => {
  softsubRequestEpoch += 1
  clearEmbeddedProbeWait()
  if (gatewayHeartbeat) clearInterval(gatewayHeartbeat)
  if (toastTimer) window.clearTimeout(toastTimer)
  if (softsubBannerTimer) window.clearTimeout(softsubBannerTimer)
  clearSoftsubPoll()
  clearSoftsubRetry()
  document.removeEventListener('visibilitychange', handleSoftsubVisibility)
})

useSeoMeta({
  title: () => item.value ? `${mode.value === 'trailer' ? 'تریلر' : 'تماشای'} ${item.value.title}` : 'پخش',
  description: () => item.value?.description || '',
  // The player is a view of the title page, not a page of its own: keep it out
  // of the index and hand every signal to the movie/series URL.
  robots: 'noindex, follow',
})
const seoSiteUrl = useRuntimeConfig().public.siteUrl
useHead(() => (item.value?.slug ? {
  link: [{ rel: 'canonical', href: absoluteUrl(seoSiteUrl, detailPath.value) }],
} : {}))
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
          :content-type="item.type"
          :can-report="mode === 'full'"
          :timeline-offset="gatewaySession?.start || 0"
          :timeline-total="gatewaySession?.duration || 0"
          :source-at-playhead="Boolean(gatewaySession)"
          :timeline-back-seconds="gatewaySession?.keepBehindSeconds || 0"
          @seek-beyond-window="handleSeekBeyondWindow"
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
          @sync-feedback="handleSubtitleSyncFeedback"
          @report-issue="handleReportIssue"
          @embedded-subtitles="handleEmbeddedSubtitles"
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

        <Transition
          enter-active-class="watch-msg-enter"
          leave-active-class="watch-msg-leave"
        >
          <aside
            v-if="sourceNotice"
            class="watch-msg overflow-hidden text-white"
            role="status"
            aria-live="polite"
          >
            <div class="watch-msg__row">
              <span class="watch-msg__icon" aria-hidden="true">
                <span class="watch-msg__spinner" />
              </span>
              <div class="watch-msg__body">
                <p class="watch-msg__title">{{ sourceNotice.title }}</p>
                <p class="watch-msg__detail">{{ sourceNotice.detail }}</p>
              </div>
            </div>
            <div class="watch-msg__track" aria-hidden="true">
              <div class="watch-msg__progress" />
            </div>
          </aside>
        </Transition>
      </div>

      <Transition
        enter-active-class="watch-msg-enter"
        leave-active-class="watch-msg-leave"
      >
        <div
          v-if="playbackBlocked"
          class="watch-blocked absolute inset-0 z-40 grid place-items-center bg-black/85 backdrop-blur-sm"
          role="alertdialog"
          aria-live="assertive"
        >
          <div class="watch-blocked__card mx-4 w-full max-w-md rounded-3xl bg-night-900/95 p-6 text-center text-white ring-1 ring-white/10 shadow-2xl sm:p-8">
            <span class="mx-auto grid size-14 place-items-center rounded-2xl bg-primary-500/15 text-primary-300 ring-1 ring-primary-400/25">
              <CinematicIcon name="film" class="size-7" />
            </span>
            <h2 class="mt-4 text-xl font-black leading-8">این فایل در مرورگر پخش نمی‌شود</h2>
            <p class="mt-2 text-sm leading-7 text-secondary">
              {{ playbackBlocked.container === 'mkv'
                ? 'این نسخه با ساختار MKV است و این نسخه از مرورگر آن را پخش نمی‌کند (iOS 17.1 به بعد مشکلی ندارد).'
                : 'این نسخه با کُدک HEVC/x265 انکود شده و مرورگر شما نمی‌تواند آن را رمزگشایی کند.' }}
              برای تماشای بی‌دردسر، اپ اندروید روایتو یا یک نسخهٔ دیگر را امتحان کنید.
            </p>
            <div class="mt-6 flex flex-col gap-3">
              <NuxtLink
                to="/app"
                class="inline-flex items-center justify-center gap-2 rounded-xl bg-primary-500 px-5 py-3 text-sm font-black text-night-950 transition hover:bg-primary-400"
              >
                <CinematicIcon name="play" class="size-5" />
                تماشا در اپ اندروید روایتو
              </NuxtLink>
              <a
                v-if="directDownloadLink"
                :href="directDownloadLink.url"
                target="_blank"
                rel="noopener"
                class="inline-flex items-center justify-center gap-2 rounded-xl bg-white/10 px-5 py-3 text-sm font-bold text-white ring-1 ring-white/15 transition hover:bg-white/15"
              >
                <CinematicIcon name="download" class="size-5" />
                دانلود مستقیم فایل{{ directDownloadLink.quality ? ` · ${directDownloadLink.quality}` : '' }}
              </a>
              <button
                type="button"
                class="text-xs font-semibold text-muted underline-offset-4 transition hover:text-secondary hover:underline"
                @click="playbackBlocked = null"
              >
                بستن و امتحان کیفیت/نسخهٔ دیگر
              </button>
            </div>
          </div>
        </div>
      </Transition>
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
    <RegionPlaybackModal :open="regionModalOpen" :country-name="regionCountryName" @close="closeRegionNotice" />
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
  font-size: 0.75rem;
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
  font-size: 0.75rem;
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
    font-size: 0.75rem;
    line-height: 1.4;
  }

  .watch-msg__dismiss {
    padding: 0.2rem 0.3rem;
    font-size: 0.75rem;
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
