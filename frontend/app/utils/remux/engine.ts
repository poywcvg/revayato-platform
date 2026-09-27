/**
 * Plays an MKV in browsers that cannot open MKV — every iOS browser, desktop
 * Safari, Firefox — by remuxing it to fragmented MP4 on the fly and feeding
 * Media Source (ManagedMediaSource on iOS 17.1+).
 *
 * The bytes come straight from the provider CDN with plain CORS range reads,
 * so the picture travels exactly the path it would for a native <video src>:
 * no server in the middle, no transcoding, no geo-blocked gateway.
 *
 * Media time equals film time (fragments carry the file's own timestamps), so
 * the player's clock, scrubber, resume and subtitle logic need no changes.
 */

import { cueBefore, findClusterIn, isPersianTextTrack, isTextSubtitleTrack, loadMkvCues, MkvClusterDemuxer, MkvError, mkvSubtitleText, parseMkvHead } from './mkv'
import type { ByteReader, MkvCue, MkvFrame, MkvHead, MkvTrack } from './mkv'
import { AudioFragmenter, buildTrack, codecNeedsFirstFrame, Fmp4Error, VideoFragmenter } from './fmp4'
import type { Fmp4Fragment, Fmp4Track } from './fmp4'
import { isRemuxCandidate, remuxSupported } from '~/utils/downloadMeta'

export class RemuxError extends Error {
  code: string
  constructor(code: string, message?: string) {
    super(message || code)
    this.code = code
  }
}

export type AudioPreference = 'fa' | 'original' | ''

export interface RemuxOptions {
  /** Film seconds to begin at (resume point). */
  startTime?: number
  /** 'fa' for the dubbed version, 'original' for the subtitled one. */
  audioPreference?: AudioPreference
  /** Called once, for failures after `startMkvRemux` resolved. */
  onFatal?: (error: RemuxError) => void
  onLog?: (message: string) => void
  /**
   * The file's own text subtitle tracks, once, as soon as the head is read
   * (before playback starts) — an empty list means the file has none.
   */
  onSubtitleTracks?: (tracks: EmbeddedSubtitleTrack[]) => void
  /**
   * Cues of those tracks as the stream reaches them, in film seconds. After a
   * seek the same stretch can be delivered again; the receiver de-duplicates.
   */
  onSubtitleCues?: (track: number, cues: EmbeddedSubtitleCue[]) => void
}

export interface EmbeddedSubtitleTrack {
  number: number
  language: string
  label: string
  persian: boolean
  isDefault: boolean
  forced: boolean
}

export interface EmbeddedSubtitleCue {
  start: number
  end: number
  text: string
}

export interface RemuxSession {
  destroy(): void
  readonly audioLanguage: string
  readonly videoCodec: string
  readonly audioCodec: string
  readonly subtitleTracks: readonly EmbeddedSubtitleTrack[]
}

/** Keep this much ahead of the playhead… */
const AHEAD_HIGH_SECONDS = 45
/** …resume downloading once it falls under this. */
const AHEAD_LOW_SECONDS = 30
/** Played-back media kept for small rewinds before it is released. */
const BACK_KEEP_SECONDS = 25
/** Give up on startup if the network delivers nothing for this long. */
const STARTUP_IDLE_MS = 15_000
const HEAD_TIMEOUT_MS = 15_000
const MAX_STREAM_RETRIES = 4
/** Shown this long when a subtitle block does not say how long it lasts. */
const DEFAULT_CUE_SECONDS = 4

type DecompressionStreamClass = new (format: 'deflate') => TransformStream<Uint8Array, Uint8Array>

function decompressionStream(): DecompressionStreamClass | null {
  return (globalThis as { DecompressionStream?: DecompressionStreamClass }).DecompressionStream || null
}

/** zlib-wrapped block → raw bytes (mkvmerge's default for text subtitles). */
async function inflate(data: Uint8Array): Promise<Uint8Array | null> {
  const Ctor = decompressionStream()
  if (!Ctor) return null
  try {
    const stream = new Blob([data as BlobPart]).stream().pipeThrough(new Ctor('deflate'))
    return new Uint8Array(await new Response(stream).arrayBuffer())
  }
  catch {
    return null
  }
}

function subtitleLabel(track: MkvTrack, persian: boolean): string {
  if (persian) return 'فارسی (داخل فایل)'
  const lang = (track.language || '').toLowerCase()
  const base = track.name || (lang === 'eng' || lang === 'en' ? 'English' : lang && lang !== 'und' ? lang : 'زیرنویس')
  return `${base} (داخل فایل)`
}

