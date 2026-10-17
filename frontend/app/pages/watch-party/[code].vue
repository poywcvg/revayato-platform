<script setup lang="ts">
import { reportClientDiag } from '~/utils/clientDiag'
import type {
  AppErrorDetails,
  DownloadLink,
  PlaybackQuality,
  PlaybackSnapshot,
  PlaybackTextTrack,
  PlaybackVersion,
  SubtitleSyncFeedback,
  WatchPartyPlaybackEvent,
  WatchPartyPlaybackState,
  WatchPartyStreamLink,
  WatchRoom,
} from '~/types'
import type { StreamGatewaySession } from '~/composables/useStreamGateway'
import type { ReportProblemType } from '~/composables/useContentReport'
import { pickStreamFriendlyLink, prefersBrowserSafeContainers, qualityHeightOf, streamNetworkProfile, videoCodecFamily, warmPlaybackOrigin } from '~/utils/downloadMeta'
import { buildPlaybackVersions, linksForVersionKind, pairSubtitleTracksForSource, resolvePlaybackVersion } from '~/utils/playbackVersions'
import { subtitleReadyNotice } from '~/utils/subtitlePolicy'
import { classifyPlayerToast, type PlayerToastMeta } from '~/utils/playerToast'

definePageMeta({ layout: 'player', middleware: 'auth', pageTransition: false })

interface PlayerHandle {
  applyRemotePlayback: (state: PlaybackSnapshot) => Promise<void>
  getPlaybackSnapshot: () => PlaybackSnapshot
  prepareResumeAt?: (seconds: number) => void
}

const route = useRoute()
const code = computed(() => String(route.params.code))
const { api } = useApi()
const { reportSubtitleSync } = useSubtitleSyncReport()
const { reportIssue } = useContentReport()
const { healFailure, pollFixedUrl } = usePlaybackSelfHeal()
const notifications = useNotifications()
const socket = useWatchPartySocket(code)
const player = useTemplateRef<PlayerHandle>('player')
const loading = ref(true)
const actionPending = ref(false)
const pageError = ref<AppErrorDetails | null>(null)
const playerReady = ref(false)
const playerSrc = ref('')
const playerNotice = ref('')
const playerToast = ref<(PlayerToastMeta & { id: number, message: string }) | null>(null)
const playbackBlocked = ref<{ family: string, container: string, url?: string } | null>(null)
const selectedQuality = ref<PlaybackQuality>('auto')
let toastSeq = 0
let autoUpgradeDone = false
const panelOpen = ref(false)
const focusMode = ref(false)
const partyFullscreen = ref(false)
const fullscreenChatOpen = ref(false)
const fullscreenChatReadCount = ref(0)
const inviteCopied = ref(false)
const justCreated = computed(() => String(route.query.created || '') === '1')
const panelActiveTab = ref<'chat' | 'members' | 'invite'>(justCreated.value ? 'invite' : 'chat')
const recreatePartyPath = computed(() => {
  const content = room.value?.content
  if (!content) return '/watch-party'
  const isMovie = content.type === 'movie'
  const seriesSlug = content.series?.slug || content.slug
  const query: Record<string, string> = {
    type: isMovie ? 'movie' : 'series',
    slug: isMovie ? content.slug : seriesSlug,
    title: isMovie ? content.title : (content.series?.title || content.title),
  }
  if (isMovie) query.id = String(content.id)
  else if (content.series?.id) query.id = String(content.series.id)
  return { path: '/watch-party', query }
})
let hostSyncTimer: ReturnType<typeof setTimeout> | undefined
let syncTightTimer: ReturnType<typeof setTimeout> | undefined
const syncTight = ref(false)
let noticeTimer: number | undefined
let inviteCopiedTimer: ReturnType<typeof setTimeout> | undefined
let lastAppliedStampMs = 0
let seekPublishTimer: ReturnType<typeof setTimeout> | undefined

const HOST_SYNC_PLAYING_MS = 1200
const HOST_SYNC_PAUSED_MS = 3000
const failedPlaybackSources = new Set<string>()

// --- playback gateway --------------------------------------------------------
// Per-viewer, not per-room: one member on Safari can be watching a rewrapped
// stream while everyone else plays the file directly. That stays in sync because
// the player reports and consumes film time, never its own media clock.
const { openGatewayStream, isGatewayUrl, gatewayMessageFor } = useStreamGateway()
const gatewaySession = ref<StreamGatewaySession | null>(null)
const gatewayAttempted = new Set<string>()
let gatewayOriginUrl = ''
let gatewayPending = false
let lastPositionSeconds = 0
let gatewayHeartbeat: ReturnType<typeof setInterval> | undefined
const hostLiveState = ref<WatchPartyPlaybackState | null>(null)

const room = computed(() => socket.room.value)
const isHost = computed(() => Boolean(room.value?.is_host))
const streamLinks = computed<WatchPartyStreamLink[]>(() => {
  const links = room.value?.content.stream_links || []
  if (links.length) return links.filter(link => Boolean(link.url))
  const fallback = room.value?.content.video_url
  return fallback ? [{ label: 'پخش', quality: '', url: fallback }] : []
})

const playbackVersions = computed(() => {
  const links: DownloadLink[] = streamLinks.value.map(link => ({
    label: link.label || link.quality || 'پخش',
    quality: link.quality || '',
    size_label: link.size_label || '',
    url: link.url,
    kind: link.kind || '',
    subtitle_type: link.subtitle_type || '',
  }))
  return buildPlaybackVersions(
    links,
    room.value?.content.subtitle_tracks || [],
    room.value?.content.video_url || '',
  )
})

const activeVersion = computed(() =>
  resolvePlaybackVersion(playbackVersions.value, playerSrc.value),
)
const playerSourceQuality = computed(() => {
  const sourceLink = streamLinks.value.find(link => link.url === playerSrc.value)
  const raw = sourceLink?.quality || activeVersion.value?.quality || ''
  const height = qualityHeightOf(raw, playerSrc.value)
  return height ? `${height}p` : raw
})

// --- parity with main player: quality / version scoping ----------------------
// Mirrors watch/[slug].vue: quality choices stay inside the active version kind
// (dub / softsub / original) so a quality switch never changes the language lane.
function versionScopedLinks() {
  const kind = activeVersion.value?.kind
  const pool: DownloadLink[] = streamLinks.value.map(link => ({
    label: link.label || link.quality || 'پخش',
    quality: link.quality || '',
    size_label: link.size_label || '',
    url: link.url,
    kind: link.kind || '',
    subtitle_type: link.subtitle_type || '',
  }))
  if (!kind || !pool.length) return pool
  const scoped = linksForVersionKind(pool, kind)
  return scoped.length ? scoped : pool
}

const playerQualities = computed<PlaybackQuality[]>(() => {
  const values = new Set<PlaybackQuality>()
  for (const link of versionScopedLinks()) {
    const height = qualityHeightOf(link.quality, link.url)
    if (height) values.add(`${height}p`)
  }
  return [...values].sort((a, b) => Number.parseInt(b, 10) - Number.parseInt(a, 10))
})

// 'movie' | 'series' — gates the «قسمت اشتباه» report option exactly like the main player.
const partyContentType = computed<'movie' | 'series' | ''>(() => {
  const content = room.value?.content
  if (!content) return ''
  return content.type === 'movie' ? 'movie' : 'series'
})

// Header meta: فصل/قسمت برای اپیزود، بدون تغییر ساختار دیتا.
const partyContentMeta = computed(() => {
  const content = room.value?.content
  if (!content) return ''
  if (content.type === 'episode' && content.series) {
    return `فصل ${Number(content.series.season_number || 1).toLocaleString('fa-IR')} · قسمت ${Number(content.series.episode_number || 0).toLocaleString('fa-IR')} · ${content.series.title}`
  }
  return content.secondary_title || ''
})

function qualityMatches(linkQuality: string | undefined, target: PlaybackQuality) {
  if (target === 'auto') return false
  const raw = String(linkQuality || '').toLowerCase()
  return raw.includes(target.toLowerCase()) || raw.includes(target.replace('p', ''))
}

const { ensurePlaybackSubtitles, getPlaybackSubtitleStatus } = usePlaybackSubtitleEnsure()
const ensuredSubtitles = ref<{ key: string, tracks: PlaybackTextTrack[] }>({ key: '', tracks: [] })
const subtitleEnsureTarget = computed(() => {
  const content = room.value?.content
  if (!content) return null
  if (content.type === 'movie') return { type: 'movie' as const, slug: content.slug, episodeId: 0 }
  const seriesSlug = content.series?.slug
  return seriesSlug ? { type: 'series' as const, slug: seriesSlug, episodeId: content.id } : null
})
const subtitleContentKey = computed(() => {
  const target = subtitleEnsureTarget.value
  return target ? `${target.type}:${target.slug}:${target.episodeId}` : ''
})
const activeSubtitleTracks = computed(() => {
  const version = activeVersion.value
  if (!version || version.burnedInSubtitles) return []
  const sourceTracks = room.value?.content.subtitle_tracks || []
  const softPool = streamLinks.value
  const paired = pairSubtitleTracksForSource(
    sourceTracks,
    playerSrc.value,
    softPool,
  )
  if (paired.length) return paired
  if (version.kind === 'softsub' && sourceTracks.length) return [...sourceTracks]
  if (version.subtitleTracks.length) return [...version.subtitleTracks]
  if (ensuredSubtitles.value.key === subtitleContentKey.value) return [...ensuredSubtitles.value.tracks]
  return []
})

