<script setup lang="ts">
import type Hls from 'hls.js'
import type { CinematicIconName, PlaybackEpisodeOption, PlaybackQuality, PlaybackSnapshot, PlaybackTextTrack, PlaybackVersion } from '~/types'
import type { ReportProblemType } from '~/composables/useContentReport'
import { pickDefaultSubtitleTrack } from '~/utils/subtitlePolicy'
import { remuxSupported } from '~/utils/downloadMeta'
import { describeMediaUrl, reportClientDiag } from '~/utils/clientDiag'
import type { AudioPreference, EmbeddedSubtitleCue, EmbeddedSubtitleTrack, RemuxSession } from '~/utils/remux/engine'
import { findActiveCue, loadSubtitleCues, SUBTITLE_OFFSET_MAX, SUBTITLE_OFFSET_MIN, SUBTITLE_OFFSET_STEP, type SubtitleCue } from '~/utils/subtitles'

const props = withDefaults(defineProps<{
  src: string
  poster?: string
  title?: string
  autoplay?: boolean
  startAtPercent?: number
  startAtSeconds?: number
  quality?: PlaybackQuality
  sourceQuality?: string
  availableQualities?: PlaybackQuality[]
  subtitleTracks?: PlaybackTextTrack[]
  playbackVersions?: PlaybackVersion[]
  activeVersionId?: string
  episodes?: PlaybackEpisodeOption[]
  activeEpisodeId?: number
  controls?: boolean
  lowLatency?: boolean
  fill?: boolean
  locked?: boolean
  partySync?: boolean
  // 'movie' | 'series' — gates the «قسمت اشتباه» option in the report picker.
  contentType?: 'movie' | 'series' | ''
  canReport?: boolean
  // --- windowed sources ---------------------------------------------------
  // A gateway stream carries only part of the film, on its own timeline that
  // always starts at zero. These say where that window sits so the scrubber,
  // the clock and seeking all speak in film time rather than in window time.
  // They are all inert (0/false) for an ordinary whole-file source.
  /** Seconds into the film at which this media begins. */
  timelineOffset?: number
  /** The film's true runtime, when the media does not carry it. */
  timelineTotal?: number
  /** This media already begins at the playhead, so do not seek on load. */
  sourceAtPlayhead?: boolean
  /**
   * How much already-played media is still fetchable behind the playhead.
   * 0 means all of it, which is true of any ordinary file. A gateway stream
   * discards what the viewer has passed, so a rewind past this has to be
   * handled by reopening rather than by seeking.
   */
  timelineBackSeconds?: number
}>(), {
  poster: '',
  title: 'ویدیو',
  autoplay: false,
  startAtPercent: 0,
  startAtSeconds: 0,
  quality: 'auto',
  sourceQuality: '',
  availableQualities: () => [],
  subtitleTracks: () => [],
  playbackVersions: () => [],
  activeVersionId: '',
  episodes: () => [],
  activeEpisodeId: 0,
  controls: true,
  lowLatency: false,
  fill: false,
  locked: false,
  partySync: false,
  contentType: '',
  canReport: true,
  timelineOffset: 0,
  timelineTotal: 0,
  sourceAtPlayhead: false,
  timelineBackSeconds: 0,
})

const emit = defineEmits<{
  play: [progressPercent: number]
  pause: [progressPercent: number]
  progress: [progressPercent: number]
  position: [progressPercent: number]
  positionSnapshot: [snapshot: PlaybackSnapshot]
  complete: [progressPercent: number]
  ready: [durationSeconds: number]
  playbackPlay: [snapshot: PlaybackSnapshot]
  playbackPause: [snapshot: PlaybackSnapshot]
  playbackSeek: [snapshot: PlaybackSnapshot]
  bufferHealth: [aheadSeconds: number]
  qualityRequest: [quality: PlaybackQuality]
  versionRequest: [version: PlaybackVersion]
  episodeRequest: [episode: PlaybackEpisodeOption]
  sourceFailed: [payload: { src: string, code: number }]
  /** Viewer aimed outside the loaded window; the owner must reopen there. */
  seekBeyondWindow: [filmSeconds: number]
  notice: [message: string]
  fullscreenChange: [active: boolean]
  syncCorrection: [payload: { type: 'seek' | 'rate', drift: number }]
  syncFeedback: [payload: { trackId: string, offset: number, sig: string }]
  reportIssue: [payload: { problemType: ReportProblemType, detail: string }]
  /**
   * Once per source: what text subtitles the file itself carries. `probed` is
   * false when this browser plays the file without reading it (native, HLS),
   * so nothing is known about its tracks.
   */
  embeddedSubtitles: [payload: { src: string, probed: boolean, count: number, persian: boolean }]
}>()

type SettingsTab = 'episodes' | 'version' | 'quality' | 'speed' | 'subtitle'

const root = useTemplateRef<HTMLElement>('root')
const video = useTemplateRef<HTMLVideoElement>('video')
const loading = ref(true)
const errorMessage = ref('')
const isPlaying = ref(false)
const currentTime = ref(0)
const duration = ref(0)
const bufferedEnd = ref(0)
const volume = ref(1)
const isMuted = ref(false)
const playbackRate = ref(1)
const isFullscreen = ref(false)
const isPseudoFullscreen = ref(false)
const isPip = ref(false)
const pipSupported = ref(false)
const showControls = ref(true)
const showSettings = ref(false)

// --- «گزارش خطا» report picker ------------------------------------------
const showReport = ref(false)
const reportProblem = ref<ReportProblemType | ''>('')
const reportDetail = ref('')
const reportSubmitting = ref(false)
const reportDone = ref(false)

function openReport() {
  showSettings.value = false
  reportDone.value = false
  reportProblem.value = ''
  reportDetail.value = ''
  showReport.value = true
  void loadReportOptions()
}

function submitReport() {
  if (!reportProblem.value || reportSubmitting.value) return
  reportSubmitting.value = true
  emit('reportIssue', { problemType: reportProblem.value, detail: reportDetail.value.trim() })
  // Optimistic: the parent files + auto-remediates; the picker confirms instantly
  // and the page surfaces the real outcome via a toast.
  reportDone.value = true
  reportSubmitting.value = false
  window.setTimeout(() => { if (reportDone.value) showReport.value = false }, 2600)
}
const settingsTab = ref<SettingsTab>('quality')
const currentStreamQuality = ref('')
const selectedSubtitleId = ref('off')
const subtitleCues = ref<SubtitleCue[]>([])
const activeCueText = ref('')
const subtitleLoading = ref(false)
const subtitleError = ref('')
// Manual subtitle sync: positive shifts subs EARLIER (subs run late), negative
// later (subs run early). Applied as mediaTime - offset when picking the cue.
const subtitleOffset = ref(0)
// User-adjustable subtitle appearance, persisted in localStorage. Position is the
// distance from the player's bottom edge as a percentage (resolution-independent,
// so it holds in fullscreen too); scale is a font-size multiplier percentage.
const SUBTITLE_POS_MIN = 2
const SUBTITLE_POS_MAX = 45
const SUBTITLE_POS_DEFAULT = 9
const SUBTITLE_SCALE_MIN = 70
const SUBTITLE_SCALE_MAX = 170
const SUBTITLE_SCALE_DEFAULT = 100
const SUBTITLE_APPEARANCE_KEY = 'revayato:subtitle-appearance'
const subtitlePosition = ref(SUBTITLE_POS_DEFAULT)
const subtitleScale = ref(SUBTITLE_SCALE_DEFAULT)
const selectedSeason = ref(0)

let hls: Hls | null = null
// In-browser MKV→MP4 remux (see utils/remux/engine). `remuxRefusedSrc` is the
// one source it already failed on, which then plays through plain <video src>.
let remuxSession: RemuxSession | null = null
let remuxRefusedSrc = ''
let remuxStarting = false
let hlsFatalNetworkRetries = 0
let hlsMediaRecoveryDone = false
// Consecutive-failure budgets above; this one is the lifetime cap that keeps a
// stream which breaks and recovers forever from looping forever.
let hlsRecoveryTotal = 0
let sawSourceProgress = false
let startupGraceUsed = false
let nativeNetworkRetryDone = false
// Media time at which playback was first seen advancing with no picture.
let pictureMissingSince: number | null = null
let trackingReady = false
let lastProgressBucket = 0
let lastPosition = -1
let lastSnapshotSecond = -1
let resumeApplied = false
let readyEmitted = false
let applyingRemotePlayback = false
let remoteRateResetTimer: ReturnType<typeof setTimeout> | undefined
let sourceStartupTimer: ReturnType<typeof setTimeout> | undefined
let stallRecoverTimer: ReturnType<typeof setTimeout> | undefined
let hideControlsTimer: ReturnType<typeof setTimeout> | undefined
let loadToken = 0
let subtitleLoadToken = 0
let stallRecoveryAttempts = 0
/**
 * Where to resume the next media that loads, **in film time**.
 *
 * Film time and not media time, because the two only agree while one source is
 * playing, and this value exists precisely to cross from one source to the
 * next. A gateway window's own clock starts at zero no matter how far into the
 * film it sits, so carrying a raw `currentTime` across the switch is how a
 * viewer 40 minutes in lands back at minute 2. It is translated to the
 * incoming media's clock exactly once, in `setReady`.
 */
let resumeAfterSourceSeconds: number | null = null
/**
 * The playhead in film time, read while the media and the window props still
 * described the same source.
 *
 * `loadSource` cannot work this out for itself: `src` and the window props
 * change together, so by the time it runs `toFilm` already describes the
 * *incoming* media and can no longer say where the outgoing one had got to.
 * This is that reading, taken on every timeupdate.
 */
let lastFilmSeconds = 0
let resumePlaybackAfterLoad = false
let hasLoadedSource = false
let failedSourceEmitted = ''
let previousBodyOverflow = ''
// Crowd-sync feedback: debounce the settled offset and report it once per value
// per track, so a viewer's manual correction feeds the auto-sync consensus.
let subtitleSyncTimer: ReturnType<typeof setTimeout> | undefined
let lastReportedSyncOffset: number | null = null
let lastReportedSyncKey = ''

const SOURCE_STARTUP_TIMEOUT_MS = 10_000
const STALL_RECOVERY_TIMEOUT_MS = 8_000
const MAX_STALL_RECOVERY_ATTEMPTS = 3
const MAX_HLS_RECOVERIES = 12
const MEDIA_ERR_NETWORK = 2
const MEDIA_ERR_DECODE = 3
const MEDIA_ERR_SRC_NOT_SUPPORTED = 4
const rateOptions = [0.5, 0.75, 1, 1.25, 1.5, 2]

type VendorDocument = Document & {
  webkitFullscreenElement?: Element | null
  webkitExitFullscreen?: () => Promise<void>
}
type IOSVideo = HTMLVideoElement & { webkitEnterFullscreen?: () => void }

/** Fullscreen element across standard and legacy WebKit implementations. */
function activeFullscreenElement(): Element | null {
  if (typeof document === 'undefined') return null
  const doc = document as VendorDocument
  return document.fullscreenElement || doc.webkitFullscreenElement || null
}

// --- film time vs media time ------------------------------------------------
// Everything the viewer sees — clock, scrubber, buffer bar, and every subtitle
// cue — is in film time. For an ordinary whole-file source the two are the
// same, because the offset is zero and the total falls back to the media's own
// duration. For a windowed gateway stream they are not, and every crossing
// between the two goes through `toFilm`/`toMedia` below rather than adding the
// offset by hand at each call site.

/**
 * Where this media's own clock begins.
 *
 * Normally zero. A gateway session is remuxed with the source timestamps
 * intact, so whether its clock starts at zero or at the film position depends
 * on whether MSE rebases the timeline — which is not ours to decide and not
 * worth guessing. It is simply measured: if the media's first seekable instant
 * sits at the film offset, the clock is already film time and nothing needs
 * adding; if it sits at zero, the offset does. Reading it rather than assuming
 * makes the arithmetic right under either behaviour.
 */
const mediaOrigin = ref(0)

