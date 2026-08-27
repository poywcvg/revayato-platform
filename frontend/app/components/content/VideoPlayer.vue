<script setup lang="ts">
import type Hls from 'hls.js'
import type { PlaybackEpisodeOption, PlaybackQuality, PlaybackSnapshot, PlaybackTextTrack, PlaybackVersion } from '~/types'
import { pickDefaultSubtitleTrack } from '~/utils/subtitlePolicy'
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
  notice: [message: string]
  fullscreenChange: [active: boolean]
  syncCorrection: [payload: { type: 'seek' | 'rate', drift: number }]
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
const selectedSeason = ref(0)

let hls: Hls | null = null
let hlsFatalNetworkRetries = 0
let hlsMediaRecoveryDone = false
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
let resumeAfterSourceSeconds: number | null = null
let resumePlaybackAfterLoad = false
let hasLoadedSource = false
let failedSourceEmitted = ''
let previousBodyOverflow = ''

const SOURCE_STARTUP_TIMEOUT_MS = 10_000
const STALL_RECOVERY_TIMEOUT_MS = 8_000
const MAX_STALL_RECOVERY_ATTEMPTS = 3
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

const progressPercent = computed(() => duration.value > 0
  ? Math.min(100, Math.max(0, currentTime.value / duration.value * 100))
  : 0)
const bufferedPercent = computed(() => duration.value > 0
  ? Math.min(100, Math.max(0, bufferedEnd.value / duration.value * 100))
  : 0)
const cueLines = computed(() => activeCueText.value.split('\n').filter(Boolean))
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
  if (video.value) {
    video.value.pause()
    video.value.removeAttribute('src')
    video.value.load()
  }
}

function currentProgress() {
  const element = video.value
  if (!element?.duration || !Number.isFinite(element.duration)) return 0
  return Math.round(element.currentTime / element.duration * 100)
}

function getPlaybackSnapshot(): PlaybackSnapshot {
  const element = video.value
  return {
    is_playing: Boolean(element && !element.paused && !element.ended),
    position_seconds: element?.currentTime || 0,
    duration_seconds: Number.isFinite(element?.duration) ? element?.duration || 0 : 0,
    playback_rate: element?.playbackRate || 1,
  }
}