// --- missing Persian subtitle ------------------------------------------------
// Same order as the main player: the player first looks inside the file it is
// streaming; only when that has no Persian track does this viewer ask the
// server once, then poll lightly until cues land or the server says none exist.
const SUBTITLE_POLL_MS = 5_000
const SUBTITLE_POLL_MAX = 24
const subtitleEnsureAsked = new Set<string>()
let subtitlePollTimer: ReturnType<typeof setTimeout> | undefined

function clearSubtitlePoll() {
  if (subtitlePollTimer) clearTimeout(subtitlePollTimer)
  subtitlePollTimer = undefined
}

function acceptEnsuredTracks(key: string, tracks: PlaybackTextTrack[] | undefined) {
  const usable = (tracks || []).filter(track => Boolean(track?.src))
  if (!usable.length || key !== subtitleContentKey.value) return false
  ensuredSubtitles.value = { key, tracks: usable }
  clearSubtitlePoll()
  showNotice(subtitleReadyNotice(true))
  return true
}

function pollEnsuredSubtitles(key: string, reportId: number | null, attempt: number) {
  clearSubtitlePoll()
  if (attempt >= SUBTITLE_POLL_MAX) return
  subtitlePollTimer = setTimeout(async () => {
    const target = subtitleEnsureTarget.value
    if (!target || key !== subtitleContentKey.value) return
    try {
      const result = await getPlaybackSubtitleStatus({ ...target, reportId })
      if (acceptEnsuredTracks(key, result?.subtitle_tracks)) return
      if (result?.status === 'exhausted') return
    } catch {
      // A missed poll is harmless; the next one retries.
    }
    pollEnsuredSubtitles(key, reportId, attempt + 1)
  }, SUBTITLE_POLL_MS)
}

async function ensureRoomSubtitles() {
  const target = subtitleEnsureTarget.value
  const key = subtitleContentKey.value
  const version = activeVersion.value
  if (!target || !key || !version || subtitleEnsureAsked.has(key)) return
  if (version.kind === 'dub' || version.burnedInSubtitles || activeSubtitleTracks.value.length) return
  subtitleEnsureAsked.add(key)
  try {
    const result = await ensurePlaybackSubtitles({
      ...target,
      version: version.kind,
      sourceUrl: gatewayOriginUrl || playerSrc.value,
      sync: true,
    })
    if (acceptEnsuredTracks(key, result?.subtitle_tracks)) return
    if (result?.status === 'exhausted' || result?.status === 'burned_in') return
    if (result?.queued || result?.status === 'queued' || result?.status === 'ready') {
      pollEnsuredSubtitles(key, result?.report_id || null, 0)
    }
  } catch {
    // Network hiccup: allow one more try the next time a file is probed.
    subtitleEnsureAsked.delete(key)
  }
}

function handleEmbeddedSubtitles(payload: { persian: boolean }) {
  if (payload.persian) {
    clearSubtitlePoll()
    return
  }
  void ensureRoomSubtitles()
}
const inviteUrl = computed(() =>
  import.meta.client
    ? `${window.location.origin}/watch-party/${encodeURIComponent(code.value)}`
    : `/watch-party/${encodeURIComponent(code.value)}`,
)
const returnPath = computed(() => {
  const content = room.value?.content
  if (!content) return '/'
  return content.type === 'movie'
    ? `/movies/${content.slug}`
    : `/series/${content.slug}`
})
const canPlay = computed(() => Boolean(playerSrc.value))
const onlineCount = computed(() => socket.members.value.filter(member => member.is_online).length)
const fullscreenUnreadCount = computed(() => Math.max(
  0,
  socket.messages.value.length - fullscreenChatReadCount.value,
))

function openPartyChat() {
  if (partyFullscreen.value) {
    openFullscreenChat()
    return
  }
  panelActiveTab.value = 'chat'
  panelOpen.value = true
}

function openPartyPanel(tab: 'chat' | 'members' | 'invite' = 'chat') {
  panelActiveTab.value = tab
  panelOpen.value = true
}

function openFullscreenChat() {
  fullscreenChatOpen.value = true
  fullscreenChatReadCount.value = socket.messages.value.length
}

function closeFullscreenChat() {
  fullscreenChatOpen.value = false
  fullscreenChatReadCount.value = socket.messages.value.length
}

function handlePartyFullscreenChange(active: boolean) {
  partyFullscreen.value = active
  fullscreenChatOpen.value = false
  fullscreenChatReadCount.value = socket.messages.value.length
}

function showNotice(message: string) {
  const text = String(message || '').trim()
  if (!text) return
  playerNotice.value = text
  toastSeq += 1
  playerToast.value = { id: toastSeq, message: text, ...classifyPlayerToast(text) }
  if (noticeTimer) window.clearTimeout(noticeTimer)
  noticeTimer = window.setTimeout(() => {
    playerNotice.value = ''
    playerToast.value = null
  }, 2800)
}

function dismissPlayerToast() {
  if (noticeTimer) window.clearTimeout(noticeTimer)
  noticeTimer = undefined
  playerNotice.value = ''
  playerToast.value = null
}

async function copyInviteLink() {
  if (!import.meta.client) return
  try {
    await navigator.clipboard.writeText(inviteUrl.value)
    inviteCopied.value = true
    showNotice('لینک دعوت کپی شد')
    if (inviteCopiedTimer) clearTimeout(inviteCopiedTimer)
    inviteCopiedTimer = setTimeout(() => { inviteCopied.value = false }, 2200)
  } catch {
    showNotice('کپی لینک انجام نشد — از تب دعوت استفاده کن')
    panelOpen.value = true
  }
}

function reportError(error: unknown, fallback: string) {
  pageError.value = notifications.notifyError(error, fallback)
}

function syncPlayerSource(url?: string | null) {
  // A running gateway session is this viewer's only working source; re-picking
  // from the link list would put them straight back on the file that failed.
  if (gatewaySession.value) return
  const requested = String(url || '').trim()
  const preferred = resolvePlaybackVersion(
    playbackVersions.value,
    requested && !failedPlaybackSources.has(requested)
      ? requested
      : (room.value?.content.video_url || ''),
  )
  const preferredUrl = preferred?.url && !failedPlaybackSources.has(preferred.url)
    ? preferred.url
    : ''
  const candidates = streamLinks.value
    .filter(link => Boolean(link.url) && !failedPlaybackSources.has(link.url))
    .map(link => ({
      label: link.label || link.quality || 'پخش',
      quality: link.quality || '',
      url: link.url,
    }))
  const friendly = pickStreamFriendlyLink(candidates, streamNetworkProfile())
  const next = String(
    (requested && !failedPlaybackSources.has(requested) ? requested : '')
    || preferredUrl
    || friendly?.url
    || room.value?.content.video_url
    || candidates[0]?.url
    || '',
  ).trim()
  if (next) warmPlaybackOrigin(next)
  if (next && next !== playerSrc.value) {
    playbackBlocked.value = null
    autoUpgradeDone = false
    playerReady.value = false
    playerSrc.value = next
  }
}

/**
 * Ask the backend to rewrap the failed file into HLS for this viewer alone.
 *
 * Resolves true once the session is playing. Only ever called from a dead end
 * in handleSourceFailed, after every direct mirror has been spent.
 */
async function tryGatewayPlayback(
  failedUrl: string,
  options: { position?: number, force?: boolean } = {},
) {
  const content = room.value?.content
  const source = String(failedUrl || '').trim()
  if (!content?.id || !source || gatewayPending || isGatewayUrl(source)) return false

  const kind = content.type === 'episode' ? 'episode' : 'movie'
  const key = `${kind}:${content.id}:${source}`
  if (!options.force && gatewayAttempted.has(key)) return false
  gatewayAttempted.add(key)

  gatewayPending = true
  try {
    const session = await openGatewayStream({
      kind,
      id: content.id,
      url: source,
      position: Math.max(0, Math.floor(options.position || 0)),
    })
    gatewayOriginUrl = source
    gatewaySession.value = session
    playbackBlocked.value = null
    playerReady.value = false
    playerSrc.value = session.playlist
    showNotice('پخش سازگار با این مرورگر فعال شد.')
    return true
  }
  catch (error) {
    gatewaySession.value = null
    showNotice(gatewayMessageFor((error as { code?: string })?.code || ''))
    return false
  }
  finally {
    gatewayPending = false
  }
}

/** Track the playhead in film seconds so a reopened session lands on it. */
function handlePartyPosition(snapshot: PlaybackSnapshot) {
  lastPositionSeconds = Math.max(0, Number(snapshot?.position_seconds) || 0)
}

/** Viewer aimed outside the session's window — reopen the stream there. */
async function handleSeekBeyondWindow(filmSeconds: number) {
  if (!gatewayOriginUrl) return
  lastPositionSeconds = filmSeconds
  await tryGatewayPlayback(gatewayOriginUrl, { position: filmSeconds, force: true })
}

// A paused viewer stops pulling segments and the session is reaped as "left".
// Re-reading the playlist is the cheapest thing that counts as presence.
watch(() => gatewaySession.value?.playlist || '', (playlist) => {
  if (gatewayHeartbeat) clearInterval(gatewayHeartbeat)
  gatewayHeartbeat = undefined
  if (!playlist || !import.meta.client) return
  gatewayHeartbeat = setInterval(() => {
    fetch(playlist, { method: 'GET', cache: 'no-store', credentials: 'omit' }).catch(() => {})
  }, 30_000)
})