function refreshMediaOrigin() {
  const element = video.value
  if (!element || props.timelineOffset <= 1) {
    mediaOrigin.value = 0
    return
  }
  const ranges = element.seekable.length ? element.seekable : element.buffered
  if (!ranges.length) return
  // Only two answers are possible, and they are a whole offset apart, so a
  // generous tolerance cannot pick the wrong one.
  mediaOrigin.value = Math.abs(ranges.start(0) - props.timelineOffset) < 2 ? props.timelineOffset : 0
}

/** Media clock → film clock. */
function toFilm(mediaTime: number) {
  return props.timelineOffset + (mediaTime - mediaOrigin.value)
}

/** Film clock → media clock. */
function toMedia(filmTime: number) {
  return mediaOrigin.value + (filmTime - props.timelineOffset)
}

/** The film's runtime, whether or not this media covers all of it. */
const filmDuration = computed(() => (props.timelineTotal > 0 ? props.timelineTotal : duration.value))
/** The playhead's position in the film. */
const filmCurrentTime = computed(() => toFilm(currentTime.value))
const progressPercent = computed(() => filmDuration.value > 0
  ? Math.min(100, Math.max(0, filmCurrentTime.value / filmDuration.value * 100))
  : 0)
const bufferedPercent = computed(() => filmDuration.value > 0
  ? Math.min(100, Math.max(0, toFilm(bufferedEnd.value) / filmDuration.value * 100))
  : 0)
/** Where this media's window starts, as a fraction of the scrubber. */
const windowStartPercent = computed(() => filmDuration.value > 0
  ? Math.min(100, Math.max(0, props.timelineOffset / filmDuration.value * 100))
  : 0)
const cueLines = computed(() => activeCueText.value.split('\n').filter(Boolean))
const captionStyle = computed(() => ({
  '--caption-bottom': `${subtitlePosition.value}%`,
  '--caption-scale': String(subtitleScale.value / 100),
}))
// Text tracks muxed into the file itself. The remux engine reads them from the
// same bytes it streams, so they need no server and are always in sync.
const EMBEDDED_PREFIX = 'embedded-'
const embeddedTracks = ref<EmbeddedSubtitleTrack[]>([])
let embeddedSrc = ''
let embeddedCueStore = new Map<number, { cues: SubtitleCue[], seen: Set<string> }>()
// The viewer picked a subtitle (or «خاموش») by hand: never override it.
let subtitleChosenByViewer = false
const subtitleOptions = computed<PlaybackTextTrack[]>(() => [
  ...embeddedTracks.value.map(track => ({
    id: `${EMBEDDED_PREFIX}${track.number}`,
    label: track.label,
    language: track.language,
    src: '',
    provider: 'embedded',
    source_priority: 0,
  })),
  ...props.subtitleTracks,
])
const activeSubtitleTrack = computed(() => (
  selectedSubtitleId.value === 'off'
    ? null
    : subtitleOptions.value.find(track => track.id === selectedSubtitleId.value) || null
))
const fullscreenActive = computed(() => isFullscreen.value || isPseudoFullscreen.value)
const selectableVersions = computed(() => props.playbackVersions.filter(version => Boolean(version.url)))
const activeVersion = computed(() => (
  selectableVersions.value.find(version => version.id === props.activeVersionId)
  || selectableVersions.value.find(version => version.url === props.src)
  || selectableVersions.value[0]
  || null
))
const episodeOptions = computed(() => [...props.episodes].sort((left, right) => (
  left.season_number - right.season_number || left.episode_number - right.episode_number
)))
const activeEpisodeIndex = computed(() => episodeOptions.value.findIndex(episode => episode.id === props.activeEpisodeId))
const activeEpisode = computed(() => activeEpisodeIndex.value >= 0 ? episodeOptions.value[activeEpisodeIndex.value] || null : null)
const previousEpisode = computed(() => activeEpisodeIndex.value > 0 ? episodeOptions.value[activeEpisodeIndex.value - 1] || null : null)
const nextEpisode = computed(() => (
  activeEpisodeIndex.value >= 0 && activeEpisodeIndex.value < episodeOptions.value.length - 1
    ? episodeOptions.value[activeEpisodeIndex.value + 1] || null
    : null
))
const episodeSeasons = computed(() => [...new Set(episodeOptions.value.map(episode => episode.season_number))])
const visibleEpisodes = computed(() => {
  const season = selectedSeason.value || activeEpisode.value?.season_number || episodeSeasons.value[0] || 0
  return episodeOptions.value.filter(episode => episode.season_number === season)
})
// Declared after episodeOptions: useReportOptions watches (reads) it during setup.
// A series is inferred from an explicit type or from having episode options,
// so «قسمت اشتباه» only appears where an episode can actually be wrong.
const isSeriesContent = computed(() => props.contentType === 'series' || episodeOptions.value.length > 0)
// The catalogue is the server's: each button exists because one distinct repair
// stands behind it. The bundled copy paints instantly; the fetched one wins.
const { groups: reportGroups, load: loadReportOptions } = useReportOptions(
  () => (isSeriesContent.value ? 'series' : 'movie'),
  () => Boolean(props.activeEpisodeId),
)
const qualityOptions = computed<PlaybackQuality[]>(() => {
  const values = new Set<PlaybackQuality>(['auto'])
  props.availableQualities.forEach(value => values.add(value))
  if (props.quality !== 'auto') values.add(props.quality)
  hls?.levels.forEach((level) => {
    if (level.height) values.add(`${level.height}p`)
  })
  return [...values].sort((left, right) => {
    if (left === 'auto') return -1
    if (right === 'auto') return 1
    return Number.parseInt(right, 10) - Number.parseInt(left, 10)
  })
})
const qualityLabel = computed(() => {
  if (props.quality !== 'auto') return formatQuality(props.quality)
  const actual = currentStreamQuality.value || props.sourceQuality
  return actual ? `خودکار · ${formatQuality(actual)}` : 'خودکار'
})

watch(() => activeEpisode.value?.season_number, (season) => {
  if (season) selectedSeason.value = season
}, { immediate: true })

function formatTime(value: number) {
  if (!Number.isFinite(value) || value < 0) return '0:00'
  const seconds = Math.floor(value)
  const hours = Math.floor(seconds / 3600)
  const minutes = Math.floor(seconds % 3600 / 60)
  const rest = seconds % 60
  return hours > 0
    ? `${hours}:${String(minutes).padStart(2, '0')}:${String(rest).padStart(2, '0')}`
    : `${minutes}:${String(rest).padStart(2, '0')}`
}

function formatQuality(value: string) {
  const raw = String(value || '').trim()
  if (!raw || raw === 'auto') return 'خودکار'
  const height = raw.match(/(\d{3,4})/)?.[1]
  return height ? `${height}p` : raw
}

function cancelSourceStartupWatchdog() {
  if (sourceStartupTimer) clearTimeout(sourceStartupTimer)
  sourceStartupTimer = undefined
}

function cancelStallRecovery() {
  if (stallRecoverTimer) clearTimeout(stallRecoverTimer)
  stallRecoverTimer = undefined
}

function cancelControlsTimer() {
  if (hideControlsTimer) clearTimeout(hideControlsTimer)
  hideControlsTimer = undefined
}

function bumpControls(force = false) {
  showControls.value = true
  cancelControlsTimer()
  if (force || !isPlaying.value || showSettings.value) return
  hideControlsTimer = setTimeout(() => {
    if (isPlaying.value && !showSettings.value) showControls.value = false
  }, 3200)
}

function emitSourceFailure(code: number, message: string) {
  const failedSrc = String(props.src || '').trim()
  if (!failedSrc || failedSourceEmitted === failedSrc) return
  failedSourceEmitted = failedSrc
  loading.value = false
  errorMessage.value = message
  reportClientDiag('source-failed', { code, message, src: describeMediaUrl(failedSrc), mediaError: video.value?.error?.code ?? null })
  emit('sourceFailed', { src: failedSrc, code })
}

function destroyPlayer() {
  trackingReady = false
  cancelSourceStartupWatchdog()
  cancelStallRecovery()
  if (remoteRateResetTimer) clearTimeout(remoteRateResetTimer)
  remoteRateResetTimer = undefined
  hls?.destroy()
  hls = null
  remuxSession?.destroy()
  remuxSession = null
  if (video.value) {
    video.value.pause()
    video.value.removeAttribute('src')
    video.value.load()
  }
}

// Everything leaving this component speaks film time, so a windowed source is
// invisible to the page, to watch-progress and to watch-party peers — whoever
// is on a gateway stream and whoever is on the direct file agree on the clock.

function currentProgress() {
  const element = video.value
  if (!element || filmDuration.value <= 0) return 0
  return Math.round(filmCurrentTime.value / filmDuration.value * 100)
}

function getPlaybackSnapshot(): PlaybackSnapshot {
  const element = video.value
  return {
    is_playing: Boolean(element && !element.paused && !element.ended),
    position_seconds: toFilm(element?.currentTime || 0),
    duration_seconds: filmDuration.value,
    playback_rate: element?.playbackRate || 1,
  }
}

/** `seconds` is a point in the film; the media may start somewhere after 0. */
function prepareResumeAt(seconds: number) {
  if (!Number.isFinite(seconds) || seconds < 0) return
  resumeAfterSourceSeconds = seconds
  const element = video.value
  if (element && element.readyState >= 1 && Number.isFinite(element.duration)) {
    const local = Math.max(mediaOrigin.value, toMedia(seconds))
    element.currentTime = Math.min(local, Math.max(0, element.duration - 0.25))
    resumeAfterSourceSeconds = null
  }
}

function handlePlay() {
  isPlaying.value = true
  bumpControls()
  if (trackingReady) emit('play', currentProgress())
  if (trackingReady && !applyingRemotePlayback) emit('playbackPlay', getPlaybackSnapshot())
}

function handlePause() {
  isPlaying.value = false
  bumpControls(true)
  if (trackingReady && !video.value?.ended) emit('pause', currentProgress())
  if (trackingReady && !video.value?.ended && !applyingRemotePlayback) emit('playbackPause', getPlaybackSnapshot())
}

function handleSeeked() {
  if (trackingReady && !applyingRemotePlayback) emit('playbackSeek', getPlaybackSnapshot())
}

async function applyRemotePlayback(state: PlaybackSnapshot) {
  const element = video.value
  if (!element) return
  const targetRate = Math.min(4, Math.max(0.25, state.playback_rate || 1))
  // The packet is in film time; this element's clock may be offset into it.
  const remoteLocal = toMedia(state.position_seconds)
  const currentPosition = Number.isFinite(element.currentTime) ? element.currentTime : 0
  const drift = remoteLocal - currentPosition
  const seekThreshold = props.partySync && state.is_playing ? 0.6 : state.is_playing ? 1.25 : 0.12
  if (remoteRateResetTimer) clearTimeout(remoteRateResetTimer)
  remoteRateResetTimer = undefined
  applyingRemotePlayback = true
  try {
    if (Math.abs(drift) > seekThreshold) {
      element.currentTime = Math.max(mediaOrigin.value, Math.min(remoteLocal, element.duration || remoteLocal))
      element.playbackRate = targetRate
      emit('syncCorrection', { type: 'seek', drift })
    } else if (state.is_playing && Math.abs(drift) > 0.1 && !element.paused) {
      const correction = Math.min(0.08, Math.abs(drift) * 0.15) * Math.sign(drift)
      element.playbackRate = Math.min(4, Math.max(0.25, targetRate + correction))
      emit('syncCorrection', { type: 'rate', drift })
      remoteRateResetTimer = setTimeout(() => {
        if (video.value === element && !applyingRemotePlayback) element.playbackRate = targetRate
      }, 6000)
    } else {
      element.playbackRate = targetRate
    }
    playbackRate.value = targetRate
    if (state.is_playing && element.paused) await element.play()
    else if (!state.is_playing && !element.paused) element.pause()
  } catch {
    // Autoplay restrictions are retried by the next party sync packet.
  } finally {
    window.setTimeout(() => { applyingRemotePlayback = false }, 120)
  }
}