type AnyMediaSource = MediaSource & { streaming?: boolean }

interface MediaSourceClass {
  new (): AnyMediaSource
  isTypeSupported(type: string): boolean
}

function mediaSourceClass(): { ctor: MediaSourceClass, managed: boolean } | null {
  if (typeof window === 'undefined') return null
  const w = window as unknown as { ManagedMediaSource?: MediaSourceClass, MediaSource?: MediaSourceClass }
  if (w.ManagedMediaSource) return { ctor: w.ManagedMediaSource, managed: true }
  if (w.MediaSource) return { ctor: w.MediaSource, managed: false }
  return null
}

export { isRemuxCandidate, remuxSupported }

function isPersianTrack(track: MkvTrack) {
  return /^(per|fa|fas)(-|$)/i.test(track.language)
    || /farsi|persian|فارسی|دوبله|dubbed/i.test(track.name)
}

/** Audio tracks in the order worth trying for this version. */
export function rankAudioTracks(tracks: readonly MkvTrack[], preference: AudioPreference): MkvTrack[] {
  const audio = tracks.filter(track => track.type === 'audio' && track.enabled)
  const score = (track: MkvTrack) => {
    let value = track.isDefault ? 2 : 0
    if (preference === 'fa') value += isPersianTrack(track) ? 10 : 0
    else if (preference === 'original') value += isPersianTrack(track) ? -10 : 0
    return value
  }
  return audio
    .map((track, index) => ({ track, index }))
    .sort((a, b) => score(b.track) - score(a.track) || a.index - b.index)
    .map(item => item.track)
}

function delay(ms: number) {
  return new Promise<void>(resolve => setTimeout(resolve, ms))
}

function isAbort(error: unknown) {
  return (error as { name?: string } | null)?.name === 'AbortError'
}

// ---------------------------------------------------------------------------
// Byte access

class RangeSource implements ByteReader {
  url: string
  /** Set once a range request has been refused, e.g. by a CORS preflight. */
  linear = false
  constructor(url: string) {
    this.url = url
  }

  /**
   * Open the file at `offset`. With ranges this is one request; without (a
   * CDN or browser that refuses the Range header cross-origin) it reads from
   * the start and discards, which is slow for far seeks but still plays.
   */
  async open(offset: number, signal: AbortSignal): Promise<ReadableStreamDefaultReader<Uint8Array>> {
    if (!this.linear) {
      try {
        const response = await fetch(this.url, {
          headers: { Range: `bytes=${offset}-` },
          signal,
          credentials: 'omit',
          mode: 'cors',
        })
        if (response.status === 206 && response.body) return response.body.getReader()
        if (response.status === 200 && response.body) {
          if (offset === 0) return response.body.getReader()
          void response.body.cancel().catch(() => {})
          this.linear = true
        }
        else {
          void response.body?.cancel().catch(() => {})
          throw new RemuxError(response.status === 410 || response.status === 403 ? 'expired' : 'http_error', String(response.status))
        }
      }
      catch (error) {
        if (isAbort(error) || error instanceof RemuxError) throw error
        // A TypeError here is a refused preflight or a network fault. Try the
        // plain request once before calling it either.
        this.linear = true
      }
    }
    const response = await fetch(this.url, { signal, credentials: 'omit', mode: 'cors' })
    if (!response.ok || !response.body) {
      void response.body?.cancel().catch(() => {})
      throw new RemuxError(response.status === 410 || response.status === 403 ? 'expired' : 'http_error', String(response.status))
    }
    const reader = response.body.getReader()
    return offset > 0 ? skipBytes(reader, offset) : reader
  }