/**
 * Automatic heal for every group-playback failure.
 *
 * Same intake and repair as the single player — filed once with room_code so
 * the server also broadcasts `playback.fix` to the whole room — plus a
 * `playback.failed` socket event so the host heals even when a guest is the
 * one whose player broke. Immediate retry when a better URL already exists,
 * background poll otherwise. One Persian notice, automatic recovery.
 */
function autoHealPartySource(failed: string, errCode: number | string, gatewayCode = '') {
  const content = room.value?.content
  if (!content?.id || !failed) return
  const isEpisode = content.type === 'episode'
  const failedUrl = String(failed).trim()
  // Tell the room right away (host + guests see progress, host files shared heal).
  socket.sendEvent({
    type: 'playback.failed',
    error_code: String(errCode ?? ''),
    source_url: failedUrl,
    played_seconds: lastPositionSeconds,
  })
  const played = player.value?.getPlaybackSnapshot()?.position_seconds || lastPositionSeconds
  void healFailure({
    type: isEpisode ? 'series' : 'movie',
    objectId: isEpisode ? (content.series?.id || 0) : content.id,
    slug: isEpisode ? (content.series?.slug || content.slug) : content.slug,
    episodeId: isEpisode ? content.id : 0,
    errorCode: String(errCode ?? ''),
    errorMessage: `auto heal watch-party code=${String(errCode ?? '')}`,
    gatewayCode,
    sourceUrl: failedUrl,
    version: activeVersion.value?.kind || '',
    roomCode: code.value,
    playedSeconds: played,
    hadPlayed: played > 1,
  }).then((healed) => {
    if (!healed) return
    showNotice(healed.messageFa)
    if (healed.shouldRetry && healed.fixedUrl && healed.fixedUrl !== playerSrc.value) {
      applyPartySource(healed.fixedUrl, 'پخش درست شد؛ ادامه از همین‌جا')
      return
    }
    if (healed.reportId && !healed.shouldRetry) {
      void pollFixedUrl(healed.reportId, failedUrl).then((fixed) => {
        if (fixed && fixed !== playerSrc.value) {
          applyPartySource(fixed, 'پخش درست شد؛ ادامه از همین‌جا')
        }
      })
    }
  })
}

function handleSourceFailed(payload: { src: string, code: number }) {
  const failed = String(payload?.src || playerSrc.value || '').trim()
  // File once for the whole room (dedupe per source) while local mirrors are
  // tried — the repair crawl runs in parallel instead of after giving up.
  if (failed && !isGatewayUrl(failed)) {
    autoHealPartySource(failed, Number(payload?.code) || 0)
  }
  // The session itself broke — usually reaped while paused. Reopen at the
  // playhead; only if that fails do we fall back to the direct mirrors, and
  // the session has to be cleared first or syncPlayerSource will refuse.
  if (failed && isGatewayUrl(failed)) {
    const origin = gatewayOriginUrl
    gatewaySession.value = null
    if (origin) {
      void tryGatewayPlayback(origin, { position: lastPositionSeconds, force: true }).then((ok) => {
        if (!ok) handleSourceFailed({ src: origin, code: Number(payload?.code) || 0 })
      })
      return
    }
  }
  if (failed) failedPlaybackSources.add(failed)
  const failedFamily = videoCodecFamily(failed)
  const failedCode = Number(payload?.code) || 0
  // Retire same-codec mirrors on decode failures so we do not churn HEVC files.
  if (failedFamily && (failedCode === 3 || failedCode === 4)) {
    for (const link of streamLinks.value) {
      if (link.url && videoCodecFamily(link.url, link.quality, link.label) === failedFamily) {
        failedPlaybackSources.add(link.url)
      }
    }
  }
  const candidates = streamLinks.value
    .filter(link => Boolean(link.url) && !failedPlaybackSources.has(link.url))
    .map(link => ({
      label: link.label || link.quality || 'پخش',
      quality: link.quality || '',
      url: link.url,
    }))
  const next = pickStreamFriendlyLink(candidates, streamNetworkProfile())
  if (next?.url && next.url !== playerSrc.value) {
    const previous = player.value?.getPlaybackSnapshot()
    if (previous && previous.position_seconds > 1) {
      player.value?.prepareResumeAt?.(previous.position_seconds)
    }
    warmPlaybackOrigin(next.url)
    playerReady.value = false
    playerSrc.value = next.url
    showNotice('منبع سازگارتر برای این مرورگر فعال شد')
    if (isHost.value && previous) sendPlayback('playback.sync', previous)
    return
  }
  // Every direct mirror is spent. Rewrapping is the last thing left, and it
  // keeps this viewer in the room instead of dropping them out of the party.
  // Same dead-end UX as the main player: a persistent panel instead of a toast
  // that vanishes while the frame stays black.
  const resumeAt = player.value?.getPlaybackSnapshot()?.position_seconds || lastPositionSeconds
  showNotice('در حال آماده‌سازی نسخهٔ سازگار با این مرورگر…')
  void tryGatewayPlayback(failed, { position: resumeAt }).then((ok) => {
    if (ok) {
      playbackBlocked.value = null
      return
    }
    if (failedFamily === 'hevc' || failedFamily === 'av1') {
      playbackBlocked.value = { family: failedFamily, container: '' }
      showNotice('این فایل با کُدک HEVC/AV1 است و این مرورگر نمی‌تواند آن را رمزگشایی کند.')
      return
    }
    if (prefersBrowserSafeContainers() && /\.mkv(?:\?|$)/i.test(failed)) {
      playbackBlocked.value = { family: failedFamily, container: 'mkv' }
      showNotice('این نسخه از مرورگر فایل MKV را پخش نمی‌کند. کیفیت دیگری را انتخاب کن یا مرورگر/iOS را به‌روز کن.')
      return
    }
    playbackBlocked.value = { family: failedFamily, container: '' }
    showNotice('این مرورگر این فایل را پخش نکرد. کیفیت دیگری را امتحان کن.')
  })
}