defineExpose({ applyRemotePlayback, getPlaybackSnapshot, prepareResumeAt })

/**
 * `time` is a point in the *film*, never the media clock — a subtitle file is
 * written against the film, so a windowed stream whose own clock starts at the
 * session boundary would otherwise look its cues up a whole session-offset out.
 */
function updateCue(time = filmCurrentTime.value) {
  if (selectedSubtitleId.value === 'off') {
    activeCueText.value = ''
    return
  }
  const offset = subtitleOffset.value || 0
  activeCueText.value = findActiveCue(subtitleCues.value, time - offset)?.text || ''
}

function nudgeSubtitleOffset(delta: number) {
  if (selectedSubtitleId.value === 'off' || !subtitleCues.value.length) return
  subtitleOffset.value = Math.min(
    SUBTITLE_OFFSET_MAX,
    Math.max(SUBTITLE_OFFSET_MIN, Math.round((subtitleOffset.value + delta) * 100) / 100),
  )
  updateCue()
  scheduleSubtitleSyncReport()
}

function resetSubtitleOffset() {
  subtitleOffset.value = 0
  updateCue()
  scheduleSubtitleSyncReport()
}

/**
 * Report the timing offset a viewer settled on so the backend can converge a
 * crowd consensus and bake it into the file. Debounced (fires once the viewer
 * stops adjusting) and de-duplicated per track+value; only tracks that carry a
 * file signature are reportable.
 */
function scheduleSubtitleSyncReport(delayMs = 2500) {
  if (subtitleSyncTimer) clearTimeout(subtitleSyncTimer)
  subtitleSyncTimer = setTimeout(reportSubtitleSyncFeedback, delayMs)
}

function reportSubtitleSyncFeedback() {
  if (subtitleSyncTimer) {
    clearTimeout(subtitleSyncTimer)
    subtitleSyncTimer = undefined
  }
  const track = activeSubtitleTrack.value
  const sig = track?.sync_sig
  if (!track || !sig) return
  const offset = Math.round((subtitleOffset.value || 0) * 100) / 100
  const key = `${track.id}:${sig}`
  // Skip repeats of the same settled value for the same file version.
  if (key === lastReportedSyncKey && offset === lastReportedSyncOffset) return
  lastReportedSyncKey = key
  lastReportedSyncOffset = offset
  emit('syncFeedback', { trackId: track.id, offset, sig })
}

function clampNumber(value: number, min: number, max: number) {
  return Math.min(max, Math.max(min, value))
}

/** Restore the viewer's saved subtitle position/size (client-only). */
function loadSubtitleAppearance() {
  try {
    const raw = localStorage.getItem(SUBTITLE_APPEARANCE_KEY)
    if (!raw) return
    const parsed = JSON.parse(raw) as { position?: unknown, scale?: unknown }
    if (typeof parsed.position === 'number') {
      subtitlePosition.value = clampNumber(Math.round(parsed.position), SUBTITLE_POS_MIN, SUBTITLE_POS_MAX)
    }
    if (typeof parsed.scale === 'number') {
      subtitleScale.value = clampNumber(Math.round(parsed.scale), SUBTITLE_SCALE_MIN, SUBTITLE_SCALE_MAX)
    }
  } catch {
    /* ignore malformed or unavailable storage */
  }
}

function persistSubtitleAppearance() {
  try {
    localStorage.setItem(SUBTITLE_APPEARANCE_KEY, JSON.stringify({
      position: subtitlePosition.value,
      scale: subtitleScale.value,
    }))
  } catch {
    /* storage may be unavailable (private mode) */
  }
}

function resetSubtitleAppearance() {
  subtitlePosition.value = SUBTITLE_POS_DEFAULT
  subtitleScale.value = SUBTITLE_SCALE_DEFAULT
}

function syncBuffer() {
  const element = video.value
  if (!element?.buffered.length) return
  const end = element.buffered.end(element.buffered.length - 1)
  // Something of this source has landed. A slow link is not a dead link, and
  // the startup watchdog reads this before retiring anything.
  if (end > 0) sawSourceProgress = true
  bufferedEnd.value = Math.max(0, end)
  emit('bufferHealth', Math.max(0, end - element.currentTime))
}

function handleTimeUpdate() {
  const element = video.value
  if (!element) return
  refreshMediaOrigin()
  currentTime.value = element.currentTime || 0
  duration.value = Number.isFinite(element.duration) ? element.duration : 0
  lastFilmSeconds = toFilm(element.currentTime)
  updateCue(lastFilmSeconds)
  syncBuffer()
  watchForMissingPicture(element)
  if (!trackingReady) return
  const progress = currentProgress()
  if (progress !== lastPosition) {
    lastPosition = progress
    emit('position', progress)
  }
  const snapshotSecond = Math.floor(element.currentTime / 10) * 10
  if (snapshotSecond >= 10 && snapshotSecond !== lastSnapshotSecond) {
    lastSnapshotSecond = snapshotSecond
    emit('positionSnapshot', getPlaybackSnapshot())
  }
  const bucket = Math.floor(progress / 10) * 10
  if (bucket >= 10 && bucket > lastProgressBucket && bucket < 100) {
    lastProgressBucket = bucket
    emit('progress', progress)
  }
}

/**
 * A video track the browser cannot decode (HEVC in MKV on Chrome, 10-bit HEVC
 * on an 8-bit decoder) raises no error: the sound plays over a black frame
 * forever. Seconds of advancing playback with a zero-size picture are the only
 * sign of it, and a decode failure is what lets the page move to another file.
 */
function watchForMissingPicture(element: HTMLVideoElement) {
  if (element.paused || element.seeking || element.readyState < 2 || element.videoWidth > 0) {
    pictureMissingSince = null
    return
  }
  const now = element.currentTime || 0
  if (pictureMissingSince === null || now < pictureMissingSince) {
    pictureMissingSince = now
    return
  }
  if (now - pictureMissingSince < 4) return
  pictureMissingSince = null
  emitSourceFailure(MEDIA_ERR_DECODE, 'تصویر این فایل در این مرورگر نمایش داده نمی‌شود؛ نسخهٔ دیگری امتحان می‌شود.')
}

function handleEnded() {
  isPlaying.value = false
  bumpControls(true)
  if (trackingReady) emit('complete', 100)
}

async function safePlay(shouldPlay = resumePlaybackAfterLoad || props.autoplay) {
  if (!shouldPlay || !video.value) return
  try { await video.value.play() } catch { /* Browser gesture policy keeps custom controls available. */ }
}

function setReady() {
  const element = video.value
  if (!element) return
  duration.value = Number.isFinite(element.duration) ? element.duration : 0
  // Before anything below seeks: the resume points are in film time, and
  // translating them needs to know where this media's own clock starts.
  refreshMediaOrigin()
  if (props.sourceAtPlayhead) {
    // The stream was opened at the playhead, so second zero of this media
    // already *is* where the viewer was. Any seek here would skip twice.
    resumeAfterSourceSeconds = null
    resumeApplied = true
  } else if (resumeAfterSourceSeconds != null && duration.value > 0) {
    // The only crossing from film time back to this media's clock.
    const local = Math.max(mediaOrigin.value, toMedia(resumeAfterSourceSeconds))
    element.currentTime = Math.min(local, Math.max(0, duration.value - 0.25))
    resumeAfterSourceSeconds = null
    resumeApplied = true
  } else if (!resumeApplied && props.startAtSeconds > 0 && duration.value > 0) {
    const resumeSeconds = Math.min(props.startAtSeconds, Math.max(0, duration.value - 2))
    element.currentTime = resumeSeconds
    resumeApplied = true
    lastPosition = Math.round(resumeSeconds / duration.value * 100)
  } else if (!resumeApplied && props.startAtPercent > 0 && duration.value > 0) {
    const resumePercent = Math.min(95, Math.max(0, props.startAtPercent))
    element.currentTime = duration.value * resumePercent / 100
    resumeApplied = true
    lastPosition = Math.round(resumePercent)
  }
  loading.value = false
  cancelSourceStartupWatchdog()
  cancelStallRecovery()
  stallRecoveryAttempts = 0
  trackingReady = true
  hasLoadedSource = true
  if (!readyEmitted && duration.value > 0) {
    readyEmitted = true
    emit('ready', filmDuration.value || duration.value)
  }
  const shouldPlay = resumePlaybackAfterLoad || props.autoplay
  resumePlaybackAfterLoad = false
  void safePlay(shouldPlay)
}

function handlePlaying() {
  loading.value = false
  errorMessage.value = ''
  cancelSourceStartupWatchdog()
  cancelStallRecovery()
  stallRecoveryAttempts = 0
}

function handleNativeError() {
  if (!video.value?.getAttribute('src') && !hls) return
  const code = video.value?.error?.code || MEDIA_ERR_SRC_NOT_SUPPORTED
  const element = video.value
  // The engine sees the same error and settles startup itself.
  if (remuxStarting) return
  if (remuxSession) {
    abandonRemux('media_error_' + code)
    return
  }
  // A file that played for twenty minutes and then lost the connection has
  // proved it is the right file on a reachable host. Reporting that as a
  // source failure retires it — and, because code 2 is read as an origin
  // fault, every mirror on the same CDN with it. Reopen it once at the
  // playhead first; only a second failure is a real verdict about the source.
  // Windowed sources (a gateway session) are excluded: their media clock is
  // not the film's, so a reload would land somewhere else entirely.
  if (
    code === MEDIA_ERR_NETWORK
    && !nativeNetworkRetryDone
    && !hls
    && !isHlsSource(String(props.src || ''))
    && !props.sourceAtPlayhead
    && hasLoadedSource
    && element
    && element.currentTime > 1
  ) {
    nativeNetworkRetryDone = true
    resumeAfterSourceSeconds = toFilm(element.currentTime)
    resumeApplied = false
    resumePlaybackAfterLoad = true
    emit('notice', 'اتصال قطع شد؛ در حال ادامه از همان لحظه')
    element.load()
    beginLoading()
    return
  }
  const message = code === MEDIA_ERR_NETWORK
    ? 'ارتباط با منبع ویدیو برقرار نشد.'
    : code === MEDIA_ERR_DECODE
      ? 'کُدک این فایل (احتمالاً HEVC/x265) در این مرورگر پشتیبانی نمی‌شود.'
      : 'فرمت یا آدرس این فایل برای پخش آنلاین پشتیبانی نمی‌شود.'
  emitSourceFailure(code, message)
}

function armSourceStartupWatchdog(token: number) {
  cancelSourceStartupWatchdog()
  sourceStartupTimer = setTimeout(() => {
    const current = video.value
    if (token !== loadToken || !current || current.readyState >= HTMLMediaElement.HAVE_CURRENT_DATA) return
    // Ten seconds is a deadline for a source that never answers, not for one
    // that is answering slowly. On a thin connection a large file — or a
    // gateway stream still being written — can take longer than that to reach
    // its first decodable frame, and retiring it there costs the viewer the
    // one source that was actually going to work. Bytes on the wire buy one
    // more window; silence still fails on time.
    if (sawSourceProgress && !startupGraceUsed) {
      startupGraceUsed = true
      emit('notice', 'اتصال کند است؛ کمی بیشتر صبر می‌کنیم')
      armSourceStartupWatchdog(token)
      return
    }
    emit('notice', 'این منبع شروع نشد؛ در حال امتحان لینک بعدی')
    emitSourceFailure(MEDIA_ERR_NETWORK, 'این منبع در زمان مناسب شروع نشد.')
  }, SOURCE_STARTUP_TIMEOUT_MS)
}