function prepareResumeAt(seconds: number) {
  if (!Number.isFinite(seconds) || seconds < 0) return
  resumeAfterSourceSeconds = seconds
  const element = video.value
  if (element && element.readyState >= 1 && Number.isFinite(element.duration)) {
    element.currentTime = Math.min(seconds, Math.max(0, element.duration - 0.25))
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
  const currentPosition = Number.isFinite(element.currentTime) ? element.currentTime : 0
  const drift = state.position_seconds - currentPosition
  const seekThreshold = props.partySync && state.is_playing ? 0.6 : state.is_playing ? 1.25 : 0.12
  if (remoteRateResetTimer) clearTimeout(remoteRateResetTimer)
  remoteRateResetTimer = undefined
  applyingRemotePlayback = true
  try {
    if (Math.abs(drift) > seekThreshold) {
      element.currentTime = Math.max(0, Math.min(state.position_seconds, element.duration || state.position_seconds))
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

function updateCue(time = currentTime.value) {
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
  updateCue(video.value?.currentTime || 0)
}

function resetSubtitleOffset() {
  subtitleOffset.value = 0
  updateCue(video.value?.currentTime || 0)
}

function syncBuffer() {
  const element = video.value
  if (!element?.buffered.length) return
  const end = element.buffered.end(element.buffered.length - 1)
  bufferedEnd.value = Math.max(0, end)
  emit('bufferHealth', Math.max(0, end - element.currentTime))
}

function handleTimeUpdate() {
  const element = video.value
  if (!element) return
  currentTime.value = element.currentTime || 0
  duration.value = Number.isFinite(element.duration) ? element.duration : 0
  updateCue(element.currentTime)
  syncBuffer()
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
  if (resumeAfterSourceSeconds != null && duration.value > 0) {
    element.currentTime = Math.min(resumeAfterSourceSeconds, Math.max(0, duration.value - 0.25))
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
    emit('ready', duration.value)
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
  const message = code === MEDIA_ERR_NETWORK
    ? 'ارتباط با منبع ویدیو برقرار نشد.'
    : code === MEDIA_ERR_DECODE
      ? 'کُدک این فایل در مرورگر قابل رمزگشایی نیست.'
      : 'فرمت یا آدرس این فایل برای پخش آنلاین پشتیبانی نمی‌شود.'
  emitSourceFailure(code, message)
}

function armSourceStartupWatchdog(token: number) {
  cancelSourceStartupWatchdog()
  sourceStartupTimer = setTimeout(() => {
    const current = video.value
    if (token !== loadToken || !current || current.readyState >= HTMLMediaElement.HAVE_CURRENT_DATA) return
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
    if (stallRecoveryAttempts === 2 && !isHlsSource(failedSrc)) {
      resumeAfterSourceSeconds = nowSeconds
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

async function loadSource() {
  const token = ++loadToken
  const previous = video.value
  resumePlaybackAfterLoad = hasLoadedSource
    ? Boolean(previous && !previous.paused && !previous.ended)
    : props.autoplay
  if (resumeAfterSourceSeconds == null && hasLoadedSource && previous && previous.currentTime > 1) {
    resumeAfterSourceSeconds = previous.currentTime
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
  currentStreamQuality.value = ''
  const element = video.value
  if (!element || !props.src) {
    errorMessage.value = 'آدرس پخش در دسترس نیست.'
    loading.value = false
    return
  }

  if (!isHlsSource(props.src)) {
    element.src = props.src
    element.load()
    armSourceStartupWatchdog(token)
    return
  }

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
    instance.on(HlsClass.Events.LEVEL_SWITCHED, (_, data) => {
      if (hls !== instance) return
      const height = instance.levels[data.level]?.height
      currentStreamQuality.value = height ? `${height}p` : ''
    })
    instance.on(HlsClass.Events.ERROR, (_, data) => {
      if (!data.fatal || token !== loadToken || hls !== instance) return
      if (data.type === HlsClass.ErrorTypes.NETWORK_ERROR) {
        // Transient network drops: resume loading before giving up on the source.
        if (hlsFatalNetworkRetries < 2) {
          hlsFatalNetworkRetries += 1
          emit('notice', 'اتصال قطع شد؛ در حال تلاش دوباره')
          instance.startLoad()
          return
        }
        emitSourceFailure(MEDIA_ERR_NETWORK, 'ارتباط با جریان ویدیو برقرار نشد.')
      } else if (data.type === HlsClass.ErrorTypes.MEDIA_ERROR) {
        // Decoder hiccups are usually recoverable once per stream.
        if (!hlsMediaRecoveryDone) {
          hlsMediaRecoveryDone = true
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

async function selectSubtitle(trackId: string) {
  selectedSubtitleId.value = trackId
  subtitleLoadToken += 1
  const token = subtitleLoadToken
  subtitleCues.value = []
  activeCueText.value = ''
  subtitleError.value = ''
  subtitleOffset.value = 0
  if (trackId === 'off') return
  const track = props.subtitleTracks.find(candidate => candidate.id === trackId)
  if (!track?.src) return
  subtitleLoading.value = true
  try {
    const cues = await loadSubtitleCues(track.src)
    if (token !== subtitleLoadToken) return
    subtitleCues.value = cues
    updateCue(video.value?.currentTime || 0)
    if (!cues.length) subtitleError.value = 'متن قابل نمایش در این زیرنویس پیدا نشد.'
  } catch {
    if (token === subtitleLoadToken) subtitleError.value = 'بارگذاری زیرنویس انجام نشد.'
  } finally {
    if (token === subtitleLoadToken) subtitleLoading.value = false
  }
}

function syncSubtitleTracks() {
  const preferred = pickDefaultSubtitleTrack(props.subtitleTracks)
  const currentStillExists = props.subtitleTracks.some(track => track.id === selectedSubtitleId.value && track.src)
  const next = currentStillExists ? selectedSubtitleId.value : preferred?.id || 'off'
  void selectSubtitle(next)
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

function seekToPercent(percent: number) {
  if (props.locked) {
    emit('notice', 'جابه‌جایی زمان با میزبان هماهنگ می‌شود')
    return
  }
  const element = video.value
  if (!element || !Number.isFinite(element.duration) || element.duration <= 0) return
  element.currentTime = Math.min(element.duration, Math.max(0, element.duration * percent / 100))
  currentTime.value = element.currentTime
  updateCue(element.currentTime)
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
  element.currentTime = Math.min(element.duration || Number.POSITIVE_INFINITY, Math.max(0, element.currentTime + seconds))
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

onBeforeUnmount(() => {
  subtitleLoadToken += 1
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
      class="absolute end-3 top-3 z-20 inline-flex items-center gap-2 rounded-full bg-black/65 px-3 py-1.5 text-[10px] font-black text-white/80 ring-1 ring-white/15 backdrop-blur-md sm:end-4 sm:top-4 sm:text-xs"
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
      aria-live="off"
    >
      <span v-for="(line, index) in cueLines" :key="`${index}-${line}`" class="block">
        <span>{{ line }}</span>
      </span>
    </div>

    <Transition name="player-fade">
      <div v-if="loading && !errorMessage" class="pointer-events-none absolute inset-0 z-20 grid place-items-center bg-black/35">
        <div class="rounded-2xl bg-black/55 px-5 py-4 text-center ring-1 ring-white/10 backdrop-blur-md">
          <span class="mx-auto block size-9 animate-spin rounded-full border-2 border-white/20 border-t-primary-400" />
          <p class="mt-3 text-xs font-black text-white/85 sm:text-sm">در حال آماده‌سازی پخش…</p>
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
            <span class="absolute inset-y-0 start-0 bg-white/25" :style="{ width: `${bufferedPercent}%` }" />
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

          <span class="ms-1 shrink-0 font-latin text-[10px] font-bold tabular-nums text-white/65 sm:text-xs">
            {{ formatTime(currentTime) }} <span class="hidden sm:inline">/ {{ formatTime(duration) }}</span>
          </span>

          <div class="min-w-0 flex-1" />

          <button v-if="previousEpisode" class="revayato-player__btn hidden md:grid" type="button" aria-label="قسمت قبل" :disabled="locked" @click="requestEpisode(previousEpisode)">
            <CinematicIcon name="chevron-right" class="size-5" />
          </button>
          <button v-if="nextEpisode" class="revayato-player__btn hidden md:grid" type="button" aria-label="قسمت بعد" :disabled="locked" @click="requestEpisode(nextEpisode)">
            <CinematicIcon name="chevron-left" class="size-5" />
          </button>

          <button v-if="subtitleTracks.length" class="revayato-player__btn" type="button" :class="selectedSubtitleId !== 'off' && 'is-active'" aria-label="زیرنویس" @click="openSettings('subtitle')">
            <CinematicIcon name="captions" class="size-5" />
          </button>
          <button class="revayato-player__quality hidden min-w-12 sm:inline-flex" type="button" @click="openSettings('quality')">
            {{ qualityLabel }}
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
              <p v-if="locked" class="mt-0.5 text-[10px] text-primary-300">گزینه‌های مشترک در اختیار میزبان است</p>
            </div>
            <button class="revayato-player__btn" type="button" aria-label="بستن" @click="showSettings = false"><CinematicIcon name="x" class="size-5" /></button>
          </header>

          <nav class="hide-scrollbar flex gap-1 overflow-x-auto border-b border-white/8 px-3 py-2" aria-label="بخش تنظیمات">
            <button v-if="episodeOptions.length" type="button" class="revayato-player__tab" :class="settingsTab === 'episodes' && 'is-active'" @click="settingsTab = 'episodes'">قسمت‌ها</button>
            <button v-if="selectableVersions.length > 1" type="button" class="revayato-player__tab" :class="settingsTab === 'version' && 'is-active'" @click="settingsTab = 'version'">نسخه</button>
            <button type="button" class="revayato-player__tab" :class="settingsTab === 'quality' && 'is-active'" @click="settingsTab = 'quality'">کیفیت</button>
            <button type="button" class="revayato-player__tab" :class="settingsTab === 'speed' && 'is-active'" @click="settingsTab = 'speed'">سرعت</button>
            <button v-if="subtitleTracks.length" type="button" class="revayato-player__tab" :class="settingsTab === 'subtitle' && 'is-active'" @click="settingsTab = 'subtitle'">زیرنویس</button>
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
              <button type="button" class="revayato-player__option" :class="selectedSubtitleId === 'off' && 'is-active'" @click="selectSubtitle('off')">
                <CinematicIcon name="captions" class="size-5" /><span class="flex-1 text-start">خاموش</span><CinematicIcon v-if="selectedSubtitleId === 'off'" name="check" class="size-4 text-primary-300" />
              </button>
              <button v-for="track in subtitleTracks" :key="track.id" type="button" class="revayato-player__option" :class="selectedSubtitleId === track.id && 'is-active'" @click="selectSubtitle(track.id)">
                <CinematicIcon name="subtitle" class="size-5" /><span class="min-w-0 flex-1 truncate text-start">{{ track.label || track.language }}</span><CinematicIcon v-if="selectedSubtitleId === track.id" name="check" class="size-4 text-primary-300" />
              </button>
              <p v-if="subtitleLoading" class="px-2 py-1 text-xs text-white/45">در حال آماده‌سازی زیرنویس…</p>
              <p v-if="subtitleError" class="rounded-lg bg-error/10 px-3 py-2 text-xs text-error">{{ subtitleError }}</p>

              <div v-if="selectedSubtitleId !== 'off'" class="mt-1 rounded-xl bg-white/[.03] p-3 ring-1 ring-white/10">
                <div class="flex items-center justify-between gap-2">
                  <p class="text-[11px] font-black text-white/70">هماهنگ‌سازی زیرنویس</p>
                  <button type="button" class="text-[10px] font-bold text-white/40 transition hover:text-white/80" :disabled="subtitleOffset === 0" @click="resetSubtitleOffset">
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
                    <p class="text-[9px] leading-relaxed text-white/35">
                      {{ subtitleOffset > 0 ? 'زیرنویس جلوتر' : subtitleOffset < 0 ? 'زیرنویس عقب‌تر' : 'هماهنگ' }}
                    </p>
                  </div>
                  <button type="button" class="revayato-player__btn size-9" aria-label="زیرنویس زودتر (مثبت)" @click="nudgeSubtitleOffset(SUBTITLE_OFFSET_STEP)">
                    <CinematicIcon name="plus" class="size-4" />
                  </button>
                </div>
                <p class="mt-1.5 text-center text-[9px] leading-relaxed text-white/30">
                  اگر زیرنویس دیر ظاهر می‌شود، {{ SUBTITLE_OFFSET_STEP }} به جلو بزنید.
                </p>
              </div>
            </div>
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
  font-size: .65rem;
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

.revayato-player__captions {
  bottom: 5.75rem;
  max-width: min(58rem, calc(100% - 2rem));
  font-size: clamp(1rem, 2.1vw, 1.75rem);
  font-weight: 800;
  line-height: 1.85;
  text-shadow: 0 2px 3px #000, 0 0 8px #000;
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

.revayato-player__tile small { font-size: .58rem; color: rgb(255 255 255 / 35%); }
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
  .revayato-player__captions { bottom: 4.8rem; font-size: clamp(.9rem, 4vw, 1.15rem); line-height: 1.75; }
  .revayato-player__center-play { display: none; }
  .revayato-player__btn { width: 2.25rem; height: 2.25rem; }
}

@media (prefers-reduced-motion: reduce) {
  .revayato-player *,
  .revayato-player *::before,
  .revayato-player *::after { scroll-behavior: auto !important; transition-duration: 1ms !important; animation-duration: 1ms !important; }
}
</style>