function pickUpgradeLink(links: DownloadLink[], currentUrl: string) {
  const currentHeight = qualityHeightOf(
    links.find(link => link.url === currentUrl)?.quality,
    currentUrl,
  ) || 0
  const profile = streamNetworkProfile()
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

// Same fast-start/auto-upgrade behaviour as watch/[slug].vue, but host-only:
// guests stay locked to the host's stream and only get the notice.
function handleBufferHealth(aheadSeconds: number) {
  if (!isHost.value || autoUpgradeDone || selectedQuality.value !== 'auto') return
  if (/\.m3u8(?:\?|$)/i.test(playerSrc.value)) return
  const profile = streamNetworkProfile()
  const threshold = profile === 'fast' ? 14 : profile === 'lean' ? 28 : 20
  if (aheadSeconds < threshold) return
  const links = versionScopedLinks().filter(link => Boolean(link.url) && !failedPlaybackSources.has(link.url))
  const upgrade = pickUpgradeLink(links, playerSrc.value)
  if (!upgrade?.url) return
  const nextHeight = qualityHeightOf(upgrade.quality, upgrade.url)
  autoUpgradeDone = profile !== 'fast' || nextHeight >= 1000
  applyPartySource(upgrade.url, `کیفیت بهتر فعال شد · ${upgrade.quality || 'HD'}`)
}

function applyPartySource(url: string, notice?: string) {
  if (!url || url === playerSrc.value) return
  const previous = player.value?.getPlaybackSnapshot()
  if (previous && previous.position_seconds > 1) {
    player.value?.prepareResumeAt?.(previous.position_seconds)
  }
  playbackBlocked.value = null
  warmPlaybackOrigin(url)
  playerReady.value = false
  playerSrc.value = url
  if (notice) showNotice(notice)
  if (isHost.value && previous) sendPlayback('playback.sync', previous)
}

function selectQuality(quality: PlaybackQuality) {
  selectedQuality.value = quality
  autoUpgradeDone = quality !== 'auto'
  if (!isHost.value) {
    showNotice('کیفیت مشترک را میزبان انتخاب می‌کند')
    return
  }
  if (/\.m3u8(?:\?|$)/i.test(playerSrc.value)) {
    showNotice(quality === 'auto' ? 'کیفیت خودکار و تطبیقی فعال شد' : `کیفیت ${quality} انتخاب شد`)
    return
  }
  const links = versionScopedLinks()
  if (!links.length) {
    showNotice(quality === 'auto' ? 'کیفیت خودکار فعال شد' : `کیفیت ${quality} انتخاب شد`)
    return
  }
  const match = quality === 'auto'
    ? pickStreamFriendlyLink(links, streamNetworkProfile())
    : pickStreamFriendlyLink(links.filter(link => qualityMatches(link.quality, quality)), streamNetworkProfile())
      || pickStreamFriendlyLink(links, streamNetworkProfile())
  if (match?.url && match.url !== playerSrc.value) {
    applyPartySource(
      match.url,
      quality === 'auto' ? `شروع سریع · ${match.quality || 'آماده'}` : `ادامه از همین‌جا · ${match.quality || quality}`,
    )
    return
  }
  showNotice(quality === 'auto' ? 'کیفیت خودکار فعال شد' : `کیفیت ${quality} انتخاب شد`)
}

function handleReportIssue(payload: { problemType: ReportProblemType, detail: string }) {
  const content = room.value?.content
  if (!content) return
  const isEpisode = content.type === 'episode'
  void reportIssue({
    type: isEpisode ? 'series' : 'movie',
    objectId: isEpisode ? (content.series?.id || 0) : content.id,
    slug: isEpisode ? (content.series?.slug || content.slug) : content.slug,
    episodeId: isEpisode ? content.id : 0,
    problemType: payload.problemType,
    version: activeVersion.value?.kind || '',
    sourceUrl: playerSrc.value || '',
    detail: payload.detail,
  })
}

async function loadRoom() {
  loading.value = true
  pageError.value = null
  socket.disconnect(false)
  try {
    const found = await api<WatchRoom>(`/watch-party/rooms/${code.value}/`)
    socket.setInitialRoom(found)
    syncPlayerSource(found.content.video_url)
    if (found.status !== 'active') {
      pageError.value = {
        title: found.status === 'expired' ? 'زمان اتاق تمام شده' : 'اتاق پایان یافته',
        message: found.status === 'expired' ? 'مدت استفاده از این اتاق به پایان رسیده است.' : 'میزبان این اتاق را بسته است.',
        hint: 'یک اتاق تازه بساز یا از میزبان بخواه لینک تازه‌ای بفرستد.',
        fields: [],
      }
      return
    }
    if (!found.content.video_url && !(found.content.stream_links || []).length) {
      pageError.value = {
        title: 'منبع پخش پیدا نشد',
        message: 'برای این عنوان هنوز لینک پخش آنلاین ثبت نشده است.',
        hint: 'از صفحه فیلم لینک دانلود/پخش را اضافه کن و دوباره اتاق بساز.',
        fields: [],
      }
    }
    const joined = await api<WatchRoom>(
      `/watch-party/rooms/${code.value}/join/`,
      { method: 'POST' },
    )
    socket.setInitialRoom(joined)
    syncPlayerSource(joined.content.video_url || joined.playback_state?.stream_url)
    socket.connect()
  } catch (error) {
    reportError(error, 'ورود به اتاق ممکن نشد.')
  } finally {
    loading.value = false
  }
}

function stateStampMs(state: WatchPartyPlaybackState) {
  const serverStamp = Number(state.server_time_ms)
  if (Number.isFinite(serverStamp) && serverStamp > 0) return serverStamp
  const parsed = Date.parse(state.updated_at)
  return Number.isFinite(parsed) ? parsed : 0
}

function adjustedState(state: WatchPartyPlaybackState): PlaybackSnapshot {
  let position = state.position_seconds
  if (state.is_playing) {
    const anchor = stateStampMs(state)
    const elapsed = anchor
      ? Math.max(0, (socket.serverNowMs() - anchor) / 1000)
      : 0
    position += elapsed * (state.playback_rate || 1)
  }
  return {
    is_playing: state.is_playing,
    position_seconds:
      state.duration_seconds > 0
        ? Math.min(position, state.duration_seconds)
        : position,
    duration_seconds: state.duration_seconds,
    playback_rate: state.playback_rate,
  }
}

async function applyPartyState(state: WatchPartyPlaybackState, force = false) {
  if (state.stream_url) syncPlayerSource(state.stream_url)
  if (!playerReady.value) return
  const stamp = stateStampMs(state)
  if (!force && stamp && lastAppliedStampMs && stamp + 250 < lastAppliedStampMs) return
  if (stamp) lastAppliedStampMs = Math.max(lastAppliedStampMs, stamp)
  await player.value?.applyRemotePlayback(adjustedState(state))
}

async function handleRemotePlayback(event: WatchPartyPlaybackEvent) {
  if (isHost.value) return
  await applyPartyState(event.state, event.type === 'playback.seek' || event.type === 'playback.play' || event.type === 'playback.pause')
}

function sendPlayback(
  type: 'playback.play' | 'playback.pause' | 'playback.seek' | 'playback.sync',
  state: PlaybackSnapshot,
) {
  if (!isHost.value) return
  // A gateway playlist is a per-viewer HLS session, not a shared mirror.
  // Broadcasting it would leak a private session URL and trip the server's
  // stream allowlist; guests stay on the direct mirror (or open their own
  // gateway) while position/timing still syncs.
  const src = String(playerSrc.value || '').trim()
  socket.sendEvent({
    type,
    ...state,
    stream_url: src && !isGatewayUrl(src) ? src : undefined,
  })
}

function refreshHostLiveState() {
  if (!isHost.value || !playerReady.value) return
  const snapshot = player.value?.getPlaybackSnapshot()
  if (snapshot) {
    hostLiveState.value = {
      ...snapshot,
      updated_by: room.value?.host ?? null,
      updated_at: new Date().toISOString(),
      server_time_ms: Date.now(),
    }
  }
}

function publishHostPlaybackState() {
  if (!isHost.value || !playerReady.value || socket.connectionStatus.value !== 'connected') return
  refreshHostLiveState()
  const state = player.value?.getPlaybackSnapshot()
  if (state) sendPlayback('playback.sync', state)
}

function scheduleHostSync() {
  if (hostSyncTimer) clearTimeout(hostSyncTimer)
  hostSyncTimer = undefined
  if (!isHost.value) return
  const playing = Boolean(player.value?.getPlaybackSnapshot()?.is_playing)
  hostSyncTimer = setTimeout(() => {
    publishHostPlaybackState()
    scheduleHostSync()
  }, playing ? HOST_SYNC_PLAYING_MS : HOST_SYNC_PAUSED_MS)
}

async function handlePlayerReady() {
  playerReady.value = true
  playbackBlocked.value = null
  if (socket.playbackState.value) await applyPartyState(socket.playbackState.value, true)
  socket.requestSync()
  if (isHost.value) scheduleHostSync()
}

function onHostPlay(state: PlaybackSnapshot) {
  if (seekPublishTimer) clearTimeout(seekPublishTimer)
  refreshHostLiveState()
  sendPlayback('playback.play', state)
  scheduleHostSync()
}

function onHostPause(state: PlaybackSnapshot) {
  if (seekPublishTimer) clearTimeout(seekPublishTimer)
  refreshHostLiveState()
  sendPlayback('playback.pause', state)
  scheduleHostSync()
}

function onHostSeek(_state: PlaybackSnapshot) {
  if (seekPublishTimer) clearTimeout(seekPublishTimer)
  seekPublishTimer = setTimeout(() => {
    const fresh = player.value?.getPlaybackSnapshot()
    if (fresh) {
      refreshHostLiveState()
      sendPlayback('playback.seek', fresh)
    }
    scheduleHostSync()
  }, 120)
}

async function activateMemberPlayback() {
  if (socket.playbackState.value) await applyPartyState(socket.playbackState.value, true)
  socket.requestSync()
  showNotice('در حال هماهنگ‌سازی با میزبان…')
}

function onSyncCorrection() {
  syncTight.value = true
  if (syncTightTimer) clearTimeout(syncTightTimer)
  syncTightTimer = setTimeout(() => { syncTight.value = false }, 1200)
}

function handleSubtitleSyncFeedback(feedback: SubtitleSyncFeedback) {
  const content = room.value?.content
  if (!content) return
  // Party rooms describe a movie or a single episode; map to the catalog target.
  const isEpisode = content.type === 'episode'
  void reportSubtitleSync({
    type: isEpisode ? 'series' : 'movie',
    objectId: isEpisode ? (content.series?.id || 0) : content.id,
    episodeId: isEpisode ? content.id : 0,
    feedback,
  })
}

function selectStream(link: WatchPartyStreamLink) {
  if (!isHost.value || !link.url || link.url === playerSrc.value) return
  applyPartySource(link.url, `کیفیت ${link.quality || link.label} · ادامه از همین‌جا`)
}

function selectVersion(version: PlaybackVersion) {
  if (!isHost.value || !version.url) return
  if (version.url === playerSrc.value) return
  autoUpgradeDone = false
  applyPartySource(
    version.url,
    version.kind === 'dub' ? 'دوبله · ادامه از همین‌جا' : `${version.label} · ادامه از همین‌جا`,
  )
}

async function leaveRoom() {
  if (actionPending.value) return
  actionPending.value = true
  try {
    socket.disconnect()
    await api(`/watch-party/rooms/${code.value}/leave/`, { method: 'POST' })
    await navigateTo(returnPath.value)
  } catch (error) {
    reportError(error, 'خروج از اتاق انجام نشد.')
  } finally {
    actionPending.value = false
  }
}

async function endRoom() {
  if (actionPending.value) return
  actionPending.value = true
  try {
    const ended = await api<WatchRoom>(
      `/watch-party/rooms/${code.value}/end/`,
      { method: 'POST' },
    )
    socket.setInitialRoom(ended)
    socket.disconnect(false)
  } catch (error) {
    reportError(error, 'پایان دادن به اتاق انجام نشد.')
  } finally {
    actionPending.value = false
  }
}

watch(
  () => socket.lastPlaybackEvent.value?.sequence,
  () => {
    const event = socket.lastPlaybackEvent.value
    if (event) void handleRemotePlayback(event)
  },
)

// A fixed URL broadcast by the server after POST /api/catalog/playback-failure/.
// Applies to whoever is still on the dead source — host and guests alike —
// without a reload, and announces it once in Persian.
watch(
  () => socket.lastPlaybackFix.value?.sequence,
  () => {
    const fix = socket.lastPlaybackFix.value
    if (!fix) return
    if (fix.messageFa) showNotice(fix.messageFa)
    const fixed = String(fix.fixedUrl || '').trim()
    if (fixed && fixed !== playerSrc.value) {
      applyPartySource(fixed, 'پخش درست شد؛ ادامه از همین‌جا')
    }
  },
)

// Another member's player broke: the host files the shared heal so one repair
// covers the whole room instead of one report per member.
watch(
  () => socket.lastMemberFailed.value?.sequence,
  () => {
    const failed = socket.lastMemberFailed.value
    if (!failed || !isHost.value) return
    if (failed.messageFa) showNotice(failed.messageFa)
    const failedUrl = String(failed.sourceUrl || playerSrc.value || '').trim()
    if (failedUrl) autoHealPartySource(failedUrl, failed.errorCode || 'member_failed')
  },
)

watch(
  () => room.value?.content.video_url,
  (url) => {
    if (url && !playerSrc.value) syncPlayerSource(url)
  },
)

watch(
  () => socket.connectionStatus.value,
  async (status, previous) => {
    if (status !== 'connected' || !previous || previous === 'connected') return
    if (isHost.value) {
      scheduleHostSync()
      publishHostPlaybackState()
      return
    }
    socket.requestSync()
    if (socket.playbackState.value) await applyPartyState(socket.playbackState.value, true)
    showNotice('دوباره با میزبان هماهنگ شد')
  },
)

watch(isHost, (host) => {
  if (host) scheduleHostSync()
  else if (hostSyncTimer) {
    clearTimeout(hostSyncTimer)
    hostSyncTimer = undefined
  }
})

watch(() => socket.messages.value.length, (count) => {
  if (partyFullscreen.value && fullscreenChatOpen.value) {
    fullscreenChatReadCount.value = count
  }
})

watch(() => socket.syncRequestSequence.value, () => {
  if (isHost.value) publishHostPlaybackState()
})

watch(panelOpen, (open) => {
  if (!import.meta.client || window.matchMedia('(min-width: 1024px)').matches) return
  document.body.classList.toggle('party-panel-open', open)
}, { flush: 'post' })

function handleTabVisibility() {
  if (import.meta.server || document.hidden) return
  if (socket.connectionStatus.value !== 'connected') return
  if (isHost.value) {
    // Tabs throttled by the browser: publish the exact fresh state at once.
    clearHostSync()
    publishHostPlaybackState()
    scheduleHostSync()
    return
  }
  // Guests: hidden tabs drift (tab throttling); re-align immediately on return.
  socket.requestSync()
  if (socket.playbackState.value) {
    void applyPartyState(socket.playbackState.value, true)
    showNotice('هم‌زمان با میزبان')
  }
}

function handleRoomKeydown(event: KeyboardEvent) {
  if (event.key !== 'Escape') return
  if (fullscreenChatOpen.value) closeFullscreenChat()
  else if (panelOpen.value && !window.matchMedia('(min-width: 1024px)').matches) panelOpen.value = false
}

function clearHostSync() {
  if (hostSyncTimer) clearTimeout(hostSyncTimer)
  hostSyncTimer = undefined
}

// Same guard as the watch page: a player throw must not become the 500 screen.
onErrorCaptured((error, _instance, info) => {
  console.error('[watch-party] player error contained:', info, error)
  reportClientDiag('contained-error', { info: String(info || '') }, error)
  return false
})

onMounted(() => {
  void loadRoom()
  if (import.meta.client && window.matchMedia('(min-width: 1024px)').matches) {
    panelOpen.value = true
  } else if (justCreated.value) {
    // New hosts land on invite tab so they can share immediately.
    panelOpen.value = true
  }
  document.addEventListener('visibilitychange', handleTabVisibility)
  window.addEventListener('keydown', handleRoomKeydown)
})

onBeforeUnmount(() => {
  clearSubtitlePoll()
  document.removeEventListener('visibilitychange', handleTabVisibility)
  window.removeEventListener('keydown', handleRoomKeydown)
  document.body.classList.remove('party-panel-open')
  if (hostSyncTimer) clearTimeout(hostSyncTimer)
  hostSyncTimer = undefined
  if (gatewayHeartbeat) clearInterval(gatewayHeartbeat)
  gatewayHeartbeat = undefined
  if (seekPublishTimer) clearTimeout(seekPublishTimer)
  seekPublishTimer = undefined
  if (syncTightTimer) clearTimeout(syncTightTimer)
  syncTightTimer = undefined
  if (noticeTimer) window.clearTimeout(noticeTimer)
  if (inviteCopiedTimer) clearTimeout(inviteCopiedTimer)
  socket.disconnect(false)
})

useSeoMeta({
  title: () =>
    room.value ? `تماشای گروهی ${room.value.content.title}` : 'تماشای گروهی',
  description: 'اتاق خصوصی تماشای هم‌زمان فیلم و سریال',
})
</script>

<template>
  <div class="party-room theme-media-dark relative overflow-x-clip bg-[#050505] text-white">
    <div
      class="pointer-events-none absolute inset-0 opacity-70"
      aria-hidden="true"
      :style="room?.content.backdrop_url
        ? {
          backgroundImage: `linear-gradient(180deg, rgba(5,5,5,.55), rgba(5,5,5,.92) 42%, #050505), url(${room.content.backdrop_url})`,
          backgroundSize: 'cover',
          backgroundPosition: 'center top',
        }
        : undefined"
    />

    <div class="relative z-10 mx-auto max-w-[var(--layout-max)] px-[var(--layout-gutter)] py-3 sm:py-4">
      <div v-if="loading" class="grid min-h-[70vh] place-items-center">
        <div class="text-center">
          <span class="mx-auto block size-11 animate-spin rounded-full border-2 border-white/15 border-t-primary-500" />
          <p class="mt-4 text-sm font-bold text-white/60">در حال ورود به اتاق خصوصی…</p>
        </div>
      </div>

      <section
        v-else-if="pageError && !room"
        class="mx-auto grid min-h-[65vh] max-w-lg place-items-center text-center"
      >
        <div class="rounded-3xl border border-white/10 bg-white/[.04] p-7">
          <span class="mx-auto grid size-14 place-items-center rounded-2xl bg-error/10 text-error ring-1 ring-error/20">
            <CinematicIcon name="alert-triangle" class="size-7" />
          </span>
          <h1 class="mt-5 text-xl font-black">{{ pageError.title }}</h1>
          <p class="mt-2 text-sm leading-7 text-white/60">{{ pageError.message }}</p>
          <p v-if="pageError.hint" class="mt-2 text-xs leading-6 text-white/40">{{ pageError.hint }}</p>
          <div class="mt-6 flex justify-center gap-2">
            <button type="button" class="min-h-11 rounded-xl bg-primary-500 px-5 text-sm font-black text-night-950 hover:bg-primary-400" @click="loadRoom">
              تلاش دوباره
            </button>
            <NuxtLink to="/" class="inline-flex min-h-11 items-center rounded-xl border border-white/10 bg-white/5 px-5 text-sm font-black text-white/70 hover:text-white">
              صفحه اصلی
            </NuxtLink>
          </div>
        </div>
      </section>

      <template v-else-if="room">
        <header
          class="mb-3 grid gap-3 transition duration-300 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-center"
          :class="focusMode && 'opacity-0 pointer-events-none lg:opacity-100 lg:pointer-events-auto'"
        >
          <div class="flex min-w-0 items-center gap-3">
            <NuxtLink
              :to="returnPath"
              class="grid size-11 shrink-0 place-items-center rounded-xl border border-white/10 bg-white/5 text-white/70 transition hover:border-primary-500/35 hover:bg-primary-500/10 hover:text-primary-300"
              aria-label="بازگشت"
            >
              <CinematicIcon name="arrow-right" class="size-5" />
            </NuxtLink>
            <div class="min-w-0">
              <div class="flex flex-wrap items-center gap-2">
                <span class="inline-flex items-center gap-1.5 text-[11px] font-black text-crimson-hover">
                  <span class="size-1.5 animate-pulse rounded-full bg-crimson" />تماشای گروهی
                </span>
                <span v-if="isHost" class="rounded-md bg-primary-500/20 px-1.5 py-0.5 text-[11px] font-black text-primary-300">میزبان</span>
                <span class="rounded-md bg-white/8 px-1.5 py-0.5 text-[11px] font-bold text-white/50">
                  {{ onlineCount.toLocaleString('fa-IR') }} آنلاین
                </span>
              </div>
              <h1 class="mt-1 truncate text-base font-black sm:text-xl" dir="auto">{{ room.content.title }}</h1>
              <p v-if="partyContentMeta" class="mt-0.5 truncate text-[11px] text-white/45" dir="auto">{{ partyContentMeta }}</p>
              <p class="mt-1 flex flex-wrap items-center gap-1.5 text-[11px]">
                <span v-if="activeVersion" class="rounded-md bg-white/8 px-1.5 py-0.5 font-bold text-white/55">
                  {{ activeVersion.kind === 'dub' ? 'دوبله فارسی' : activeVersion.label }}
                </span>
                <span v-if="playerSourceQuality" class="rounded-md bg-white/8 px-1.5 py-0.5 font-latin font-bold text-white/55" dir="ltr">{{ playerSourceQuality }}</span>
                <span v-if="gatewaySession" class="rounded-md bg-info/15 px-1.5 py-0.5 font-bold text-info">پخش سازگار</span>
              </p>
            </div>
          </div>
          <div
            class="party-actions"
            :class="isHost ? 'party-actions--host' : 'party-actions--guest'"
            role="toolbar"
            aria-label="اقدامات اتاق"
          >
            <button
              v-if="isHost"
              type="button"
              class="party-btn party-btn--invite"
              :aria-label="inviteCopied ? 'لینک دعوت کپی شد' : 'کپی لینک دعوت'"
              @click="copyInviteLink"
            >
              <CinematicIcon :name="inviteCopied ? 'check' : 'user-plus'" class="party-btn__icon" />
              <span class="party-btn__label">{{ inviteCopied ? 'شد' : 'دعوت' }}</span>
            </button>
            <button
              type="button"
              class="party-btn party-btn--cinema"
              :class="focusMode && 'is-active'"
              :aria-pressed="focusMode"
              :aria-label="focusMode ? 'خروج از حالت سینما' : 'حالت سینما'"
              @click="focusMode = !focusMode"
            >
              <CinematicIcon :name="focusMode ? 'eye' : 'eye-off'" class="party-btn__icon" />
              <span class="party-btn__label">{{ focusMode ? 'پنل' : 'سینما' }}</span>
            </button>
            <button
              type="button"
              class="party-btn party-btn--chat lg:!hidden"
              aria-controls="watch-party-panel"
              :aria-expanded="panelOpen"
              aria-label="باز کردن گفت‌وگو"
              @click="panelOpen ? panelOpen = false : openPartyPanel('chat')"
            >
              <CinematicIcon name="comments" class="party-btn__icon" />
              <span class="party-btn__label">چت</span>
              <span
                v-if="socket.messages.value.length"
                class="party-btn__badge"
              >
                {{ socket.messages.value.length.toLocaleString('fa-IR') }}
              </span>
            </button>
          </div>
        </header>

        <UiErrorAlert v-if="pageError" class="mb-4" :error="pageError" @close="pageError = null" />

        <section
          v-if="room.status !== 'active'"
          class="mx-auto grid min-h-[55vh] max-w-xl place-items-center text-center"
        >
          <div class="rounded-3xl border border-white/10 bg-white/[.04] p-8">
            <span class="mx-auto grid size-14 place-items-center rounded-2xl bg-wine text-crimson-hover ring-1 ring-crimson/25">
              <CinematicIcon name="clock" class="size-7" />
            </span>
            <h2 class="mt-5 text-xl font-black">این تماشای گروهی پایان یافته است</h2>
            <p class="mt-2 text-sm leading-7 text-white/60">برای شروع دوباره، یک اتاق خصوصی تازه بسازید.</p>
            <div class="mt-6 flex flex-wrap justify-center gap-2">
              <NuxtLink
                :to="recreatePartyPath"
                class="inline-flex min-h-11 items-center rounded-xl bg-primary-500 px-5 text-sm font-black text-night-950 hover:bg-primary-400"
              >
                ساخت اتاق تازه
              </NuxtLink>
              <NuxtLink
                :to="returnPath"
                class="inline-flex min-h-11 items-center rounded-xl border border-white/10 bg-white/5 px-5 text-sm font-black text-white/70 hover:text-white"
              >
                بازگشت به محتوا
              </NuxtLink>
            </div>

          </div>
        </section>

        <div
          v-else
          class="party-room__layout grid items-start gap-4"
          :class="focusMode
 ? 'lg:grid-cols-1'
            : 'lg:grid-cols-[minmax(0,1fr)_340px] xl:grid-cols-[minmax(0,1fr)_370px]'"
        >
          <section class="party-room__stage min-w-0" aria-label="پخش هم‌زمان">
            <div v-if="canPlay" class="party-room__player-frame relative overflow-hidden rounded-2xl ring-1 ring-white/10">
              <VideoPlayer
                ref="player"
                :src="playerSrc"
                :poster="room.content.backdrop_url || room.content.poster_url || ''"
                :title="room.content.title"
                :subtitle-tracks="activeSubtitleTracks"
                :playback-versions="playbackVersions"
                :active-version-id="activeVersion?.id || ''"
                :source-quality="playerSourceQuality"
                :quality="selectedQuality"
                :available-qualities="playerQualities"
                :content-type="partyContentType"
                :locked="!isHost"
                :timeline-offset="gatewaySession?.start || 0"
                :timeline-total="gatewaySession?.duration || 0"
                :source-at-playhead="Boolean(gatewaySession)"
                :timeline-back-seconds="gatewaySession?.keepBehindSeconds || 0"
                autoplay
                party-sync
                @ready="handlePlayerReady"
                @position-snapshot="handlePartyPosition"
                @seek-beyond-window="handleSeekBeyondWindow"
                @playback-play="onHostPlay"
                @playback-pause="onHostPause"
                @playback-seek="onHostSeek"
                @buffer-health="handleBufferHealth"
                @quality-request="selectQuality"
                @version-request="selectVersion"
                @source-failed="handleSourceFailed"
                @notice="showNotice"
                @fullscreen-change="handlePartyFullscreenChange"
                @sync-correction="onSyncCorrection"
                @sync-feedback="handleSubtitleSyncFeedback"
                @report-issue="handleReportIssue"
                @embedded-subtitles="handleEmbeddedSubtitles"
              >
                <template #fullscreen-overlay="{ isFullscreen }">
                  <div
                    v-if="isFullscreen"
                    class="party-fullscreen-layer"
                    data-player-ui
                    @click.stop
                  >
                    <Transition
                      enter-active-class="transition duration-200"
                      enter-from-class="opacity-0"
                      leave-active-class="transition duration-150"
                      leave-to-class="opacity-0"
                    >
                      <button
                        v-if="fullscreenChatOpen"
                        type="button"
                        class="party-fullscreen-scrim"
                        aria-label="بستن گفت‌وگوی تمام‌صفحه"
                        @click="closeFullscreenChat"
                      />
                    </Transition>

                    <Transition
                      enter-active-class="transition duration-200 ease-out"
                      enter-from-class="translate-y-4 opacity-0 sm:translate-y-0 sm:-translate-x-4"
                      leave-active-class="transition duration-150 ease-in"
                      leave-to-class="translate-y-4 opacity-0 sm:translate-y-0 sm:-translate-x-4"
                    >
                      <aside
                        v-if="fullscreenChatOpen"
                        id="party-fullscreen-chat"
                        class="party-fullscreen-chat"
                        aria-label="گفت‌وگوی زنده در تمام‌صفحه"
                      >
                        <header class="party-fullscreen-chat__header">
                          <div class="min-w-0">
                            <div class="flex items-center gap-2">
                              <span class="size-2 rounded-full" :class="socket.connectionStatus.value === 'connected' ? 'bg-success' : 'bg-warning'" />
                              <p class="truncate text-sm font-black">گفت‌وگوی تماشای گروهی</p>
                            </div>
                            <p class="mt-1 text-[11px] text-white/45">
                              {{ onlineCount.toLocaleString('fa-IR') }} نفر آنلاین · ویدیو هم‌زمان ادامه دارد
                            </p>
                          </div>
                          <button
                            type="button"
                            class="grid size-11 shrink-0 place-items-center rounded-xl bg-white/8 text-white/70 transition hover:bg-white/15 hover:text-white"
                            aria-label="بستن گفت‌وگو"
                            @click="closeFullscreenChat"
                          >
                            <CinematicIcon name="x" class="size-5" />
                          </button>
                        </header>

                        <WatchPartyChat
                          compact
                          :messages="socket.messages.value"
                          :disabled="socket.connectionStatus.value !== 'connected' || room.status !== 'active'"
                          @send="socket.sendChat"
                        />
                      </aside>
                    </Transition>

                    <button
                      v-if="!fullscreenChatOpen"
                      type="button"
                      class="party-fullscreen-chat-trigger"
                      aria-controls="party-fullscreen-chat"
                      aria-expanded="false"
                      @click="openFullscreenChat"
                    >
                      <CinematicIcon name="comments" class="size-5" />
                      <span>چت</span>
                      <span
                        v-if="fullscreenUnreadCount"
                        class="grid min-w-5 place-items-center rounded-full bg-night-950/20 px-1.5 py-0.5 font-latin text-[11px]"
                      >
                        {{ Math.min(fullscreenUnreadCount, 99) }}
                      </span>
                    </button>
                  </div>
                </template>
              </VideoPlayer>
              <Transition
                enter-active-class="transition duration-200"
                enter-from-class="opacity-0"
                leave-active-class="transition duration-150"
                leave-to-class="opacity-0"
              >
                <div
                  v-if="playbackBlocked"
                  class="absolute inset-0 z-30 grid place-items-center bg-black/85 p-4 text-center"
                  role="alertdialog"
                  aria-live="assertive"
                >
                  <div class="w-full max-w-sm rounded-2xl bg-night-900/95 p-5 ring-1 ring-white/10">
                    <span class="mx-auto grid size-12 place-items-center rounded-2xl bg-primary-500/15 text-primary-300 ring-1 ring-primary-400/25">
                      <CinematicIcon name="film" class="size-6" />
                    </span>
                    <p class="mt-3 text-sm font-black">این فایل در مرورگر پخش نمی‌شود</p>
                    <p class="mt-1.5 text-xs leading-6 text-white/55">
                      {{ playbackBlocked.container === 'mkv'
                        ? 'این نسخه با ساختار MKV است و این مرورگر آن را پخش نمی‌کند.'
                        : 'این نسخه با کُدک HEVC/x265 است و مرورگر شما آن را رمزگشایی نمی‌کند.' }}
                      کیفیت یا نسخهٔ دیگری را امتحان کن.
                    </p>
                    <div class="mt-4 grid gap-2">
                      <a
                        v-if="room.content.download_url"
                        :href="room.content.download_url"
                        target="_blank"
                        rel="noopener"
                        class="inline-flex min-h-11 items-center justify-center gap-2 rounded-xl bg-white/10 px-4 text-xs font-black text-white ring-1 ring-white/15 transition hover:bg-white/15"
                      >
                        <CinematicIcon name="download" class="size-4" />
                        دانلود مستقیم فایل
                      </a>
                      <button
                        type="button"
                        class="text-[11px] font-bold text-white/40 transition hover:text-white/80"
                        @click="playbackBlocked = null"
                      >
                        بستن و امتحان کیفیت/نسخهٔ دیگر
                      </button>
                    </div>
                  </div>
                </div>
              </Transition>
              <Transition
                enter-active-class="transition duration-150"
                enter-from-class="translate-y-1 opacity-0"
                leave-active-class="transition duration-100"
                leave-to-class="translate-y-1 opacity-0"
              >
                <div
                  v-if="playerToast"
                  :key="playerToast.id"
                  class="absolute bottom-3 left-1/2 z-20 flex max-w-[calc(100%-1.5rem)] -translate-x-1/2 items-center gap-2 rounded-xl bg-black/90 py-2 pe-2 ps-3 text-xs font-bold text-white ring-1 ring-white/15 sm:bottom-5"
                  role="status"
                >
                  <CinematicIcon :name="playerToast.icon" class="size-4 shrink-0 text-primary-300" />
                  <span class="min-w-0 truncate">{{ playerToast.message }}</span>
                  <button
                    type="button"
                    class="shrink-0 rounded-md px-1.5 py-0.5 text-[11px] text-white/50 transition hover:bg-white/10 hover:text-white"
                    aria-label="بستن پیام"
                    @click="dismissPlayerToast"
                  >
                    بستن
                  </button>
                </div>
              </Transition>
            </div>
            <div
              v-else
              class="grid aspect-video place-items-center rounded-2xl border border-white/10 bg-white/[.03] p-6 text-center"
            >
              <div>
                <CinematicIcon name="signal-off" class="mx-auto size-8 text-error" />
                <p class="mt-3 text-sm font-black">منبع پخش برای این اتاق آماده نیست</p>
                <p class="mt-1 text-xs leading-6 text-white/45">لینک پخش آنلاین را در کاتالوگ ثبت کن و اتاق را دوباره بساز.</p>
              </div>
            </div>

            <div class="mt-3 rounded-2xl border border-white/8 bg-black/35 p-3">
              <WatchPartyPresence
                :members="socket.members.value"
                :playback-state="isHost ? (hostLiveState || socket.playbackState.value) : socket.playbackState.value"
                :is-host="isHost"
                :latency-ms="socket.latencyMs.value"
              />
            </div>

            <div
              v-if="isHost && (playbackVersions.length > 1 || streamLinks.length > 1)"
              class="mt-3 space-y-3 rounded-2xl border border-white/8 bg-black/30 p-3"
            >
              <div v-if="playbackVersions.length > 1">
                <p class="mb-2 text-xs font-black text-primary-300">نسخه مشترک اتاق</p>
                <div class="hide-scrollbar flex gap-2 overflow-x-auto pb-1">
                  <button
                    v-for="version in playbackVersions"
                    :key="version.id"
                    type="button"
                    class="inline-flex min-h-11 shrink-0 items-center gap-2 rounded-xl px-3 text-xs font-black transition"
                    :class="activeVersion?.id === version.id ? 'bg-primary-500 text-night-950' : 'bg-white/5 text-white/65 ring-1 ring-white/10 hover:text-white'"
                    :aria-pressed="activeVersion?.id === version.id"
                    @click="selectVersion(version)"
                  >
                    <CinematicIcon :name="version.kind === 'dub' ? 'audio' : 'subtitle'" class="size-4" />
                    {{ version.label }}
                  </button>
                </div>
              </div>
              <div v-if="streamLinks.length > 1">
                <p class="mb-2 text-xs font-black text-primary-300">کیفیت مشترک اتاق</p>
                <div class="hide-scrollbar flex gap-2 overflow-x-auto pb-1">
                  <button
                    v-for="(link, index) in streamLinks"
                    :key="`${link.url}-${index}`"
                    type="button"
                    class="inline-flex min-h-11 shrink-0 items-center gap-2 rounded-xl px-3 text-xs font-black transition"
                    :class="playerSrc === link.url ? 'bg-primary-500 text-night-950' : 'bg-white/5 text-white/65 ring-1 ring-white/10 hover:text-white'"
                    :aria-pressed="playerSrc === link.url"
                    @click="selectStream(link)"
                  >
                    {{ link.quality || link.label || `کیفیت ${index + 1}` }}
                  </button>
                </div>
              </div>
              <p class="text-[11px] leading-5 text-white/35">تغییر نسخه یا کیفیت از همین‌جا برای همه ادامه پیدا می‌کند؛ داخل پلیر هم می‌توانی عوض کنی.</p>
            </div>

            <div
              v-if="!isHost"
              class="mt-3 flex flex-wrap items-center justify-between gap-2 rounded-xl border border-white/8 bg-black/25 px-3 py-2.5 text-xs text-white/50"
            >
              <p class="inline-flex items-center gap-1.5">
                <CinematicIcon name="lock" class="size-4 text-crimson-hover" />
                پخش با {{ room.host.display_name }} جلو می‌رود.
                <span v-if="syncTight" class="size-1.5 animate-pulse rounded-full bg-success" aria-hidden="true" />
              </p>
              <button
                type="button"
                class="party-btn party-btn--sync"
                aria-label="هماهنگ شدن دوباره با میزبان"
                @click="activateMemberPlayback"
              >
                <CinematicIcon name="resume" class="party-btn__icon" />
                <span class="party-btn__label">هم‌زمان</span>
              </button>
            </div>
          </section>

            <div
              class="party-room__panel-shell fixed inset-x-0 bottom-0 z-40 isolate max-h-[78dvh] origin-bottom lg:static lg:z-auto lg:max-h-none"
              :class="[
 panelOpen ? 'block' : 'hidden lg:block',
                focusMode && 'lg:!hidden',
              ]"
            >
              <button
                v-if="panelOpen"
                type="button"
                class="fixed inset-0 -z-10 bg-black/55 lg:hidden"
                aria-label="بستن پنل اتاق"
                @click="panelOpen = false"
              />
              <WatchPartyPanel
                id="watch-party-panel"
                class="party-room__panel rounded-t-3xl border-t border-white/10 lg:rounded-2xl lg:border"
                :room="(room as WatchRoom)"
                :members="socket.members.value"
                :messages="socket.messages.value"
                :connection-status="socket.connectionStatus.value"
                :latency-ms="socket.latencyMs.value"
                :invite-url="inviteUrl"
                :error-message="socket.socketError.value?.message"
                :action-pending="actionPending"
                v-model:active-tab="panelActiveTab"
                @send="socket.sendChat"
                @retry="socket.connect"
                @leave="leaveRoom"
                @end="endRoom"
                @close="panelOpen = false"
              />
            </div>
        </div>

        <div
          v-if="room.status === 'active' && !panelOpen"
          class="party-fab lg:hidden"
        >
          <button
            v-if="focusMode"
            type="button"
            class="party-btn party-btn--cinema party-btn--fab is-active"
            aria-label="خروج از حالت سینما"
            @click="focusMode = false"
          >
            <CinematicIcon name="eye" class="party-btn__icon" />
            <span class="party-btn__label">پنل</span>
          </button>
          <button
            type="button"
            class="party-btn party-btn--chat party-btn--fab"
            aria-controls="watch-party-panel"
            :aria-expanded="panelOpen"
            aria-label="باز کردن کنترل اتاق"
            @click="openPartyPanel('chat')"
          >
            <CinematicIcon name="comments" class="party-btn__icon" />
            <span class="party-btn__label">چت</span>
            <span v-if="socket.messages.value.length" class="party-btn__badge party-btn__badge--solid">
              {{ socket.messages.value.length.toLocaleString('fa-IR') }}
            </span>
          </button>
        </div>

        <WatchPartyMessageToasts
          :message="socket.lastChatMessage.value"
          @open-chat="openPartyChat"
        />
      </template>
    </div>
  </div>