  async read(offset: number, length: number): Promise<Uint8Array> {
    const controller = new AbortController()
    const timer = setTimeout(() => controller.abort(), HEAD_TIMEOUT_MS)
    try {
      if (!this.linear) {
        try {
          const response = await fetch(this.url, {
            headers: { Range: `bytes=${offset}-${offset + length - 1}` },
            signal: controller.signal,
            credentials: 'omit',
            mode: 'cors',
          })
          if (response.status === 206) return new Uint8Array(await response.arrayBuffer()).subarray(0, length)
          if (response.status === 200 && response.body) {
            // The whole file came back: read what we need and hang up.
            this.linear = true
            return await collect(skipBytes(response.body.getReader(), offset), length, controller)
          }
          void response.body?.cancel().catch(() => {})
          throw new RemuxError(response.status === 410 || response.status === 403 ? 'expired' : 'http_error', String(response.status))
        }
        catch (error) {
          if (error instanceof RemuxError) throw error
          if (isAbort(error)) throw new RemuxError('timeout')
          this.linear = true
        }
      }
      const response = await fetch(this.url, { signal: controller.signal, credentials: 'omit', mode: 'cors' })
      if (!response.ok || !response.body) throw new RemuxError(response.status === 410 || response.status === 403 ? 'expired' : 'http_error', String(response.status))
      return await collect(skipBytes(response.body.getReader(), offset), length, controller)
    }
    catch (error) {
      if (error instanceof RemuxError) throw error
      if (isAbort(error)) throw new RemuxError('timeout')
      throw new RemuxError('fetch_failed', String((error as Error)?.message || error))
    }
    finally {
      clearTimeout(timer)
    }
  }
}

/** A reader that silently drops the first `count` bytes of `reader`. */
function skipBytes(reader: ReadableStreamDefaultReader<Uint8Array>, count: number): ReadableStreamDefaultReader<Uint8Array> {
  if (count <= 0) return reader
  let remaining = count
  const stream = new ReadableStream<Uint8Array>({
    async pull(controller) {
      for (;;) {
        const { done, value } = await reader.read()
        if (done) { controller.close(); return }
        if (remaining >= value.length) { remaining -= value.length; continue }
        controller.enqueue(remaining ? value.subarray(remaining) : value)
        remaining = 0
        return
      }
    },
    cancel(reason) {
      return reader.cancel(reason)
    },
  })
  return stream.getReader()
}

async function collect(reader: ReadableStreamDefaultReader<Uint8Array>, length: number, controller: AbortController) {
  const out = new Uint8Array(length)
  let filled = 0
  while (filled < length) {
    const { done, value } = await reader.read()
    if (done) break
    const take = Math.min(value.length, length - filled)
    out.set(value.subarray(0, take), filled)
    filled += take
  }
  void reader.cancel().catch(() => {})
  controller.abort()
  return out.subarray(0, filled)
}

// ---------------------------------------------------------------------------
// SourceBuffer queue

type LaneOp = { kind: 'append', data: Uint8Array, init?: boolean } | { kind: 'remove', start: number, end: number }

class Lane {
  sb: SourceBuffer
  queue: LaneOp[] = []
  queuedBytes = 0
  quotaUntil = 0
  private onQuota: () => void
  private onError: (error: unknown) => void

  constructor(sb: SourceBuffer, onQuota: () => void, onError: (error: unknown) => void) {
    this.sb = sb
    this.onQuota = onQuota
    this.onError = onError
    sb.addEventListener('updateend', () => this.kick())
  }

  append(data: Uint8Array, init = false) {
    this.queue.push({ kind: 'append', data, init })
    this.queuedBytes += data.length
    this.kick()
  }

  remove(start: number, end: number) {
    if (end - start < 1) return
    if (this.queue.some(op => op.kind === 'remove')) return
    // Ahead of pending appends: a full buffer only drains through removals.
    this.queue.unshift({ kind: 'remove', start, end })
    this.kick()
  }

  /** Drop queued media and cut off an append in flight (seek); init segments stay. */
  clear() {
    this.queue = this.queue.filter(op => op.kind === 'append' && op.init)
    this.queuedBytes = this.queue.reduce((sum, op) => sum + (op.kind === 'append' ? op.data.length : 0), 0)
    try {
      if (this.sb.updating) this.sb.abort()
    }
    catch { /* media source already closed */ }
  }

  get idle() {
    return !this.sb.updating && !this.queue.length
  }

  kick() {
    if (this.sb.updating || !this.queue.length) return
    const op = this.queue[0]!
    if (op.kind === 'append' && Date.now() < this.quotaUntil) return
    try {
      if (op.kind === 'append') this.sb.appendBuffer(op.data as BufferSource)
      else this.sb.remove(op.start, op.end)
      this.queue.shift()
      if (op.kind === 'append') this.queuedBytes -= op.data.length
    }
    catch (error) {
      if ((error as { name?: string })?.name === 'QuotaExceededError') {
        // Full: free the back-buffer and try again shortly.
        this.quotaUntil = Date.now() + 1000
        this.onQuota()
        setTimeout(() => this.kick(), 1100)
        return
      }
      this.onError(error)
    }
  }
}