function beginLoading() {
  loading.value = true
  if (stallRecoverTimer) return
  const failedSrc = String(props.src || '').trim()
  const token = loadToken
  stallRecoverTimer = setTimeout(() => {
    stallRecoverTimer = undefined
    const current = video.value
    if (token !== loadToken || !current || props.src !== failedSrc) return
    if (!current.paused && current.readyState >= HTMLMediaElement.HAVE_FUTURE_DATA) {
      handlePlaying()
      return
    }
    stallRecoveryAttempts += 1
    const nowSeconds = Number.isFinite(current.currentTime) ? current.currentTime : 0
    if (stallRecoveryAttempts === 1) {
      try { current.currentTime = Math.max(0, nowSeconds + 0.01) } catch { /* retry below */ }
      void current.play().catch(() => {})
      beginLoading()
      return
    }
    if (stallRecoveryAttempts === 2 && remuxSession) {
      abandonRemux('stalled')
      return
    }
    if (stallRecoveryAttempts === 2 && !isHlsSource(failedSrc)) {
      resumeAfterSourceSeconds = toFilm(nowSeconds)
      current.load()
      beginLoading()
      return
    }
    if (stallRecoveryAttempts >= MAX_STALL_RECOVERY_ATTEMPTS) {
      emit('sourceFailed', { src: failedSrc, code: MEDIA_ERR_NETWORK })
      failedSourceEmitted = failedSrc
      errorMessage.value = 'این منبع متوقف شد؛ منبع جایگزین پیدا نشد.'
      loading.value = false
      return
    }
    beginLoading()
  }, STALL_RECOVERY_TIMEOUT_MS)
}