</template>

<style scoped>
.party-room__player-frame {
  display: flex;
  width: min(100%, calc(80dvh * 16 / 9));
  justify-content: center;
  margin-inline: auto;
  background: #000;
}

.party-fullscreen-layer {
  pointer-events: none;
  position: absolute;
  inset: 0;
  z-index: 60;
}

.party-fullscreen-scrim {
  pointer-events: auto;
  position: absolute;
  inset: 0;
  border: 0;
  background: rgb(0 0 0 / 58%);
}

.party-fullscreen-chat {
  pointer-events: auto;
  position: absolute;
  inset-block: max(0.5rem, env(safe-area-inset-top, 0px)) max(0.5rem, env(safe-area-inset-bottom, 0px));
  inset-inline-end: max(0.5rem, env(safe-area-inset-right, 0px));
  display: flex;
  width: min(24rem, calc(100vw - 1rem));
  min-height: 0;
  flex-direction: column;
  overflow: hidden;
  border: 1px solid rgb(255 255 255 / 14%);
  border-radius: 1.25rem;
  background: rgb(10 10 10 / 96%);
  padding: 0.875rem;
  box-shadow: none;
}

.party-fullscreen-chat__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
  margin-bottom: 0.75rem;
  padding-bottom: 0.75rem;
  border-bottom: 1px solid rgb(255 255 255 / 8%);
}