function bufferedEndAt(ranges: TimeRanges | null | undefined, time: number): number {
  if (!ranges) return time
  for (let i = 0; i < ranges.length; i++) {
    if (time >= ranges.start(i) - 0.4 && time <= ranges.end(i) + 0.2) return ranges.end(i)
  }
  return time
}

function isBufferedAt(ranges: TimeRanges | null | undefined, time: number) {
  if (!ranges) return false
  for (let i = 0; i < ranges.length; i++) {
    if (time >= ranges.start(i) - 0.1 && time < ranges.end(i) - 0.3) return true
  }
  return false
}

// ---------------------------------------------------------------------------
// Engine

class MkvRemuxEngine implements RemuxSession {
  private video: HTMLVideoElement
  private url: string
  private options: RemuxOptions
  private source: RangeSource
  private head!: MkvHead
  private videoTrack!: MkvTrack
  private audioTrack: MkvTrack | null = null
  private videoMp4!: Fmp4Track
  private audioMp4: Fmp4Track | null = null
  private audioMime = ''
  private ms!: AnyMediaSource
  private managed = false
  private objectUrl = ''
  private videoLane!: Lane
  private audioLane: Lane | null = null
  private videoFrag!: VideoFragmenter
  private audioFrag: AudioFragmenter | null = null
  private cues: Promise<MkvCue[]> | null = null
  private fileSize = 0
  private generation = 0
  private controller: AbortController | null = null
  /** Film seconds the stream has reached (last frame demuxed). */
  private streamTime = 0
  /** Film seconds the stream in flight was opened for. */
  private streamFrom = 0
  private streamActive = false
  private streamEnded = false
  private retries = 0
  private destroyed = false
  private fatal = false
  private listeners: Array<[EventTarget, string, EventListener]> = []
  private firstAppend: { resolve: () => void, reject: (error: RemuxError) => void } | null = null
  private lastBytesAt = 0
  private textTracks = new Map<number, MkvTrack>()
  private pendingCues = new Map<number, EmbeddedSubtitleCue[]>()
  /** zlib blocks inflate asynchronously; this keeps their cues in file order. */
  private cueChain: Promise<void> = Promise.resolve()

  videoCodec = ''
  audioCodec = ''
  audioLanguage = ''
  subtitleTracks: EmbeddedSubtitleTrack[] = []

  constructor(video: HTMLVideoElement, url: string, options: RemuxOptions) {
    this.video = video
    this.url = url
    this.options = options
    this.source = new RangeSource(url)
  }

  private log(message: string) {
    this.options.onLog?.(`[remux] ${message}`)
  }

  async start(): Promise<void> {
    const ms = mediaSourceClass()
    if (!ms) throw new RemuxError('no_mse')

    try {
      this.head = await parseMkvHead(this.source)
    }
    catch (error) {
      if (error instanceof RemuxError) throw error
      if (error instanceof MkvError) throw new RemuxError(error.code)
      throw new RemuxError('head_failed', String((error as Error)?.message || error))
    }
    if (this.destroyed) throw new RemuxError('destroyed')

    const videoTrack = this.head.tracks.find(track => track.type === 'video' && track.enabled)
    if (!videoTrack) throw new RemuxError('no_video')
    try {
      this.videoMp4 = buildTrack(videoTrack, 1)
    }
    catch (error) {
      throw new RemuxError(error instanceof Fmp4Error ? error.code : 'video_codec', videoTrack.codecId)
    }
    if (!ms.ctor.isTypeSupported(this.videoMp4.mime)) throw new RemuxError('video_codec', this.videoMp4.mime)
    this.videoTrack = videoTrack
    this.videoCodec = this.videoMp4.codec

    for (const track of rankAudioTracks(this.head.tracks, this.options.audioPreference || '')) {
      let mime: string
      if (codecNeedsFirstFrame(track)) {
        mime = `audio/mp4; codecs="${track.codecId === 'A_AC3' ? 'ac-3' : 'ec-3'}"`
      }
      else {
        try {
          this.audioMp4 = buildTrack(track, 2)
          mime = this.audioMp4.mime
        }
        catch {
          this.audioMp4 = null
          continue
        }
      }
      if (ms.ctor.isTypeSupported(mime)) {
        this.audioTrack = track
        this.audioMime = mime
        break
      }
      this.audioMp4 = null
    }
    const hasAudio = this.head.tracks.some(track => track.type === 'audio')
    if (hasAudio && !this.audioTrack) throw new RemuxError('audio_codec')
    if (this.audioTrack) {
      this.audioLanguage = this.audioTrack.language
      this.audioCodec = this.audioMime.replace(/.*codecs="([^"]+)".*/, '$1')
    }
    this.log(`head ok: ${this.videoCodec} + ${this.audioCodec || 'no audio'} (${this.audioLanguage}), ${Math.round(this.head.durationSeconds)}s, cues ${this.head.cuesOffset >= 0}`)
    this.readSubtitleTracks()

