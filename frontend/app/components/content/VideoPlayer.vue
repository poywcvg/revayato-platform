<script setup lang="ts">
import type Hls from 'hls.js'
import type { PlaybackQuality, PlaybackSnapshot, PlaybackTextTrack } from '~/types'

const props = withDefaults(defineProps<{
  src: string
  poster?: string
  title?: string
  autoplay?: boolean
  startAtPercent?: number
  quality?: PlaybackQuality
  subtitleTracks?: PlaybackTextTrack[]
  controls?: boolean
  lowLatency?: boolean
}>(), {
  poster: '',
  title: 'ویدیو',
  autoplay: false,
  startAtPercent: 0,
  quality: 'auto',
  subtitleTracks: () => [],
  controls: true,
  lowLatency: false,
})
const emit = defineEmits<{
  play: [progressPercent: number]
  pause: [progressPercent: number]
  progress: [progressPercent: number]
  position: [progressPercent: number]
  complete: [progressPercent: number]
  ready: [durationSeconds: number]
  playbackPlay: [snapshot: PlaybackSnapshot]
  playbackPause: [snapshot: PlaybackSnapshot]
  playbackSeek: [snapshot: PlaybackSnapshot]
}>()

const video = useTemplateRef<HTMLVideoElement>('video')
const loading = ref(true)
const errorMessage = ref('')
let hls: Hls | null = null
let trackingReady = false
let lastProgressBucket = 0
let lastPosition = -1
let resumeApplied = false
let readyEmitted = false
let applyingRemotePlayback = false
let remoteRateResetTimer: ReturnType<typeof setTimeout> | undefined