.party-fullscreen-chat-trigger {
  pointer-events: auto;
  position: absolute;
  top: max(4rem, calc(env(safe-area-inset-top, 0px) + 3.25rem));
  inset-inline-end: max(0.75rem, env(safe-area-inset-right, 0px));
  display: inline-flex;
  min-height: 2.75rem;
  align-items: center;
  gap: 0.5rem;
  border: 1px solid rgb(255 255 255 / 16%);
  border-radius: 0.875rem;
  background: rgb(8 8 8 / 82%);
  padding-inline: 0.875rem;
  color: white;
  font-size: 0.75rem;
  font-weight: 900;
  box-shadow: none;
  transition: background-color 0.15s ease, transform 0.15s ease;
}

.party-fullscreen-chat-trigger:hover {
  background: rgb(240 180 41 / 94%);
  color: #08090a;
}

.party-fullscreen-chat-trigger:active {
  transform: scale(0.97);
}

@media (min-width: 1024px) {
  .party-room__panel-shell {
    position: sticky !important;
    top: 1rem;
    align-self: start;
  }
}

@media (max-width: 1023px) {
  .party-room__panel-shell {
    max-height: min(78dvh, calc(100dvh - max(0.5rem, env(safe-area-inset-top, 0px))));
  }
}

@media (orientation: portrait) and (max-width: 639px) {
  .party-fullscreen-chat {
    inset-block-start: auto;
    inset-inline: max(0.5rem, env(safe-area-inset-left, 0px)) max(0.5rem, env(safe-area-inset-right, 0px));
    bottom: max(0.5rem, env(safe-area-inset-bottom, 0px));
    width: auto;
    height: min(68dvh, 34rem);
    max-height: calc(100dvh - max(1rem, env(safe-area-inset-top, 0px)) - max(1rem, env(safe-area-inset-bottom, 0px)));
    border-radius: 1.35rem;
  }
}