    await this.attach(ms.ctor, ms.managed)
    if (this.destroyed) throw new RemuxError('destroyed')

    this.videoFrag = new VideoFragmenter(this.videoMp4, this.head.timecodeScale, this.videoTrack.defaultDurationNs)
    this.videoLane.append(this.videoMp4.init, true)
    if (this.audioMp4 && this.audioLane) {
      this.audioFrag = new AudioFragmenter(this.audioMp4, this.head.timecodeScale, this.audioTrack!.codecId)
      this.audioLane.append(this.audioMp4.init, true)
    }

    this.bindEvents()
    const firstData = new Promise<void>((resolve, reject) => {
      this.firstAppend = { resolve, reject }
    })
    const startTime = Math.max(0, this.options.startTime || 0)
    void this.restart(startTime)

    // Startup succeeds on the first appended video fragment; it fails only if
    // the network goes quiet, never merely because it is slow.
    this.lastBytesAt = Date.now()
    const watchdog = setInterval(() => {
      if (!this.firstAppend) return
      if (Date.now() - this.lastBytesAt > STARTUP_IDLE_MS) this.failStartup(new RemuxError('startup_stalled'))
    }, 1000)
    try {
      await firstData
    }
    finally {
      clearInterval(watchdog)
    }
  }

  private failStartup(error: RemuxError) {
    const pending = this.firstAppend
    this.firstAppend = null
    pending?.reject(error)
  }

  private async attach(ctor: MediaSourceClass, managed: boolean) {
    const ms = new ctor()
    this.ms = ms
    this.managed = managed
    const video = this.video
    if (managed) {
      // ManagedMediaSource only plays when AirPlay is off, or offers an
      // alternative source — which an MKV cannot be.
      (video as HTMLVideoElement & { disableRemotePlayback: boolean }).disableRemotePlayback = true
    }
    const opened = new Promise<void>((resolve, reject) => {
      const timer = setTimeout(() => reject(new RemuxError('sourceopen_timeout')), 8000)
      ms.addEventListener('sourceopen', () => {
        clearTimeout(timer)
        resolve()
      }, { once: true })
    })
    this.objectUrl = URL.createObjectURL(ms)
    video.src = this.objectUrl
    this.on(video, 'error', () => this.fail(new RemuxError('media_error', String(video.error?.code || ''))))
    await opened
    if (this.head.durationSeconds > 0) {
      try {
        ms.duration = this.head.durationSeconds
      }
      catch { /* duration grows by itself as media is appended */ }
    }
    const onQuota = () => this.evict(true)
    const onError = (error: unknown) => this.fail(new RemuxError('append_failed', String((error as Error)?.message || error)))
    this.videoLane = new Lane(ms.addSourceBuffer(this.videoMp4.mime), onQuota, onError)
    if (this.audioTrack) this.audioLane = new Lane(ms.addSourceBuffer(this.audioMime), onQuota, onError)
    this.videoLane.sb.addEventListener('updateend', () => this.afterAppend())
    this.audioLane?.sb.addEventListener('updateend', () => this.afterAppend())
    this.videoLane.sb.addEventListener('error', () => this.fail(new RemuxError('sourcebuffer_error')))
  }

  private on(target: EventTarget, type: string, handler: EventListener) {
    target.addEventListener(type, handler)
    this.listeners.push([target, type, handler])
  }

  private bindEvents() {
    const video = this.video
    this.on(video, 'seeking', () => this.onSeeking())
    this.on(video, 'waiting', () => this.onWaiting())
    this.on(video, 'timeupdate', () => this.evict(false))
    if (this.managed) {
      // The system says when it wants data (battery, memory pressure); the
      // pump reads `ms.streaming` directly, these just wake it up sooner.
      this.on(this.ms, 'startstreaming', () => this.log('startstreaming'))
      this.on(this.ms, 'endstreaming', () => this.log('endstreaming'))
    }
  }

  private afterAppend() {
    if (this.firstAppend && this.videoLane.sb.buffered.length) {
      const pending = this.firstAppend
      this.firstAppend = null
      pending.resolve()
    }
    this.maybeEndOfStream()
  }

  private get bufferedAhead(): number {
    const now = this.video.currentTime
    let end = bufferedEndAt(this.videoLane.sb.buffered, now)
    if (this.audioLane) end = Math.min(end, bufferedEndAt(this.audioLane.sb.buffered, now))
    return end - now
  }

  private isBuffered(time: number) {
    if (!isBufferedAt(this.videoLane.sb.buffered, time)) return false
    return !this.audioLane || isBufferedAt(this.audioLane.sb.buffered, time)
  }

  private onSeeking() {
    if (this.destroyed || this.fatal) return
    const target = this.video.currentTime
    if (this.isBuffered(target)) return
    // Inside, or just ahead of, what the stream in flight is delivering: let it arrive.
    if (this.streamActive && target >= this.streamFrom - 1 && target <= Math.max(this.streamFrom, this.streamTime) + 8) return
    this.log(`seek → ${target.toFixed(1)}s`)
    void this.restart(target)
  }

  private onWaiting() {
    if (this.destroyed || this.fatal || this.streamActive) return
    const now = this.video.currentTime
    if (this.isBuffered(now)) return
    if (this.streamEnded && this.head.durationSeconds && now >= this.head.durationSeconds - 1) return
    this.log(`stalled at ${now.toFixed(1)}s with no stream — restarting`)
    void this.restart(now)
  }

  private evict(urgent: boolean) {
    if (this.destroyed) return
    const now = this.video.currentTime
    const keep = urgent ? 4 : BACK_KEEP_SECONDS
    for (const lane of [this.videoLane, this.audioLane]) {
      if (!lane) continue
      const ranges = lane.sb.buffered
      if (!ranges.length) continue
      const start = ranges.start(0)
      if (now - start > keep + (urgent ? 0 : 10)) lane.remove(start, now - keep)
      // Media far ahead of the playhead that a backwards seek left behind.
      const last = ranges.length - 1
      if (ranges.start(last) > now + AHEAD_HIGH_SECONDS * 2) lane.remove(ranges.start(last), ranges.end(last))
    }
  }

  private maybeEndOfStream() {
    if (!this.streamEnded || this.destroyed) return
    if (!this.videoLane.idle || (this.audioLane && !this.audioLane.idle)) return
    if (this.ms.readyState !== 'open') return
    try {
      this.ms.endOfStream()
    }
    catch { /* a lane started updating again */ }
  }

  private async cueOffset(time: number): Promise<number> {
    if (time <= 0.5) return this.head.firstClusterOffset
    if (!this.source.linear && this.head.cuesOffset >= 0) {
      if (!this.cues) this.cues = loadMkvCues(this.source, this.head, this.videoTrack.number).catch(() => [])
      const cue = cueBefore(await this.cues, time)
      if (cue) return cue.offset
    }
    return this.estimateOffset(time)
  }

  /** No usable cues: interpolate by bitrate and refine on real cluster times. */
  private async estimateOffset(time: number): Promise<number> {
    const duration = this.head.durationSeconds
    if (!duration) return this.head.firstClusterOffset
    if (!this.fileSize) {
      try {
        const response = await fetch(this.url, { method: 'HEAD', credentials: 'omit', mode: 'cors' })
        this.fileSize = Number(response.headers.get('content-length')) || 0
      }
      catch { /* fall back to the first cluster */ }
    }
    if (!this.fileSize) return this.head.firstClusterOffset
    let lo = { time: 0, offset: this.head.firstClusterOffset }
    let hi = { time: duration, offset: this.fileSize }
    if (this.source.linear) {
      // Every probe would download from byte zero: take the plain estimate.
      return Math.floor(lo.offset + (hi.offset - lo.offset) * Math.max(0, time - 8) / duration)
    }
    for (let i = 0; i < 6; i++) {
      const fraction = (time - lo.time) / Math.max(0.001, hi.time - lo.time)
      const guess = Math.floor(lo.offset + (hi.offset - lo.offset) * Math.min(0.98, Math.max(0, fraction)))
      let found: { index: number, seconds: number } | null
      try {
        const window = await this.source.read(guess, 512 * 1024)
        found = findClusterIn(window, 0, this.head.timecodeScale)
      }
      catch {
        break
      }
      if (!found) break
      const offset = guess + found.index
      if (found.seconds <= time) {
        lo = { time: found.seconds, offset }
        if (time - found.seconds < 12) break
      }
      else {
        if (offset >= hi.offset) break
        hi = { time: found.seconds, offset }
      }
    }
    return lo.offset
  }

  /** (Re)start streaming so that `time` is covered, abandoning any stream in flight. */
  private async restart(time: number) {
    const generation = ++this.generation
    this.controller?.abort()
    this.controller = null
    this.videoLane.clear()
    this.audioLane?.clear()
    this.videoFrag.reset()
    this.audioFrag?.reset()
    this.streamEnded = false
    this.streamActive = true
    this.streamFrom = time
    this.streamTime = time
    let offset: number
    try {
      offset = await this.cueOffset(time)
    }
    catch {
      offset = this.head.firstClusterOffset
    }
    if (generation !== this.generation || this.destroyed) return
    await this.pump(offset, generation)
  }

  private async waitForRoom(generation: number) {
    for (;;) {
      if (generation !== this.generation || this.destroyed) return
      const ahead = this.bufferedAhead
      const backlog = this.videoLane.queuedBytes + (this.audioLane?.queuedBytes || 0)
      const quota = Date.now() < Math.max(this.videoLane.quotaUntil, this.audioLane?.quotaUntil || 0)
      const systemSaysStop = this.managed && this.ms.streaming === false && ahead > 10
      if (ahead < AHEAD_HIGH_SECONDS && backlog < 24 * 1024 * 1024 && !quota && !systemSaysStop) return
      // Wait for playback to eat into the buffer before reading more.
      while (generation === this.generation && !this.destroyed) {
        await delay(400)
        const now = this.bufferedAhead
        const stillQuota = Date.now() < Math.max(this.videoLane.quotaUntil, this.audioLane?.quotaUntil || 0)
        const stillStopped = this.managed && this.ms.streaming === false && now > 10
        const queue = this.videoLane.queuedBytes + (this.audioLane?.queuedBytes || 0)
        if (now < AHEAD_LOW_SECONDS && !stillQuota && !stillStopped && queue < 8 * 1024 * 1024) break
      }
    }
  }

  private async pump(offset: number, generation: number) {
    const controller = new AbortController()
    this.controller = controller
    const wanted = new Set<number>([this.videoTrack.number, ...this.textTracks.keys()])
    if (this.audioTrack) wanted.add(this.audioTrack.number)
    const demuxer = new MkvClusterDemuxer(this.head, wanted, offset)
    let reader: ReadableStreamDefaultReader<Uint8Array> | null = null
    const current = () => generation === this.generation && !this.destroyed
    try {
      reader = await this.source.open(offset, controller.signal)
      for (;;) {
        await this.waitForRoom(generation)
        if (!current()) break
        const { done, value } = await reader.read()
        if (!current()) break
        if (done) {
          const nearEnd = !this.head.durationSeconds || this.streamTime >= this.head.durationSeconds - 5
          if (!nearEnd) throw new RemuxError('stream_cut')
          this.finishStream()
          break
        }
        this.lastBytesAt = Date.now()
        for (const frame of demuxer.push(value)) {
          this.streamTime = frame.time * this.head.timecodeScale / 1e9
          const textTrack = this.textTracks.get(frame.track)
          if (textTrack) {
            this.pushSubtitle(textTrack, frame)
          }
          else if (frame.track === this.videoTrack.number) {
            const fragment = this.videoFrag.push(frame)
            if (fragment) this.appendVideo(fragment)
          }
          else if (this.audioTrack) {
            this.pushAudio(frame)
          }
        }
        if (this.textTracks.size) this.flushCues()
        this.retries = 0
      }
    }
    catch (error) {
      if (!current() || isAbort(error)) return
      const code = error instanceof RemuxError ? error.code : 'stream_failed'
      if (this.firstAppend) {
        this.failStartup(new RemuxError(code, String((error as Error)?.message || error)))
        return
      }
      if (code === 'expired' || this.retries >= MAX_STREAM_RETRIES) {
        this.fail(new RemuxError(code))
        return
      }
      this.retries++
      this.log(`stream error (${code}), retry ${this.retries}`)
      await delay(800 * this.retries)
      if (!current()) return
      const resumeAt = Math.max(this.video.currentTime, bufferedEndAt(this.videoLane.sb.buffered, this.video.currentTime) - 2)
      void this.restart(resumeAt)
      return
    }
    finally {
      if (current()) this.streamActive = false
      try {
        await reader?.cancel()
      }
      catch { /* already closed */ }
    }
  }

  private appendVideo(fragment: Fmp4Fragment) {
    this.videoLane.append(fragment.data)
  }

  private pushAudio(frame: Parameters<AudioFragmenter['push']>[0]) {
    if (!this.audioFrag) {
      // AC-3/E-AC-3: the init segment needs the first frame's header.
      try {
        this.audioMp4 = buildTrack(this.audioTrack!, 2, frame.data)
      }
      catch {
        return
      }
      this.audioFrag = new AudioFragmenter(this.audioMp4, this.head.timecodeScale, this.audioTrack!.codecId)
      this.audioLane?.append(this.audioMp4.init, true)
    }
    for (const fragment of this.audioFrag.push(frame)) this.audioLane?.append(fragment.data)
  }

  private readSubtitleTracks() {
    const canInflate = Boolean(decompressionStream())
    for (const track of this.head.tracks) {
      if (!isTextSubtitleTrack(track) || (track.zlib && !canInflate)) continue
      const persian = isPersianTextTrack(track)
      this.textTracks.set(track.number, track)
      this.subtitleTracks.push({
        number: track.number,
        language: persian ? 'fa' : track.language,
        label: subtitleLabel(track, persian),
        persian,
        isDefault: track.isDefault,
        forced: track.forced,
      })
    }
    if (this.subtitleTracks.length) this.log(`subtitles: ${this.subtitleTracks.map(track => `${track.number}:${track.language}`).join(', ')}`)
    try {
      this.options.onSubtitleTracks?.(this.subtitleTracks.slice())
    }
    catch { /* the player's problem, never the stream's */ }
  }

  private pushSubtitle(track: MkvTrack, frame: MkvFrame) {
    if (!this.options.onSubtitleCues) return
    const scale = this.head.timecodeScale / 1e9
    const start = frame.time * scale
    const end = frame.duration > 0 ? (frame.time + frame.duration) * scale : start + DEFAULT_CUE_SECONDS
    const add = (data: Uint8Array) => {
      const text = mkvSubtitleText(track.codecId, data)
      if (!text || !(end > start)) return
      let list = this.pendingCues.get(track.number)
      if (!list) this.pendingCues.set(track.number, list = [])
      list.push({ start, end, text })
    }
    if (!track.zlib) {
      add(frame.data)
      return
    }
    const data = frame.data
    this.cueChain = this.cueChain.then(async () => {
      const raw = await inflate(data)
      if (raw) add(raw)
    })
  }

  private flushCues() {
    this.cueChain = this.cueChain.then(() => {
      if (this.destroyed || !this.pendingCues.size) return
      const batches = [...this.pendingCues]
      this.pendingCues.clear()
      for (const [track, cues] of batches) {
        try {
          this.options.onSubtitleCues?.(track, cues)
        }
        catch { /* see readSubtitleTracks */ }
      }
    })
  }

  private finishStream() {
    const video = this.videoFrag.flush()
    if (video) this.appendVideo(video)
    const audio = this.audioFrag?.flush()
    if (audio) this.audioLane?.append(audio.data)
    this.streamEnded = true
    this.maybeEndOfStream()
  }

  private fail(error: RemuxError) {
    if (this.fatal || this.destroyed) return
    this.log(`fatal: ${error.code} ${error.message}`)
    if (this.firstAppend) {
      this.failStartup(error)
      return
    }
    this.fatal = true
    this.controller?.abort()
    this.options.onFatal?.(error)
  }

  destroy() {
    if (this.destroyed) return
    this.destroyed = true
    this.generation++
    this.controller?.abort()
    this.failStartup(new RemuxError('destroyed'))
    for (const [target, type, handler] of this.listeners) target.removeEventListener(type, handler)
    this.listeners = []
    if (this.objectUrl) {
      URL.revokeObjectURL(this.objectUrl)
      this.objectUrl = ''
    }
  }
}

/**
 * Attach a remuxed MKV to `video`. Resolves once the first video fragment is
 * buffered (playback can start); rejects — having detached nothing the caller
 * must undo beyond `video.src` — when this file or browser cannot be remuxed,
 * so the caller can fall back to native playback or the server gateway.
 */
export async function startMkvRemux(video: HTMLVideoElement, url: string, options: RemuxOptions = {}): Promise<RemuxSession> {
  const engine = new MkvRemuxEngine(video, url, options)
  try {
    await engine.start()
    return engine
  }
  catch (error) {
    engine.destroy()
    throw error instanceof RemuxError ? error : new RemuxError('failed', String((error as Error)?.message || error))
  }
}