function isHlsSource(src: string) {
  try {
    return /\.m3u8$/i.test(new URL(src, window.location.href).pathname)
  } catch {
    return /\.m3u8(?:$|[?#])/i.test(src)
  }
}

function applyQuality() {
  if (!hls) return
  if (props.quality === 'auto') {
    hls.currentLevel = -1
    return
  }
  const targetHeight = Number.parseInt(props.quality, 10)
  let closestIndex = -1
  let closestDistance = Number.POSITIVE_INFINITY
  hls.levels.forEach((level, index) => {
    if (!level.height) return
    const distance = Math.abs(level.height - targetHeight)
    if (distance < closestDistance) {
      closestDistance = distance
      closestIndex = index
    }
  })
  hls.currentLevel = closestIndex
}

function remuxAudioPreference(): AudioPreference {
  const kind = activeVersion.value?.kind
  if (kind === 'dub') return 'fa'
  if (kind === 'softsub' || kind === 'hardsub' || kind === 'original') return 'original'
  return ''
}

/**
 * MKV is what most of the catalogue is, and no iOS browser, desktop Safari or
 * Firefox can open it. Remuxing it here, in the page, to fragmented MP4 plays
 * the very same bytes from the very same CDN in all of them — and lets us pick
 * the Persian audio track of a dubbed file, which Chrome's native MKV player
 * ignores. Resolves false when this file or browser cannot be remuxed, and the
 * caller carries on with plain `<video src>`.
 */
async function startRemux(token: number, element: HTMLVideoElement): Promise<boolean> {
  const src = String(props.src || '').trim()
  // Decide before pulling the engine chunk in: with the remuxer switched off
  // (downloadMeta REMUX_ENABLED) the page never loads or runs it.
  if (!remuxSupported()) {
    reportEmbeddedProbe(src, [], false)
    return false
  }
  let engine: typeof import('~/utils/remux/engine')
  try {
    engine = await import('~/utils/remux/engine')
  }
  catch {
    reportEmbeddedProbe(src, [], false)
    return false
  }
  const { isRemuxCandidate, startMkvRemux } = engine
  if (token !== loadToken) return false
  if (!isRemuxCandidate(src) || !remuxSupported()) {
    reportEmbeddedProbe(src, [], false)
    return false
  }
  const startTime = resumeAfterSourceSeconds ?? (props.startAtSeconds > 0 ? props.startAtSeconds : 0)
  remuxStarting = true
  try {
    const session = await startMkvRemux(element, src, {
      startTime,
      audioPreference: remuxAudioPreference(),
      onFatal: (error) => {
        if (remuxSession !== session) return
        abandonRemux(error.code)
      },
      onLog: import.meta.dev ? message => console.info(message) : undefined,
      onSubtitleTracks: (tracks) => {
        if (token === loadToken) reportEmbeddedProbe(src, tracks, true)
      },
      onSubtitleCues: (trackNumber, cues) => addEmbeddedCues(src, trackNumber, cues),
    })
    if (token !== loadToken || element !== video.value) {
      session.destroy()
      return true
    }
    remuxSession = session
    sawSourceProgress = true
    return true
  }
  catch (error) {
    const code = (error as { code?: string } | null)?.code || 'failed'
    if (token !== loadToken || code === 'destroyed') return true
    if (import.meta.dev) console.info(`[remux] not used: ${code}`)
    // Dead link: the native element would only spend its own timeout finding
    // that out. Anything else (codec, CORS, parse) is ours — let it try.
    if (code === 'expired' || code === 'http_error') {
      emitSourceFailure(MEDIA_ERR_NETWORK, 'ارتباط با منبع ویدیو برقرار نشد.')
      return true
    }
    remuxRefusedSrc = src
    reportEmbeddedProbe(src, [], false)
    element.removeAttribute('src')
    element.load()
    return false
  }
  finally {
    remuxStarting = false
  }
}

/** Remux broke mid-film: carry on natively from the same moment. */
function abandonRemux(reason: string) {
  if (import.meta.dev) console.info(`[remux] abandoned: ${reason}`)
  remuxRefusedSrc = String(props.src || '').trim()
  if (lastFilmSeconds > 1) resumeAfterSourceSeconds = lastFilmSeconds
  void loadSource()
}

async function loadSource() {
  const token = ++loadToken
  const previous = video.value
  resumePlaybackAfterLoad = hasLoadedSource
    ? Boolean(previous && !previous.paused && !previous.ended)
    : props.autoplay
  // A windowed source opened at the playhead carries no position over: the new
  // media starts exactly where the old one stopped, on its own zero-based clock.
  if (props.sourceAtPlayhead) resumeAfterSourceSeconds = null
  else if (resumeAfterSourceSeconds == null && hasLoadedSource && lastFilmSeconds > 1) {
    // `previous.currentTime` would be the outgoing media's own clock, which is
    // the film's only when that media began at zero. Falling back from a
    // gateway window to a direct mirror is exactly when it does not.
    resumeAfterSourceSeconds = lastFilmSeconds
  }
  destroyPlayer()
  lastProgressBucket = 0
  lastPosition = -1
  resumeApplied = false
  readyEmitted = false
  errorMessage.value = ''
  loading.value = true
  failedSourceEmitted = ''
  stallRecoveryAttempts = 0
  hlsFatalNetworkRetries = 0
  hlsMediaRecoveryDone = false
  hlsRecoveryTotal = 0
  sawSourceProgress = false
  startupGraceUsed = false
  nativeNetworkRetryDone = false
  pictureMissingSince = null
  // Measured per media, never inherited: `refreshMediaOrigin` keeps its last
  // answer when there is nothing to measure yet, and that answer belonged to
  // the source being replaced. Zero is right for every whole-file source and
  // is corrected within the first frames of a windowed one.
  mediaOrigin.value = 0
  currentStreamQuality.value = ''
  const element = video.value
  if (!element || !props.src) {
    errorMessage.value = 'آدرس پخش در دسترس نیست.'
    loading.value = false
    return
  }
  // A new file brings its own tracks; the same file (native fallback after a
  // remux) keeps the cues already read from it.
  if (embeddedSrc && embeddedSrc !== String(props.src).trim()) clearEmbeddedSubtitles()

  if (!isHlsSource(props.src)) {
    if (props.src !== remuxRefusedSrc && await startRemux(token, element)) return
    if (token !== loadToken || element !== video.value) return
    reportEmbeddedProbe(String(props.src).trim(), [], false)
    element.src = props.src
    element.load()
    armSourceStartupWatchdog(token)
    return
  }

  reportEmbeddedProbe(String(props.src).trim(), [], false)
  // Native HLS first (Safari, iOS, some WebViews); both MIME variants for wider detection.
  if (element.canPlayType('application/vnd.apple.mpegurl') || element.canPlayType('application/x-mpegurl')) {
    element.src = props.src
    element.load()
    armSourceStartupWatchdog(token)
    return
  }

  const { default: HlsClass } = await import('hls.js')
  if (token !== loadToken || element !== video.value) return

  if (HlsClass.isSupported()) {
    hls = new HlsClass({
      enableWorker: true,
      lowLatencyMode: props.lowLatency,
      capLevelToPlayerSize: true,
      backBufferLength: props.lowLatency ? 10 : 30,
      maxBufferLength: props.lowLatency ? 12 : 36,
      maxMaxBufferLength: props.lowLatency ? 24 : 72,
      startFragPrefetch: true,
    })
    hls.loadSource(props.src)
    hls.attachMedia(element)
    const instance = hls
    instance.on(HlsClass.Events.MANIFEST_PARSED, () => {
      if (hls !== instance) return
      applyQuality()
      armSourceStartupWatchdog(token)
      void safePlay()
    })
    instance.on(HlsClass.Events.FRAG_BUFFERED, () => {
      if (hls !== instance) return
      // A fragment landed, so whatever broke before is over. The budgets below
      // are meant to stop a source that cannot recover — not to add up three
      // unrelated blips over a two-hour film into a dead stream. Only
      // hlsRecoveryTotal keeps counting, and it is what ends a genuine loop.
      sawSourceProgress = true
      hlsFatalNetworkRetries = 0
      hlsMediaRecoveryDone = false
    })
    instance.on(HlsClass.Events.LEVEL_SWITCHED, (_, data) => {
      if (hls !== instance) return
      const height = instance.levels[data.level]?.height
      currentStreamQuality.value = height ? `${height}p` : ''
    })
    instance.on(HlsClass.Events.ERROR, (_, data) => {
      if (!data.fatal || token !== loadToken || hls !== instance) return
      if (data.type === HlsClass.ErrorTypes.NETWORK_ERROR) {
        // Transient network drops: resume loading before giving up on the source.
        if (hlsFatalNetworkRetries < 2 && hlsRecoveryTotal < MAX_HLS_RECOVERIES) {
          hlsFatalNetworkRetries += 1
          hlsRecoveryTotal += 1
          emit('notice', 'اتصال قطع شد؛ در حال تلاش دوباره')
          instance.startLoad()
          return
        }
        emitSourceFailure(MEDIA_ERR_NETWORK, 'ارتباط با جریان ویدیو برقرار نشد.')
      } else if (data.type === HlsClass.ErrorTypes.MEDIA_ERROR) {
        // Decoder hiccups are usually recoverable once per stretch of playback.
        if (!hlsMediaRecoveryDone && hlsRecoveryTotal < MAX_HLS_RECOVERIES) {
          hlsMediaRecoveryDone = true
          hlsRecoveryTotal += 1
          instance.recoverMediaError()
          return
        }
        emitSourceFailure(MEDIA_ERR_DECODE, 'مرورگر نتوانست این ویدیو را رمزگشایی کند.')
      } else {
        emitSourceFailure(MEDIA_ERR_SRC_NOT_SUPPORTED, 'خطایی در آماده‌سازی پخش رخ داد.')
      }
      instance.destroy()
      if (hls === instance) hls = null
    })
    armSourceStartupWatchdog(token)
    return
  }

  emitSourceFailure(MEDIA_ERR_SRC_NOT_SUPPORTED, 'پخش HLS در این مرورگر پشتیبانی نمی‌شود.')
}

function chooseSubtitle(trackId: string) {
  subtitleChosenByViewer = true
  void selectSubtitle(trackId)
}

async function selectSubtitle(trackId: string) {
  selectedSubtitleId.value = trackId
  subtitleLoadToken += 1
  const token = subtitleLoadToken
  subtitleCues.value = []
  activeCueText.value = ''
  subtitleError.value = ''
  subtitleOffset.value = 0
  subtitleLoading.value = false
  if (trackId === 'off') return
  if (trackId.startsWith(EMBEDDED_PREFIX)) {
    // Cues arrive as the stream reaches them; addEmbeddedCues keeps this fed.
    subtitleCues.value = embeddedCueStore.get(Number(trackId.slice(EMBEDDED_PREFIX.length)))?.cues.slice() || []
    updateCue()
    return
  }
  const track = props.subtitleTracks.find(candidate => candidate.id === trackId)
  if (!track?.src) return
  subtitleLoading.value = true
  try {
    const cues = await loadSubtitleCues(track.src)
    if (token !== subtitleLoadToken) return
    subtitleCues.value = cues
    updateCue()
    if (!cues.length) subtitleError.value = 'متن قابل نمایش در این زیرنویس پیدا نشد.'
  } catch {
    if (token === subtitleLoadToken) subtitleError.value = 'بارگذاری زیرنویس انجام نشد.'
  } finally {
    if (token === subtitleLoadToken) subtitleLoading.value = false
  }
}

function syncSubtitleTracks() {
  const current = selectedSubtitleId.value
  // The file's own track stays on while it exists; a sidecar landing later
  // (ensure flow) is offered in the menu, not forced over it.
  if (current.startsWith(EMBEDDED_PREFIX) && subtitleOptions.value.some(track => track.id === current)) return
  const currentStillExists = props.subtitleTracks.some(track => track.id === current && track.src)
  const preferred = pickDefaultSubtitleTrack(props.subtitleTracks)
  const embedded = subtitleChosenByViewer ? '' : embeddedPersianOptionId()
  const next = currentStillExists ? current : preferred?.id || embedded || 'off'
  void selectSubtitle(next)
}

function embeddedPersianOptionId(): string {
  if (activeVersion.value?.kind === 'dub') return ''
  const persian = embeddedTracks.value.find(track => track.persian && !track.forced)
    || embeddedTracks.value.find(track => track.persian)
  return persian ? `${EMBEDDED_PREFIX}${persian.number}` : ''
}

function clearEmbeddedSubtitles() {
  embeddedSrc = ''
  embeddedCueStore = new Map()
  if (!embeddedTracks.value.length) return
  embeddedTracks.value = []
  if (selectedSubtitleId.value.startsWith(EMBEDDED_PREFIX)) syncSubtitleTracks()
}

/** Tell the page what this source carries — once per source. */
function reportEmbeddedProbe(src: string, tracks: EmbeddedSubtitleTrack[], probed: boolean) {
  if (embeddedSrc === src) return
  embeddedSrc = src
  embeddedCueStore = new Map()
  embeddedTracks.value = tracks
  emit('embeddedSubtitles', {
    src,
    probed,
    count: tracks.length,
    persian: tracks.some(track => track.persian),
  })
  if (!tracks.length) return
  // The file's own Persian track is timed to this exact encode, so it beats a
  // provider sidecar matched by title — but never what the viewer picked, and
  // never a sidecar cut from this same file (source_priority 1).
  const embeddedId = embeddedPersianOptionId()
  if (!embeddedId || subtitleChosenByViewer) return
  const current = activeSubtitleTrack.value
  if (current && (current.source_priority || 99) <= 1) return
  void selectSubtitle(embeddedId)
}

function addEmbeddedCues(src: string, trackNumber: number, cues: EmbeddedSubtitleCue[]) {
  if (src !== embeddedSrc) return
  let store = embeddedCueStore.get(trackNumber)
  if (!store) embeddedCueStore.set(trackNumber, store = { cues: [], seen: new Set() })
  let added = false
  let ordered = true
  for (const cue of cues) {
    // A seek re-streams stretches already read: keep each cue once.
    const key = `${Math.round(cue.start * 1000)}|${cue.text}`
    if (store.seen.has(key)) continue
    store.seen.add(key)
    const last = store.cues[store.cues.length - 1]
    if (last && cue.start < last.start) ordered = false
    store.cues.push({ start: cue.start, end: cue.end, text: cue.text })
    added = true
  }
  if (!added) return
  if (!ordered) store.cues.sort((left, right) => left.start - right.start)
  if (selectedSubtitleId.value === `${EMBEDDED_PREFIX}${trackNumber}`) {
    subtitleCues.value = store.cues.slice()
    updateCue()
  }
}

async function togglePlayback() {
  if (props.locked) {
    emit('notice', 'کنترل پخش در اختیار میزبان است')
    return
  }
  const element = video.value
  if (!element) return
  if (element.paused || element.ended) {
    try { await element.play() } catch { /* error overlay handles source failures */ }
  } else {
    element.pause()
  }
}

/** Is this media-time already decoded in the browser? Then a seek costs nothing. */
function isLocallyBuffered(element: HTMLMediaElement, local: number) {
  const ranges = element.buffered
  for (let index = 0; index < ranges.length; index += 1) {
    if (local >= ranges.start(index) - 0.25 && local <= ranges.end(index)) return true
  }
  return false
}

/**
 * Move the playhead to a point in the *film*.
 *
 * Inside the loaded window this is an ordinary seek. Outside it — only possible
 * for a windowed source — the media simply does not contain that moment, so the
 * owner is asked to reopen the stream there.
 */
function seekToFilmSeconds(target: number) {
  const element = video.value
  if (!element) return
  const bounded = Math.max(0, Math.min(target, filmDuration.value || target))
  const local = toMedia(bounded)
  const mediaEnd = duration.value > mediaOrigin.value ? duration.value : mediaOrigin.value + duration.value
  const hasWindow = props.timelineOffset > 0 || (props.timelineTotal > 0 && props.timelineTotal > duration.value + 1)
  // A second of slack at each edge: landing exactly on the boundary would
  // reopen a stream the viewer is already watching.
  if (hasWindow && (local < mediaOrigin.value - 1 || local > mediaEnd + 1)) {
    emit('seekBeyondWindow', bounded)
    return
  }
  // Behind the playhead a windowed source keeps only a short tail, pruned as
  // far back as the furthest point already fetched. A rewind past that still
  // works for as long as the browser holds the frames itself — only once both
  // are gone does the moment have to be fetched again, which means reopening.
  if (props.timelineBackSeconds > 0) {
    const fetchedTo = Math.max(element.currentTime, bufferedEnd.value)
    if (local < fetchedTo - props.timelineBackSeconds && !isLocallyBuffered(element, local)) {
      emit('seekBeyondWindow', bounded)
      return
    }
  }
  if (!Number.isFinite(element.duration) || element.duration <= 0) return
  element.currentTime = Math.min(element.duration, Math.max(mediaOrigin.value, local))
  currentTime.value = element.currentTime
  lastFilmSeconds = toFilm(element.currentTime)
  updateCue(lastFilmSeconds)
}

function seekToPercent(percent: number) {
  if (props.locked) {
    emit('notice', 'جابه‌جایی زمان با میزبان هماهنگ می‌شود')
    return
  }
  if (filmDuration.value <= 0) return
  seekToFilmSeconds(filmDuration.value * percent / 100)
}

function handleProgressInput(event: Event) {
  seekToPercent(Number((event.target as HTMLInputElement).value))
}

function skip(seconds: number) {
  if (props.locked) {
    emit('notice', 'کنترل زمان در اختیار میزبان است')
    return
  }
  const element = video.value
  if (!element) return
  seekToFilmSeconds(toFilm(element.currentTime) + seconds)
}

function setVolume(value: number) {
  const element = video.value
  if (!element) return
  element.volume = Math.min(1, Math.max(0, value))
  element.muted = element.volume === 0
  volume.value = element.volume
  isMuted.value = element.muted
}

function handleVolumeInput(event: Event) {
  setVolume(Number((event.target as HTMLInputElement).value))
}

function toggleMute() {
  const element = video.value
  if (!element) return
  element.muted = !element.muted
  isMuted.value = element.muted
}

function setRate(rate: number) {
  if (props.locked) {
    emit('notice', 'سرعت پخش با میزبان هماهنگ می‌شود')
    return
  }
  if (!video.value) return
  video.value.playbackRate = rate
  playbackRate.value = rate
  showSettings.value = false
}

function requestQuality(quality: PlaybackQuality) {
  if (props.locked) {
    emit('notice', 'کیفیت مشترک را میزبان انتخاب می‌کند')
    return
  }
  emit('qualityRequest', quality)
  showSettings.value = false
}

function requestVersion(version: PlaybackVersion) {
  if (props.locked || version.url === props.src) return
  emit('versionRequest', version)
  showSettings.value = false
}

function requestEpisode(episode: PlaybackEpisodeOption | null) {
  if (!episode || props.locked || episode.id === props.activeEpisodeId) return
  emit('episodeRequest', episode)
  showSettings.value = false
}

function openSettings(tab: SettingsTab) {
  settingsTab.value = tab
  showSettings.value = true
  bumpControls(true)
}

/** Best-effort landscape lock while fullscreen on phones; silently ignored where unsupported. */
function lockLandscapeWhileFullscreen() {
  const orientation = screen.orientation as ScreenOrientation & { lock?: (orientation: 'landscape' | string) => Promise<void> }
  if (orientation?.lock && window.matchMedia('(hover: none) and (max-width: 767px)').matches) {
    orientation.lock('landscape').catch(() => { /* iOS and desktop ignore this */ })
  }
}

async function toggleFullscreen() {
  const element = root.value
  if (!element) return
  try {
    const active = activeFullscreenElement()
    if (active) {
      if (document.exitFullscreen) await document.exitFullscreen()
      else await (document as VendorDocument).webkitExitFullscreen?.()
      return
    }
    if (element.requestFullscreen) {
      await element.requestFullscreen({ navigationUI: 'hide' })
      lockLandscapeWhileFullscreen()
      return
    }
    // iPhone Safari only allows the video element itself to go fullscreen.
    const videoEl = video.value as IOSVideo | null
    if (videoEl?.webkitEnterFullscreen) {
      videoEl.webkitEnterFullscreen()
      return
    }
    throw new Error('Fullscreen API unavailable')
  } catch {
    isPseudoFullscreen.value = !isPseudoFullscreen.value
    if (isPseudoFullscreen.value) {
      previousBodyOverflow = document.body.style.overflow
      document.body.style.overflow = 'hidden'
    } else {
      document.body.style.overflow = previousBodyOverflow
    }
    emit('fullscreenChange', isPseudoFullscreen.value)
  }
}

async function togglePip() {
  const element = video.value
  if (!element || !pipSupported.value) return
  try {
    if (document.pictureInPictureElement) await document.exitPictureInPicture()
    else await element.requestPictureInPicture()
  } catch {
    emit('notice', 'تصویر در تصویر در این مرورگر فعال نشد')
  }
}

function handleFullscreenChange() {
  isFullscreen.value = activeFullscreenElement() === root.value
  emit('fullscreenChange', fullscreenActive.value)
  bumpControls(true)
}

function handleIosVideoFullscreen(active: boolean) {
  isFullscreen.value = active
  emit('fullscreenChange', fullscreenActive.value)
  bumpControls(true)
}

/** Lock-screen / hardware media key integration (mobile platforms). */
function setupMediaSession() {
  if (typeof navigator === 'undefined' || !('mediaSession' in navigator)) return
  const session = navigator.mediaSession
  try {
    session.metadata = new MediaMetadata({
      title: props.title,
      artist: 'روایتو',
      artwork: props.poster ? [{ src: props.poster }] : [],
    })
  } catch { /* MediaMetadata unsupported */ }
  const guarded = (action: MediaSessionAction, handler: MediaSessionActionHandler) => {
    try { session.setActionHandler(action, (details) => { if (!props.locked) handler(details) }) }
    catch { /* action unsupported on this platform */ }
  }
  guarded('play', () => { void togglePlayback() })
  guarded('pause', () => { void togglePlayback() })
  guarded('seekbackward', () => skip(-10))
  guarded('seekforward', () => skip(10))
  guarded('seekto', (details) => {
    if (typeof details.seekTime === 'number' && video.value) video.value.currentTime = details.seekTime
  })
}

function teardownMediaSession() {
  if (typeof navigator === 'undefined' || !('mediaSession' in navigator)) return
  ;(['play', 'pause', 'seekbackward', 'seekforward', 'seekto'] as MediaSessionAction[]).forEach((action) => {
    try { navigator.mediaSession.setActionHandler(action, null) } catch { /* ignore */ }
  })
}

function handleKeydown(event: KeyboardEvent) {
  const target = event.target as HTMLElement | null
  if (target?.matches('input, textarea, select, button')) return
  if (!root.value?.contains(document.activeElement) && document.fullscreenElement !== root.value) return
  if (event.key === ' ' || event.key.toLowerCase() === 'k') {
    event.preventDefault()
    void togglePlayback()
  } else if (event.key === 'ArrowLeft') {
    event.preventDefault()
    skip(-10)
  } else if (event.key === 'ArrowRight') {
    event.preventDefault()
    skip(10)
  } else if (event.key === 'ArrowUp') {
    event.preventDefault()
    setVolume(volume.value + 0.05)
  } else if (event.key === 'ArrowDown') {
    event.preventDefault()
    setVolume(volume.value - 0.05)
  } else if (event.key.toLowerCase() === 'm') {
    toggleMute()
  } else if (event.key.toLowerCase() === 'f') {
    void toggleFullscreen()
  }
  bumpControls()
}

function handleSurfaceClick(event: MouseEvent) {
  if ((event.target as HTMLElement).closest('[data-player-ui]')) return
  root.value?.focus({ preventScroll: true })
  void togglePlayback()
}

onMounted(() => {
  pipSupported.value = Boolean(document.pictureInPictureEnabled && video.value?.requestPictureInPicture)
  document.addEventListener('fullscreenchange', handleFullscreenChange)
  document.addEventListener('webkitfullscreenchange', handleFullscreenChange)
  window.addEventListener('keydown', handleKeydown)
  video.value?.addEventListener('enterpictureinpicture', () => { isPip.value = true })
  video.value?.addEventListener('leavepictureinpicture', () => { isPip.value = false })
  video.value?.addEventListener('webkitbeginfullscreen', () => handleIosVideoFullscreen(true))
  video.value?.addEventListener('webkitendfullscreen', () => handleIosVideoFullscreen(false))
  setupMediaSession()
  loadSubtitleAppearance()
  syncSubtitleTracks()
  void loadSource()
  bumpControls(true)
})

watch(() => props.src, () => { void loadSource() })
watch(() => props.quality, applyQuality)
watch(() => props.lowLatency, () => { void loadSource() })
watch(() => [props.title, props.poster], setupMediaSession)
watch(() => props.subtitleTracks.map(track => `${track.id}:${track.src}`).join('|'), syncSubtitleTracks)
watch(showSettings, (open) => {
  if (open) bumpControls(true)
  else bumpControls()
})
watch([subtitlePosition, subtitleScale], persistSubtitleAppearance)

onBeforeUnmount(() => {
  subtitleLoadToken += 1
  // Flush any pending crowd-sync feedback the debounce hasn't sent yet.
  if (subtitleSyncTimer) reportSubtitleSyncFeedback()
  destroyPlayer()
  cancelControlsTimer()
  document.removeEventListener('fullscreenchange', handleFullscreenChange)
  document.removeEventListener('webkitfullscreenchange', handleFullscreenChange)
  window.removeEventListener('keydown', handleKeydown)
  teardownMediaSession()
  if (isPseudoFullscreen.value) document.body.style.overflow = previousBodyOverflow
})
</script>

<template>
  <div
    ref="root"
    data-video-player
    class="revayato-player group relative isolate overflow-hidden bg-black text-white shadow-2xl ring-1 ring-white/10 outline-none"
    :class="[
      fill ? 'h-full w-full' : 'aspect-video rounded-xl sm:rounded-2xl',
      fullscreenActive && 'revayato-player--fullscreen',
      showControls && 'is-controls-visible',
    ]"
    :aria-label="`پخش ${title}`"
    :aria-busy="loading"
    tabindex="0"
    role="region"
    dir="rtl"
    @mousemove="bumpControls()"
    @pointerdown="bumpControls()"
    @mouseleave="bumpControls()"
    @click="handleSurfaceClick"
    @dblclick.stop="toggleFullscreen"
  >
    <video
      ref="video"
      class="revayato-player__video h-full w-full object-contain"
      :poster="poster"
      :controls="false"
      controlslist="nodownload noplaybackrate"
      playsinline
      webkit-playsinline
      preload="auto"
      @loadedmetadata="setReady"
      @durationchange="setReady"
      @canplay="setReady"
      @waiting="beginLoading"
      @stalled="beginLoading"
      @playing="handlePlaying"
      @play="handlePlay"
      @pause="handlePause"
      @seeked="handleSeeked"
      @timeupdate="handleTimeUpdate"
      @progress="syncBuffer"
      @volumechange="volume = video?.volume || 0; isMuted = Boolean(video?.muted)"
      @ratechange="playbackRate = video?.playbackRate || 1"
      @ended="handleEnded"
      @error="handleNativeError"
    />

    <div class="revayato-player__vignette pointer-events-none absolute inset-0" />

    <div
      v-if="partySync"
      data-player-ui
      class="absolute end-3 top-3 z-20 inline-flex items-center gap-2 rounded-full bg-black/65 px-3 py-1.5 text-[11px] font-black text-white/80 ring-1 ring-white/15 backdrop-blur-md sm:end-4 sm:top-4 sm:text-xs"
    >
      <span class="size-1.5 animate-pulse rounded-full bg-success" />
      {{ locked ? 'هماهنگ با میزبان' : 'میزبان اتاق' }}
    </div>

    <Transition name="player-fade">
      <button
        v-if="controls && showControls && !loading && !errorMessage"
        data-player-ui
        type="button"
        class="revayato-player__center-play absolute left-1/2 top-1/2 z-10 grid size-16 -translate-x-1/2 -translate-y-1/2 place-items-center rounded-full bg-black/45 text-white ring-1 ring-white/25 backdrop-blur-sm transition hover:scale-105 hover:bg-primary-500 hover:text-night-950 sm:size-20"
        :aria-label="isPlaying ? 'توقف پخش' : 'شروع پخش'"
        @click.stop="togglePlayback"
      >
        <CinematicIcon :name="isPlaying ? 'pause' : 'play'" class="size-7 sm:size-9" />
      </button>
    </Transition>

    <div
      v-if="cueLines.length"
      class="revayato-player__captions pointer-events-none absolute inset-x-4 z-20 mx-auto text-center"
      :style="captionStyle"
      aria-live="off"
    >
      <span v-for="(line, index) in cueLines" :key="`${index}-${line}`" class="block">
        <span>{{ line }}</span>
      </span>
    </div>

    <Transition name="player-fade">
      <div v-if="loading && !errorMessage" class="pointer-events-none absolute inset-0 z-20 grid place-items-center bg-black/35">
        <div class="rounded-2xl bg-black/55 px-5 py-4 text-center ring-1 ring-white/10 backdrop-blur-md" style="--spinner-color: #fff;">
          <LoadingSpinnerA size="large" class="!text-white/85">در حال آماده‌سازی پخش…</LoadingSpinnerA>
        </div>
      </div>
    </Transition>

    <div v-if="errorMessage" data-player-ui class="absolute inset-0 z-30 grid place-items-center bg-slate-950/92 p-4 text-center">
      <div class="max-w-md">
        <span class="mx-auto grid size-12 place-items-center rounded-2xl bg-error/15 text-error ring-1 ring-error/25">
          <CinematicIcon name="alert-triangle" class="size-6" />
        </span>
        <p class="mt-4 font-black">پخش ویدیو ممکن نشد</p>
        <p class="mt-1 text-xs leading-6 text-white/55 sm:text-sm">{{ errorMessage }}</p>
        <button type="button" class="mt-5 inline-flex min-h-11 items-center gap-2 rounded-xl bg-white/10 px-4 text-sm font-black ring-1 ring-white/15 hover:bg-white/20" @click.stop="loadSource">
          <CinematicIcon name="refresh" class="size-4" />تلاش دوباره
        </button>
      </div>
    </div>

    <Transition name="player-controls">
      <div
        v-if="controls && showControls && !errorMessage"
        data-player-ui
        class="revayato-player__controls absolute inset-x-0 bottom-0 z-20 px-3 pb-3 pt-16 sm:px-5 sm:pb-4 sm:pt-24"
        @click.stop
      >
        <div class="revayato-player__timeline relative mb-2.5 flex h-5 items-center sm:mb-3">
          <div class="pointer-events-none absolute inset-x-0 h-1.5 overflow-hidden rounded-full bg-white/20">
            <span
              class="absolute inset-y-0 bg-white/25"
              :style="{ insetInlineStart: `${windowStartPercent}%`, width: `${Math.max(0, bufferedPercent - windowStartPercent)}%` }"
            />
            <span class="absolute inset-y-0 start-0 bg-primary-500" :style="{ width: `${progressPercent}%` }" />
          </div>
          <input
            class="revayato-player__range relative z-10 w-full cursor-pointer"
            type="range"
            min="0"
            max="100"
            step="0.05"
            :value="progressPercent"
            :disabled="locked || !duration"
            aria-label="موقعیت پخش"
            dir="ltr"
            @input="handleProgressInput"
          >
        </div>

        <div class="flex min-w-0 items-center gap-1 sm:gap-1.5">
          <button class="revayato-player__btn" type="button" :aria-label="isPlaying ? 'توقف' : 'پخش'" @click="togglePlayback">
            <CinematicIcon :name="isPlaying ? 'pause' : 'play'" class="size-5" />
          </button>
          <button class="revayato-player__btn hidden sm:grid" type="button" aria-label="۱۰ ثانیه عقب" :disabled="locked" @click="skip(-10)">
            <CinematicIcon name="rewind" class="size-5" />
          </button>
          <button class="revayato-player__btn hidden sm:grid" type="button" aria-label="۱۰ ثانیه جلو" :disabled="locked" @click="skip(10)">
            <CinematicIcon name="fast-forward" class="size-5" />
          </button>

          <div class="revayato-player__volume flex items-center">
            <button class="revayato-player__btn" type="button" :aria-label="isMuted ? 'وصل کردن صدا' : 'قطع صدا'" @click="toggleMute">
              <CinematicIcon :name="isMuted || volume === 0 ? 'volume-x' : volume < 0.5 ? 'volume-1' : 'volume'" class="size-5" />
            </button>
            <input
              class="revayato-player__volume-range hidden w-20 sm:block"
              type="range"
              min="0"
              max="1"
              step="0.02"
              :value="isMuted ? 0 : volume"
              aria-label="بلندی صدا"
              dir="ltr"
              @input="handleVolumeInput"
            >
          </div>

          <span class="ms-1 shrink-0 font-latin text-[11px] font-bold tabular-nums text-white/65 sm:text-xs">
            {{ formatTime(filmCurrentTime) }} <span class="hidden sm:inline">/ {{ formatTime(filmDuration) }}</span>
          </span>

          <div class="min-w-0 flex-1" />

          <button v-if="previousEpisode" class="revayato-player__btn hidden md:grid" type="button" aria-label="قسمت قبل" :disabled="locked" @click="requestEpisode(previousEpisode)">
            <CinematicIcon name="chevron-right" class="size-5" />
          </button>
          <button v-if="nextEpisode" class="revayato-player__btn hidden md:grid" type="button" aria-label="قسمت بعد" :disabled="locked" @click="requestEpisode(nextEpisode)">
            <CinematicIcon name="chevron-left" class="size-5" />
          </button>

          <button v-if="subtitleOptions.length" class="revayato-player__btn" type="button" :class="selectedSubtitleId !== 'off' && 'is-active'" aria-label="زیرنویس" @click="openSettings('subtitle')">
            <CinematicIcon name="captions" class="size-5" />
          </button>
          <button class="revayato-player__quality hidden min-w-12 sm:inline-flex" type="button" @click="openSettings('quality')">
            {{ qualityLabel }}
          </button>
          <button v-if="canReport" class="revayato-player__btn" type="button" aria-label="گزارش خطا" @click="openReport">
            <CinematicIcon name="flag" class="size-5" />
          </button>
          <button class="revayato-player__btn" type="button" aria-label="تنظیمات پخش" @click="openSettings(selectableVersions.length > 1 ? 'version' : episodeOptions.length ? 'episodes' : 'quality')">
            <CinematicIcon name="settings" class="size-5" />
          </button>
          <button v-if="pipSupported" class="revayato-player__btn hidden sm:grid" type="button" :class="isPip && 'is-active'" aria-label="تصویر در تصویر" @click="togglePip">
            <CinematicIcon name="picture-in-picture" class="size-5" />
          </button>
          <button class="revayato-player__btn" type="button" :aria-label="fullscreenActive ? 'خروج از تمام صفحه' : 'تمام صفحه'" @click="toggleFullscreen">
            <CinematicIcon :name="fullscreenActive ? 'minimize' : 'maximize'" class="size-5" />
          </button>
        </div>
      </div>
    </Transition>

    <Transition name="player-settings">
      <div v-if="showSettings" data-player-ui class="revayato-player__settings-layer absolute inset-0 z-[28]" @click.stop>
        <button type="button" class="absolute inset-0 bg-black/40" aria-label="بستن تنظیمات" @click="showSettings = false" />
        <section class="revayato-player__settings absolute bottom-3 end-3 start-3 max-h-[74%] overflow-hidden rounded-2xl bg-slate-950/95 text-white shadow-2xl ring-1 ring-white/15 backdrop-blur-xl sm:bottom-20 sm:end-5 sm:start-auto sm:w-[25rem]">
          <header class="flex items-center justify-between border-b border-white/10 px-4 py-3">
            <div class="min-w-0">
              <p class="text-sm font-black">تنظیمات پخش</p>
              <p v-if="locked" class="mt-0.5 text-[11px] text-primary-300">گزینه‌های مشترک در اختیار میزبان است</p>
            </div>
            <button class="revayato-player__btn" type="button" aria-label="بستن" @click="showSettings = false"><CinematicIcon name="x" class="size-5" /></button>
          </header>

          <nav class="hide-scrollbar flex gap-1 overflow-x-auto border-b border-white/8 px-3 py-2" aria-label="بخش تنظیمات">
            <button v-if="episodeOptions.length" type="button" class="revayato-player__tab" :class="settingsTab === 'episodes' && 'is-active'" @click="settingsTab = 'episodes'">قسمت‌ها</button>
            <button v-if="selectableVersions.length > 1" type="button" class="revayato-player__tab" :class="settingsTab === 'version' && 'is-active'" @click="settingsTab = 'version'">نسخه</button>
            <button type="button" class="revayato-player__tab" :class="settingsTab === 'quality' && 'is-active'" @click="settingsTab = 'quality'">کیفیت</button>
            <button type="button" class="revayato-player__tab" :class="settingsTab === 'speed' && 'is-active'" @click="settingsTab = 'speed'">سرعت</button>
            <button v-if="subtitleOptions.length" type="button" class="revayato-player__tab" :class="settingsTab === 'subtitle' && 'is-active'" @click="settingsTab = 'subtitle'">زیرنویس</button>
          </nav>

          <div class="max-h-[48dvh] overflow-y-auto p-3 sm:max-h-80">
            <div v-if="settingsTab === 'episodes'" class="space-y-3">
              <div v-if="episodeSeasons.length > 1" class="hide-scrollbar flex gap-1.5 overflow-x-auto">
                <button v-for="season in episodeSeasons" :key="season" type="button" class="revayato-player__chip" :class="selectedSeason === season && 'is-active'" @click="selectedSeason = season">فصل {{ season.toLocaleString('fa-IR') }}</button>
              </div>
              <div class="grid gap-1.5">
                <button v-for="episode in visibleEpisodes" :key="episode.id" type="button" class="revayato-player__option" :class="episode.id === activeEpisodeId && 'is-active'" :disabled="locked" @click="requestEpisode(episode)">
                  <span class="grid size-9 shrink-0 place-items-center rounded-lg bg-white/8 font-latin text-xs font-black">{{ episode.episode_number }}</span>
                  <span class="min-w-0 flex-1 truncate text-start">{{ episode.title || `قسمت ${episode.episode_number.toLocaleString('fa-IR')}` }}</span>
                  <CinematicIcon v-if="episode.id === activeEpisodeId" name="check" class="size-4 text-primary-300" />
                </button>
              </div>
            </div>

            <div v-else-if="settingsTab === 'version'" class="grid gap-1.5">
              <button v-for="version in selectableVersions" :key="version.id" type="button" class="revayato-player__option" :class="version.id === activeVersion?.id && 'is-active'" :disabled="locked" @click="requestVersion(version)">
                <CinematicIcon :name="version.kind === 'dub' ? 'audio' : 'subtitle'" class="size-5 shrink-0" />
                <span class="min-w-0 flex-1 text-start"><strong class="block truncate">{{ version.label }}</strong><small class="mt-0.5 block text-white/40">{{ formatQuality(version.quality || sourceQuality) }}</small></span>
                <CinematicIcon v-if="version.id === activeVersion?.id" name="check" class="size-4 text-primary-300" />
              </button>
            </div>

            <div v-else-if="settingsTab === 'quality'" class="grid grid-cols-2 gap-2">
              <button v-for="qualityOption in qualityOptions" :key="qualityOption" type="button" class="revayato-player__tile" :class="qualityOption === quality && 'is-active'" :disabled="locked" @click="requestQuality(qualityOption)">
                <span class="font-latin text-sm font-black">{{ formatQuality(qualityOption) }}</span>
                <small>{{ qualityOption === 'auto' ? 'پیشنهادی' : 'انتخاب ثابت' }}</small>
              </button>
            </div>

            <div v-else-if="settingsTab === 'speed'" class="grid grid-cols-3 gap-2">
              <button v-for="rate in rateOptions" :key="rate" type="button" class="revayato-player__tile" :class="playbackRate === rate && 'is-active'" :disabled="locked" @click="setRate(rate)">
                <span class="font-latin text-sm font-black">{{ rate }}×</span><small>{{ rate === 1 ? 'عادی' : 'سرعت' }}</small>
              </button>
            </div>

            <div v-else class="grid gap-1.5">
              <button type="button" class="revayato-player__option" :class="selectedSubtitleId === 'off' && 'is-active'" @click="chooseSubtitle('off')">
                <CinematicIcon name="captions" class="size-5" /><span class="flex-1 text-start">خاموش</span><CinematicIcon v-if="selectedSubtitleId === 'off'" name="check" class="size-4 text-primary-300" />
              </button>
              <button v-for="track in subtitleOptions" :key="track.id" type="button" class="revayato-player__option" :class="selectedSubtitleId === track.id && 'is-active'" @click="chooseSubtitle(track.id)">
                <CinematicIcon name="subtitle" class="size-5" /><span class="min-w-0 flex-1 truncate text-start">{{ track.label || track.language }}</span><CinematicIcon v-if="selectedSubtitleId === track.id" name="check" class="size-4 text-primary-300" />
              </button>
              <p v-if="subtitleLoading" class="px-2 py-1 text-xs text-white/45">در حال آماده‌سازی زیرنویس…</p>
              <p v-if="subtitleError" class="rounded-lg bg-error/10 px-3 py-2 text-xs text-error">{{ subtitleError }}</p>

              <div v-if="selectedSubtitleId !== 'off'" class="mt-1 rounded-xl bg-white/[.03] p-3 ring-1 ring-white/10">
                <div class="flex items-center justify-between gap-2">
                  <p class="text-xs font-black text-white/70">هماهنگ‌سازی زیرنویس</p>
                  <button type="button" class="text-[11px] font-bold text-white/40 transition hover:text-white/80" :disabled="subtitleOffset === 0" @click="resetSubtitleOffset">
                    {{ subtitleOffset === 0 ? 'در وضعیت عادی' : 'بازگردانی' }}
                  </button>
                </div>
                <div class="mt-2 flex items-center justify-between gap-2">
                  <button type="button" class="revayato-player__btn size-9" aria-label="زیرنویس دیرتر (منفی)" @click="nudgeSubtitleOffset(-SUBTITLE_OFFSET_STEP)">
                    <CinematicIcon name="minus" class="size-4" />
                  </button>
                  <div class="min-w-0 text-center">
                    <p class="font-latin text-sm font-black tabular-nums" :class="subtitleOffset === 0 ? 'text-white/50' : subtitleOffset > 0 ? 'text-primary-300' : 'text-sky-300'">
                      {{ subtitleOffset > 0 ? '+' : '' }}{{ subtitleOffset }}s
                    </p>
                    <p class="text-[11px] leading-relaxed text-white/35">
                      {{ subtitleOffset > 0 ? 'زیرنویس جلوتر' : subtitleOffset < 0 ? 'زیرنویس عقب‌تر' : 'هماهنگ' }}
                    </p>
                  </div>
                  <button type="button" class="revayato-player__btn size-9" aria-label="زیرنویس زودتر (مثبت)" @click="nudgeSubtitleOffset(SUBTITLE_OFFSET_STEP)">
                    <CinematicIcon name="plus" class="size-4" />
                  </button>
                </div>
                <p class="mt-1.5 text-center text-[11px] leading-relaxed text-white/30">
                  اگر زیرنویس دیر ظاهر می‌شود، {{ SUBTITLE_OFFSET_STEP }} به جلو بزنید.
                </p>
              </div>

              <div v-if="selectedSubtitleId !== 'off'" class="mt-1.5 rounded-xl bg-white/[.03] p-3 ring-1 ring-white/10">
                <div class="flex items-center justify-between gap-2">
                  <p class="text-xs font-black text-white/70">ظاهر زیرنویس</p>
                  <button
                    type="button"
                    class="text-[11px] font-bold text-white/40 transition hover:text-white/80"
                    :disabled="subtitlePosition === SUBTITLE_POS_DEFAULT && subtitleScale === SUBTITLE_SCALE_DEFAULT"
                    @click="resetSubtitleAppearance"
                  >
                    {{ (subtitlePosition === SUBTITLE_POS_DEFAULT && subtitleScale === SUBTITLE_SCALE_DEFAULT) ? 'پیش‌فرض' : 'بازگردانی' }}
                  </button>
                </div>
                <label class="mt-2.5 block">
                  <span class="mb-1 flex items-center justify-between text-[11px] text-white/45">
                    <span>فاصله از پایین</span>
                    <span class="font-latin tabular-nums text-white/60">٪{{ subtitlePosition }}</span>
                  </span>
                  <input
                    v-model.number="subtitlePosition"
                    type="range"
                    class="revayato-player__setting-range"
                    :min="SUBTITLE_POS_MIN"
                    :max="SUBTITLE_POS_MAX"
                    step="1"
                    aria-label="فاصله زیرنویس از پایین"
                  >
                </label>
                <label class="mt-2 block">
                  <span class="mb-1 flex items-center justify-between text-[11px] text-white/45">
                    <span>اندازه متن</span>
                    <span class="font-latin tabular-nums text-white/60">٪{{ subtitleScale }}</span>
                  </span>
                  <input
                    v-model.number="subtitleScale"
                    type="range"
                    class="revayato-player__setting-range"
                    :min="SUBTITLE_SCALE_MIN"
                    :max="SUBTITLE_SCALE_MAX"
                    step="5"
                    aria-label="اندازه متن زیرنویس"
                  >
                </label>
              </div>
            </div>
          </div>
        </section>
      </div>
    </Transition>

    <Transition name="player-settings">
      <div v-if="showReport" data-player-ui class="revayato-player__settings-layer absolute inset-0 z-[29]" @click.stop>
        <button type="button" class="absolute inset-0 bg-black/40" aria-label="بستن گزارش خطا" @click="showReport = false" />
        <section class="revayato-player__settings absolute bottom-3 end-3 start-3 max-h-[80%] overflow-hidden rounded-2xl bg-slate-950/95 text-white shadow-2xl ring-1 ring-white/15 backdrop-blur-xl sm:bottom-20 sm:end-5 sm:start-auto sm:w-[26rem]">
          <header class="flex items-center justify-between border-b border-white/10 px-4 py-3">
            <div class="flex min-w-0 items-center gap-2.5">
              <span class="grid size-9 shrink-0 place-items-center rounded-xl bg-amber-400/15 text-amber-300 ring-1 ring-amber-300/25">
                <CinematicIcon name="flag" class="size-4.5" />
              </span>
              <div class="min-w-0">
                <p class="text-sm font-black">گزارش خطا</p>
                <p class="mt-0.5 text-[11px] text-white/50">مشکل را انتخاب کن تا خودکار بررسی و رفع شود</p>
              </div>
            </div>
            <button class="revayato-player__btn" type="button" aria-label="بستن" @click="showReport = false"><CinematicIcon name="x" class="size-5" /></button>
          </header>

          <div class="max-h-[58dvh] overflow-y-auto p-3 sm:max-h-96">
            <Transition name="player-settings" mode="out-in">
              <div v-if="reportDone" key="done" class="grid place-items-center gap-3 px-4 py-9 text-center">
                <span class="grid size-14 place-items-center rounded-full bg-emerald-400/15 text-emerald-300 ring-1 ring-emerald-300/30">
                  <CinematicIcon name="check-circle" class="size-7" />
                </span>
                <p class="text-sm font-black">گزارشت ثبت شد</p>
                <p class="max-w-xs text-xs leading-6 text-white/55">سیستم به‌صورت خودکار در حال بررسی و رفع مشکل است. اگر لازم باشد تیم روایتو هم می‌بیند. ممنون که کمک کردی!</p>
                <button type="button" class="mt-1 rounded-xl bg-white/10 px-4 py-2 text-xs font-bold transition hover:bg-white/15" @click="showReport = false">بستن</button>
              </div>

              <div v-else key="compose" class="grid gap-1.5">
                <p class="px-1 pb-1 text-xs font-bold text-white/55">چه مشکلی دیدی؟</p>
                <div v-for="group in reportGroups" :key="group.key" class="grid gap-1.5">
                  <p class="px-1 pt-1.5 text-[11px] font-black tracking-wide text-white/35">{{ group.label }}</p>
                  <button
                    v-for="option in group.options"
                    :key="option.value"
                    type="button"
                    class="revayato-player__option items-start !py-2.5"
                    :class="reportProblem === option.value && 'is-active'"
                    @click="reportProblem = option.value"
                  >
                    <span class="grid size-9 shrink-0 place-items-center rounded-lg bg-white/8"><CinematicIcon :name="(option.icon as CinematicIconName)" class="size-4.5" /></span>
                    <span class="min-w-0 flex-1 text-start">
                      <strong class="block truncate text-[13px]">{{ option.label }}</strong>
                      <small class="mt-0.5 block leading-4 text-white/40">{{ option.hint }}</small>
                    </span>
                    <CinematicIcon v-if="reportProblem === option.value" name="check" class="mt-1 size-4 text-primary-300" />
                  </button>
                </div>

                <textarea
                  v-model="reportDetail"
                  rows="2"
                  maxlength="500"
                  class="mt-1 w-full resize-none rounded-xl bg-white/[.04] px-3 py-2.5 text-[13px] leading-6 text-white outline-none ring-1 ring-white/10 transition placeholder:text-white/30 focus:ring-primary-400/50"
                  placeholder="توضیح اختیاری… (مثلاً «زیرنویس از دقیقه ۱۰ عقب می‌افتد»)"
                  aria-label="توضیح مشکل"
                />

                <button
                  type="button"
                  class="mt-1 inline-flex min-h-11 items-center justify-center gap-2 rounded-xl bg-gradient-to-l from-amber-400 to-amber-300 px-4 text-[13px] font-black text-amber-950 transition enabled:hover:brightness-105 disabled:opacity-40"
                  :disabled="!reportProblem || reportSubmitting"
                  @click="submitReport"
                >
                  <CinematicIcon name="send" class="size-4" />
                  {{ reportSubmitting ? 'در حال ارسال…' : 'ارسال گزارش' }}
                </button>
              </div>
            </Transition>
          </div>
        </section>
      </div>
    </Transition>

    <slot name="fullscreen-overlay" :is-fullscreen="fullscreenActive" />
  </div>
</template>

<style scoped>
.revayato-player {
  --player-accent: #e4ff3f;
  min-height: 0;
  user-select: none;
  -webkit-tap-highlight-color: transparent;
}

.revayato-player--fullscreen {
  position: fixed !important;
  inset: 0 !important;
  z-index: 9999 !important;
  width: 100vw !important;
  height: 100dvh !important;
  border-radius: 0 !important;
}

.revayato-player__video {
  display: block;
  background: #000;
}

.revayato-player__vignette {
  background: linear-gradient(180deg, rgb(0 0 0 / 28%) 0%, transparent 28%, transparent 58%, rgb(0 0 0 / 78%) 100%);
  opacity: 0;
  transition: opacity 180ms ease;
}

.is-controls-visible .revayato-player__vignette { opacity: 1; }

.revayato-player__controls {
  background: linear-gradient(180deg, transparent, rgb(0 0 0 / 88%));
}

.revayato-player__btn {
  display: grid;
  width: 2.5rem;
  height: 2.5rem;
  flex: 0 0 auto;
  place-items: center;
  border: 0;
  border-radius: 0.75rem;
  background: transparent;
  color: rgb(255 255 255 / 82%);
  transition: background-color 150ms ease, color 150ms ease, transform 150ms ease;
}

.revayato-player__btn:hover:not(:disabled),
.revayato-player__btn.is-active {
  background: rgb(255 255 255 / 12%);
  color: var(--player-accent);
}

.revayato-player__btn:active:not(:disabled) { transform: scale(.92); }
.revayato-player__btn:disabled { cursor: not-allowed; opacity: .38; }

.revayato-player__quality {
  min-height: 2.5rem;
  align-items: center;
  justify-content: center;
  border: 0;
  border-radius: .75rem;
  background: rgb(255 255 255 / 8%);
  padding-inline: .65rem;
  color: rgb(255 255 255 / 76%);
  font-size: 0.75rem;
  font-weight: 900;
}

.revayato-player__range,
.revayato-player__volume-range {
  appearance: none;
  height: 1.25rem;
  border: 0;
  outline: 0;
  background: transparent;
}

.revayato-player__range::-webkit-slider-runnable-track { height: .35rem; background: transparent; }
.revayato-player__range::-moz-range-track { height: .35rem; background: transparent; }
.revayato-player__range::-webkit-slider-thumb {
  appearance: none;
  width: .9rem;
  height: .9rem;
  margin-top: -.28rem;
  border: 2px solid #0a0a0a;
  border-radius: 999px;
  background: var(--player-accent);
  box-shadow: 0 0 0 3px rgb(228 255 63 / 18%);
}
.revayato-player__range::-moz-range-thumb {
  width: .8rem;
  height: .8rem;
  border: 2px solid #0a0a0a;
  border-radius: 999px;
  background: var(--player-accent);
}
.revayato-player__range:disabled { cursor: not-allowed; opacity: .55; }

.revayato-player__volume-range::-webkit-slider-runnable-track { height: .22rem; border-radius: 999px; background: rgb(255 255 255 / 28%); }
.revayato-player__volume-range::-moz-range-track { height: .22rem; border-radius: 999px; background: rgb(255 255 255 / 28%); }
.revayato-player__volume-range::-webkit-slider-thumb { appearance: none; width: .7rem; height: .7rem; margin-top: -.24rem; border-radius: 999px; background: white; }
.revayato-player__volume-range::-moz-range-thumb { width: .7rem; height: .7rem; border: 0; border-radius: 999px; background: white; }

.revayato-player__setting-range { appearance: none; width: 100%; height: 1.1rem; border: 0; outline: 0; background: transparent; }
.revayato-player__setting-range::-webkit-slider-runnable-track { height: .28rem; border-radius: 999px; background: rgb(255 255 255 / 22%); }
.revayato-player__setting-range::-moz-range-track { height: .28rem; border-radius: 999px; background: rgb(255 255 255 / 22%); }
.revayato-player__setting-range::-webkit-slider-thumb { appearance: none; width: .85rem; height: .85rem; margin-top: -.29rem; border: 2px solid #0a0a0a; border-radius: 999px; background: var(--player-accent); }
.revayato-player__setting-range::-moz-range-thumb { width: .8rem; height: .8rem; border: 2px solid #0a0a0a; border-radius: 999px; background: var(--player-accent); }

.revayato-player__captions {
  bottom: var(--caption-bottom, 9%);
  max-width: min(58rem, calc(100% - 2rem));
  font-size: calc(clamp(1rem, 2.1vw, 1.75rem) * var(--caption-scale, 1));
  font-weight: 800;
  line-height: 1.85;
  text-shadow: 0 2px 3px #000, 0 0 8px #000;
  transition: bottom 160ms ease;
}

.revayato-player__captions span > span {
  box-decoration-break: clone;
  -webkit-box-decoration-break: clone;
  border-radius: .3rem;
  background: rgb(0 0 0 / 76%);
  padding: .08em .35em .15em;
}

.revayato-player__tab,
.revayato-player__chip {
  min-height: 2.25rem;
  flex: 0 0 auto;
  border: 1px solid transparent;
  border-radius: .65rem;
  background: transparent;
  padding-inline: .75rem;
  color: rgb(255 255 255 / 52%);
  font-size: .72rem;
  font-weight: 900;
}

.revayato-player__tab.is-active,
.revayato-player__chip.is-active {
  border-color: rgb(228 255 63 / 22%);
  background: rgb(228 255 63 / 10%);
  color: var(--player-accent);
}

.revayato-player__option {
  display: flex;
  min-height: 3rem;
  width: 100%;
  align-items: center;
  gap: .65rem;
  border: 1px solid transparent;
  border-radius: .8rem;
  background: rgb(255 255 255 / 4%);
  padding: .55rem .7rem;
  color: rgb(255 255 255 / 68%);
  font-size: .75rem;
  font-weight: 800;
  transition: background-color 150ms ease, border-color 150ms ease, color 150ms ease;
}

.revayato-player__option:hover:not(:disabled),
.revayato-player__option.is-active {
  border-color: rgb(255 255 255 / 10%);
  background: rgb(255 255 255 / 8%);
  color: white;
}

.revayato-player__option:disabled { cursor: not-allowed; opacity: .55; }

.revayato-player__tile {
  display: grid;
  min-height: 3.4rem;
  place-items: center;
  gap: .1rem;
  border: 1px solid rgb(255 255 255 / 8%);
  border-radius: .8rem;
  background: rgb(255 255 255 / 4%);
  color: rgb(255 255 255 / 68%);
}

.revayato-player__tile small { font-size: 0.75rem; color: rgb(255 255 255 / 35%); }
.revayato-player__tile.is-active { border-color: rgb(228 255 63 / 28%); background: rgb(228 255 63 / 10%); color: var(--player-accent); }
.revayato-player__tile:disabled { cursor: not-allowed; opacity: .5; }

.player-controls-enter-active,
.player-controls-leave-active,
.player-fade-enter-active,
.player-fade-leave-active { transition: opacity 180ms ease, transform 180ms ease; }
.player-controls-enter-from,
.player-controls-leave-to { opacity: 0; transform: translateY(.75rem); }
.player-fade-enter-from,
.player-fade-leave-to { opacity: 0; transform: translate(-50%, -50%) scale(.88); }
.player-settings-enter-active,
.player-settings-leave-active { transition: opacity 160ms ease; }
.player-settings-enter-from,
.player-settings-leave-to { opacity: 0; }

@media (max-width: 639px) {
  .revayato-player__captions { bottom: var(--caption-bottom, 9%); font-size: calc(clamp(.9rem, 4vw, 1.15rem) * var(--caption-scale, 1)); line-height: 1.75; }
  .revayato-player__center-play { display: none; }
  .revayato-player__btn { width: 2.25rem; height: 2.25rem; }
}

@media (prefers-reduced-motion: reduce) {
  .revayato-player *,
  .revayato-player *::before,
  .revayato-player *::after { scroll-behavior: auto !important; transition-duration: 1ms !important; animation-duration: 1ms !important; }
}
</style>