@media (orientation: landscape) and (max-height: 500px) and (max-width: 1023px) {
  .party-room__panel-shell {
    inset: 0 0 0 auto;
    inset-inline: auto 0;
    width: min(24rem, 58vw);
    max-height: 100dvh;
    transform-origin: center left;
  }

  .party-room__panel {
    height: 100dvh;
    max-height: 100dvh;
    border: 1px solid rgb(255 255 255 / 10%);
    border-radius: 1rem 0 0 1rem;
  }

  .party-fullscreen-chat {
    width: min(22rem, 48vw);
    padding: 0.625rem;
    border-radius: 1rem;
  }

  .party-fullscreen-chat__header {
    margin-bottom: 0.5rem;
    padding-bottom: 0.5rem;
  }

  .party-fullscreen-chat-trigger {
    top: max(3.25rem, calc(env(safe-area-inset-top, 0px) + 2.75rem));
    min-height: 2.5rem;
  }
}

@media (max-width: 379px) {
  .party-fullscreen-chat {
    padding: 0.625rem;
  }

  .party-fullscreen-chat-trigger {
    padding-inline: 0.7rem;
  }
}

.party-actions {
  display: grid;
  gap: 0.5rem;
  width: 100%;
}

.party-actions--host {
  grid-template-columns: repeat(3, minmax(0, 1fr));
}