function destroyPlayer() {
  trackingReady = false
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
  if (!video.value?.duration || !Number.isFinite(video.value.duration)) return 0
  return Math.round((video.value.currentTime / video.value.duration) * 100)
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

function handlePlay() {
  if (trackingReady) emit('play', currentProgress())
  if (trackingReady && !applyingRemotePlayback) emit('playbackPlay', getPlaybackSnapshot())
}

function handlePause() {
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
  const seekThreshold = state.is_playing ? 1.25 : 0.12
  if (remoteRateResetTimer) clearTimeout(remoteRateResetTimer)
  remoteRateResetTimer = undefined
  applyingRemotePlayback = true
  try {
    if (Math.abs(drift) > seekThreshold) {
      element.currentTime = Math.max(0, Math.min(state.position_seconds, element.duration || state.position_seconds))
      element.playbackRate = targetRate
    } else if (state.is_playing && Math.abs(drift) > 0.12 && !element.paused) {
      // Correct small network jitter with a barely audible speed change instead
      // of seeking, which is much less distracting on mobile connections.
      const correction = Math.min(0.06, Math.abs(drift) * 0.12) * Math.sign(drift)
      element.playbackRate = Math.min(4, Math.max(0.25, targetRate + correction))
      if (remoteRateResetTimer) clearTimeout(remoteRateResetTimer)
      remoteRateResetTimer = setTimeout(() => {
        if (video.value === element && !applyingRemotePlayback) element.playbackRate = targetRate
      }, 5000)
    } else {
      element.playbackRate = targetRate
    }
    if (state.is_playing && element.paused) await element.play()
    else if (!state.is_playing && !element.paused) element.pause()
  } catch {
    // Autoplay policies may require a member gesture; the next sync retries.
  } finally {
    window.setTimeout(() => { applyingRemotePlayback = false }, 120)
  }
}

defineExpose({ applyRemotePlayback, getPlaybackSnapshot })

function handleTimeUpdate() {
  if (!trackingReady) return
  const progress = currentProgress()
  if (progress !== lastPosition) {
    lastPosition = progress
    emit('position', progress)
  }
  const bucket = Math.floor(progress / 10) * 10
  if (bucket >= 10 && bucket > lastProgressBucket && bucket < 100) {
    lastProgressBucket = bucket
    emit('progress', progress)
  }
}

function handleEnded() {
  if (trackingReady) emit('complete', 100)
}

async function safePlay() {
  if (!props.autoplay || !video.value) return
  try { await video.value.play() } catch { /* Browser autoplay policy keeps controls available. */ }
}

function setReady() {
  const element = video.value
  if (!element) return
  if (!resumeApplied && props.startAtPercent > 0 && Number.isFinite(element.duration) && element.duration > 0) {
    const resumePercent = Math.min(95, Math.max(0, props.startAtPercent))
    element.currentTime = element.duration * resumePercent / 100
    resumeApplied = true
    lastPosition = Math.round(resumePercent)
  }
  loading.value = false
  trackingReady = true
  if (!readyEmitted && Number.isFinite(element.duration)) {
    readyEmitted = true
    emit('ready', element.duration)
  }
  void safePlay()
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
  destroyPlayer()
  lastProgressBucket = 0
  lastPosition = -1
  resumeApplied = false
  readyEmitted = false
  errorMessage.value = ''
  loading.value = true
  const element = video.value
  if (!element || !props.src) {
    errorMessage.value = 'آدرس پخش در دسترس نیست.'
    loading.value = false
    return
  }

  if (element.canPlayType('application/vnd.apple.mpegurl')) {
    element.src = props.src
    element.load()
    return
  }

  const { default: HlsClass } = await import('hls.js')
  if (element !== video.value) return

  if (HlsClass.isSupported()) {
    hls = new HlsClass({
      enableWorker: true,
      lowLatencyMode: props.lowLatency,
      capLevelToPlayerSize: true,
      backBufferLength: props.lowLatency ? 10 : 30,
      maxBufferLength: props.lowLatency ? 12 : 30,
      maxMaxBufferLength: props.lowLatency ? 24 : 60,
    })
    hls.loadSource(props.src)
    hls.attachMedia(element)
    hls.on(HlsClass.Events.MANIFEST_PARSED, () => {
      applyQuality()
      setReady()
    })
    hls.on(HlsClass.Events.ERROR, (_, data) => {
      if (!data.fatal) return
      loading.value = false
      if (data.type === HlsClass.ErrorTypes.NETWORK_ERROR) {
        errorMessage.value = 'ارتباط با جریان ویدیو برقرار نشد. اتصال خود را بررسی کنید.'
      } else if (data.type === HlsClass.ErrorTypes.MEDIA_ERROR) {
        errorMessage.value = 'مرورگر نتوانست این ویدیو را پخش کند.'
      } else {
        errorMessage.value = 'خطایی در آماده‌سازی پخش رخ داد.'
      }
      hls?.destroy()
      hls = null
    })
    return
  }

  loading.value = false
  errorMessage.value = 'پخش HLS در این مرورگر پشتیبانی نمی‌شود.'
}

onMounted(() => { void loadSource() })
watch(() => props.src, () => { void loadSource() })
watch(() => props.quality, applyQuality)
watch(() => props.lowLatency, () => { void loadSource() })
onBeforeUnmount(destroyPlayer)
</script>

<template>
  <div class="relative aspect-video overflow-hidden rounded-xl bg-black shadow-2xl ring-1 ring-white/10 sm:rounded-2xl">
    <video ref="video" class="h-full w-full object-contain" :poster="poster" :controls="controls" controlslist="nodownload" playsinline preload="metadata" :aria-label="`پخش ${title}`" @loadedmetadata="setReady" @canplay="setReady" @waiting="loading = true" @playing="loading = false" @play="handlePlay" @pause="handlePause" @seeked="handleSeeked" @timeupdate="handleTimeUpdate" @ended="handleEnded" @error="errorMessage = 'بارگذاری فایل ویدیو ممکن نشد.'; loading = false">
      <track v-for="track in subtitleTracks" :key="track.id" kind="subtitles" :label="track.label" :srclang="track.language" :src="track.src" :default="track.default">
    </video>
    <div class="pointer-events-none absolute right-3 top-3 flex items-center gap-1.5 rounded-lg bg-black/80 px-2 py-1 text-[10px] font-bold text-slate-300 sm:right-4 sm:top-4">
      <span class="h-1.5 w-1.5 rounded-full bg-success" />
      HLS · {{ quality === 'auto' ? 'AUTO' : quality }}
    </div>
    <div v-if="loading && !errorMessage" class="pointer-events-none absolute inset-0 grid place-items-center bg-black/45 text-white">
      <div class="text-center"><span class="mx-auto block h-10 w-10 animate-spin rounded-full border-2 border-white/25 border-t-primary-500" /><p class="mt-3 text-sm font-bold">در حال آماده‌سازی پخش...</p></div>
    </div>
    <div v-if="errorMessage" class="absolute inset-0 grid place-items-center bg-slate-950/90 p-3 text-center text-white sm:p-6">
      <div><span class="mx-auto hidden size-12 place-items-center rounded-2xl bg-error/15 text-error sm:grid"><CinematicIcon name="alert-triangle" class="size-6" /></span><p class="font-black sm:mt-4">پخش ویدیو ممکن نشد</p><p class="mt-1 line-clamp-2 max-w-md text-xs leading-5 text-muted sm:text-sm sm:leading-6">{{ errorMessage }}</p><button type="button" class="mt-3 min-h-11 rounded-xl bg-white/10 px-4 text-xs font-black ring-1 ring-white/15 hover:bg-white/20 sm:mt-5 sm:text-sm" @click="loadSource"><CinematicIcon name="refresh" class="ml-1 inline size-4" />تلاش دوباره</button></div>
    </div>
  </div>
</template>