.party-actions--guest {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

@media (min-width: 640px) {
  .party-actions,
  .party-actions--host,
  .party-actions--guest {
    display: flex;
    width: auto;
    flex-wrap: wrap;
    justify-content: flex-end;
  }
}

.party-btn {
  position: relative;
  display: inline-flex;
  min-height: 2.75rem;
  align-items: center;
  justify-content: center;
  gap: 0.4rem;
  overflow: hidden;
  border-radius: 0.9rem;
  border: 1px solid transparent;
  padding-inline: 0.7rem;
  font-size: 0.75rem;
  font-weight: 900;
  letter-spacing: -0.01em;
  transition:
    transform 160ms ease,
    background-color 160ms ease,
    border-color 160ms ease,
    color 160ms ease,
    box-shadow 180ms ease,
    filter 160ms ease;
  -webkit-tap-highlight-color: transparent;
}

.party-btn::after {
  content: '';
  position: absolute;
  inset: 0;
  background: linear-gradient(135deg, rgb(255 255 255 / 14%), transparent 55%);
  opacity: 0;
  transition: opacity 160ms ease;
  pointer-events: none;
}

.party-btn:hover {
  transform: translateY(-1px);
}

.party-btn:hover::after {
  opacity: 1;
}

.party-btn:active {
  transform: translateY(0) scale(0.98);
}

.party-btn:focus-visible {
  outline: 2px solid currentColor;
  outline-offset: 2px;
}

.party-btn__icon {
  width: 0.95rem;
  height: 0.95rem;
  flex-shrink: 0;
}

.party-btn__label {
  white-space: nowrap;
}

.party-btn__badge {
  display: inline-grid;
  min-width: 1.15rem;
  place-items: center;
  border-radius: 999px;
  padding: 0.1rem 0.35rem;
  font-family: var(--font-latin, ui-monospace, monospace);
  font-size: 0.75rem;
  line-height: 1.1;
  background: rgb(255 255 255 / 12%);
}

.party-btn__badge--solid {
  background: rgb(5 5 5 / 18%);
  color: inherit;
}

/* Invite / share — sky */
.party-btn--invite {
  color: #7dd3fc;
  background: rgb(14 165 233 / 14%);
  border-color: rgb(56 189 248 / 32%);
  box-shadow: 0 0 0 0 rgb(14 165 233 / 0%);
}

.party-btn--invite:hover {
  color: #e0f2fe;
  background: rgb(14 165 233 / 28%);
  border-color: rgb(56 189 248 / 55%);
  box-shadow: none;
}

/* Cinema focus — amber */
.party-btn--cinema {
  color: #fbbf24;
  background: rgb(245 158 11 / 12%);
  border-color: rgb(251 191 36 / 28%);
}

.party-btn--cinema:hover,
.party-btn--cinema.is-active {
  color: #fff7ed;
  background: rgb(245 158 11 / 26%);
  border-color: rgb(251 191 36 / 50%);
  box-shadow: none;
}

/* Chat / panel — brand mint */
.party-btn--chat {
  color: #b0e4cc;
  background: rgb(176 228 204 / 12%);
  border-color: rgb(176 228 204 / 28%);
}

.party-btn--chat:hover {
  color: #ecfdf5;
  background: rgb(176 228 204 / 26%);
  border-color: rgb(176 228 204 / 50%);
  box-shadow: none;
}

.party-btn--chat.party-btn--fab {
  color: #07140f;
  background: #b0e4cc;
  border-color: transparent;
  box-shadow: none;
}

.party-btn--chat.party-btn--fab:hover {
  color: #04100b;
  background: #c8efdc;
  box-shadow: none;
}

/* Resync — violet */
.party-btn--sync {
  color: #c4b5fd;
  background: rgb(139 92 246 / 14%);
  border-color: rgb(167 139 250 / 30%);
  min-height: 2.5rem;
  padding-inline: 0.85rem;
}

.party-btn--sync:hover {
  color: #f5f3ff;
  background: rgb(139 92 246 / 28%);
  border-color: rgb(167 139 250 / 55%);
  box-shadow: none;
}

.party-fab {
  position: fixed;
  z-index: 30;
  bottom: max(1rem, env(safe-area-inset-bottom));
  inset-inline-start: max(0.75rem, env(safe-area-inset-left));
  display: flex;
  flex-direction: column;
  align-items: stretch;
  gap: 0.5rem;
}

.party-btn--fab {
  min-height: 3rem;
  min-width: 5.75rem;
  border-radius: 1rem;
  padding-inline: 1rem;
  font-size: 0.75rem;
  box-shadow: none;
}

.party-btn--cinema.party-btn--fab {
  background: rgb(20 14 4 / 88%);
  border-color: rgb(251 191 36 / 35%);
}

@media (max-width: 379px) {
  .party-btn {
    min-height: 2.55rem;
    padding-inline: 0.45rem;
    gap: 0.3rem;
    font-size: 0.75rem;
  }

  .party-btn__label {
    max-width: 3.4rem;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .party-btn--fab {
    min-width: 4.75rem;
    padding-inline: 0.75rem;
  }
}

@media (min-width: 640px) {
  .party-btn {
    min-width: 4.75rem;
    padding-inline: 0.9rem;
  }
}

/* Viewport-unit fallback for browsers without dvh support. */
.party-room {
  min-height: 100vh;
  min-height: 100dvh;
}
</style>
