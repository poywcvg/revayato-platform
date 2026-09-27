/**
 * Fragmented-MP4 writing for the in-browser remuxer.
 *
 * Each track gets its own init segment and its own stream of moof+mdat
 * fragments, because Media Source wants one SourceBuffer per track anyway and
 * that keeps the muxing free of any cross-track interleaving.
 *
 * Timing is where MKV→MP4 gets subtle:
 *  - MKV stores only presentation times. MP4 needs decode times too, so each
 *    video fragment (one GOP) takes its sorted presentation times as decode
 *    times, pulled back by the stream's reorder delay so no frame is decoded
 *    after it is shown.
 *  - MKV times are rounded to the millisecond. Played back as-is, audio frames
 *    would jitter by a sample or forty and click, so audio gets continuous
 *    synthetic times at its own sample rate, re-anchored only when the file
 *    genuinely jumps.
 *
 * Free of DOM and runtime imports, like `mkv.ts`.
 */

import type { MkvFrame, MkvTrack } from './mkv'

export interface Fmp4Track {
  /** MP4 track_ID. */
  id: number
  kind: 'video' | 'audio'
  /** Matroska track number this was built from. */
  source: number
  timescale: number
  /** RFC 6381 codec string, e.g. avc1.64001f / mp4a.40.2. */
  codec: string
  /** Full MIME type for MediaSource.isTypeSupported / addSourceBuffer. */
  mime: string
  init: Uint8Array
  /** Samples per audio frame (0 for video). */
  frameSamples: number
}

export class Fmp4Error extends Error {
  code: string
  constructor(code: string, message?: string) {
    super(message || code)
    this.code = code
  }
}

// ---------------------------------------------------------------------------
// Box writing

const encoder = new TextEncoder()

function concat(parts: readonly Uint8Array[]): Uint8Array {
  let length = 0
  for (const part of parts) length += part.length
  const out = new Uint8Array(length)
  let offset = 0
  for (const part of parts) {
    out.set(part, offset)
    offset += part.length
  }
  return out
}

function u8(value: number) {
  return Uint8Array.of(value & 0xFF)
}
function u16(value: number) {
  return Uint8Array.of((value >>> 8) & 0xFF, value & 0xFF)
}
function u24(value: number) {
  return Uint8Array.of((value >>> 16) & 0xFF, (value >>> 8) & 0xFF, value & 0xFF)
}
function u32(value: number) {
  const out = new Uint8Array(4)
  new DataView(out.buffer).setUint32(0, value >>> 0)
  return out
}
function i32(value: number) {
  const out = new Uint8Array(4)
  new DataView(out.buffer).setInt32(0, value | 0)
  return out
}
function u64(value: number) {
  const out = new Uint8Array(8)
  const view = new DataView(out.buffer)
  view.setUint32(0, Math.floor(value / 2 ** 32))
  view.setUint32(4, value >>> 0)
  return out
}
function zeros(n: number) {
  return new Uint8Array(n)
}
function fourcc(type: string) {
  return encoder.encode(type)
}

function box(type: string, ...parts: Uint8Array[]): Uint8Array {
  const body = concat(parts)
  return concat([u32(body.length + 8), fourcc(type), body])
}

function fullBox(type: string, version: number, flags: number, ...parts: Uint8Array[]): Uint8Array {
  return box(type, u8(version), u24(flags), ...parts)
}

const MATRIX = concat([
  u32(0x00010000), u32(0), u32(0),
  u32(0), u32(0x00010000), u32(0),
  u32(0), u32(0), u32(0x40000000),
])

// ---------------------------------------------------------------------------
// Codec configuration

function hex2(value: number) {
  return value.toString(16).padStart(2, '0')
}

function reverseBits32(value: number) {
  let out = 0
  for (let i = 0; i < 32; i++) {
    out = (out << 1) | ((value >>> i) & 1)
  }
  return out >>> 0
}

function avcCodec(avcC: Uint8Array) {
  return `avc1.${hex2(avcC[1]!)}${hex2(avcC[2]!)}${hex2(avcC[3]!)}`
}

function hevcCodec(hvcC: Uint8Array) {
  const b1 = hvcC[1]!
  const space = ['', 'A', 'B', 'C'][b1 >> 6] || ''
  const tier = (b1 & 0x20) ? 'H' : 'L'
  const profile = b1 & 0x1F
  const compat = reverseBits32(((hvcC[2]! << 24) | (hvcC[3]! << 16) | (hvcC[4]! << 8) | hvcC[5]!) >>> 0)
  const level = hvcC[12]!
  const constraints: string[] = []
  for (let i = 6; i < 12; i++) constraints.push(hex2(hvcC[i]!).toUpperCase())
  while (constraints.length && constraints[constraints.length - 1] === '00') constraints.pop()
  return [`hvc1.${space}${profile}`, compat.toString(16).toUpperCase(), `${tier}${level}`, ...constraints].join('.')
}

function visualSampleEntry(type: string, track: MkvTrack, config: Uint8Array): Uint8Array {
  const parts = [
    zeros(6), u16(1), // reserved, data_reference_index
    u16(0), u16(0), zeros(12), // pre_defined, reserved, pre_defined
    u16(track.width), u16(track.height),
    u32(0x00480000), u32(0x00480000), // 72 dpi
    u32(0), u16(1), // reserved, frame_count
    zeros(32), // compressorname
    u16(0x0018), u16(0xFFFF),
    config,
  ]
  const dw = track.displayWidth || track.width
  const dh = track.displayHeight || track.height
  if (dw && dh && track.width && track.height && dw * track.height !== dh * track.width) {
    // Non-square pixels (anamorphic DVD rips): tell the decoder the display shape.
    let h = dw * track.height
    let v = dh * track.width
    const gcd = (a: number, b: number): number => (b ? gcd(b, a % b) : a)
    const g = gcd(h, v) || 1
    h /= g
    v /= g
    parts.push(box('pasp', u32(h), u32(v)))
  }
  return box(type, ...parts)
}

const AAC_RATES = [96000, 88200, 64000, 48000, 44100, 32000, 24000, 22050, 16000, 12000, 11025, 8000, 7350]

function synthAsc(track: MkvTrack): Uint8Array {
  const id = track.codecId.toUpperCase()
  const aot = id.includes('/MAIN') ? 1 : id.includes('/SSR') ? 3 : 2
  let index = AAC_RATES.indexOf(track.sampleRate)
  if (index < 0) index = 3
  const channels = Math.min(7, Math.max(1, track.channels || 2))
  return Uint8Array.of((aot << 3) | (index >> 1), ((index & 1) << 7) | (channels << 3))
}

function aacObjectType(asc: Uint8Array) {
  let aot = asc[0]! >> 3
  if (aot === 31) aot = 32 + (((asc[0]! & 7) << 3) | (asc[1]! >> 5))
  return aot
}

function esds(objectType: number, dsi: Uint8Array | null): Uint8Array {
  const decoderSpecific = dsi ? concat([u8(0x05), u8(dsi.length), dsi]) : new Uint8Array(0)
  const decoderConfig = concat([
    u8(0x04), u8(13 + decoderSpecific.length),
    u8(objectType), u8(0x15), // audio stream
    u24(0), u32(0), u32(0), // bufferSizeDB, maxBitrate, avgBitrate
    decoderSpecific,
  ])
  const sl = Uint8Array.of(0x06, 0x01, 0x02)
  const es = concat([u8(0x03), u8(3 + decoderConfig.length + sl.length), u16(0), u8(0), decoderConfig, sl])
  return fullBox('esds', 0, 0, es)
}

function audioSampleEntry(type: string, channels: number, sampleRate: number, config: Uint8Array): Uint8Array {
  return box(
    type,
    zeros(6), u16(1),
    zeros(8), // version, revision, vendor
    u16(channels), u16(16),
    u16(0), u16(0),
    u32((sampleRate & 0xFFFF) * 0x10000),
    config,
  )
}

class Bits {
  private pos = 0
  private data: Uint8Array
  constructor(data: Uint8Array) {
    this.data = data
  }

  read(n: number) {
    let value = 0
    for (let i = 0; i < n; i++) {
      const byte = this.data[this.pos >> 3] ?? 0
      value = (value << 1) | ((byte >> (7 - (this.pos & 7))) & 1)
      this.pos++
    }
    return value
  }
}

/** Samples in one AC-3 / E-AC-3 / MP3 frame, from its own header. */
export function audioFrameSamples(codecId: string, frame: Uint8Array | null): number {
  if (codecId.startsWith('A_AAC')) return 1024
  if (codecId === 'A_AC3') return 1536
  if (codecId === 'A_EAC3') {
    if (!frame || frame.length < 5) return 1536
    const fscod = frame[4]! >> 6
    const numblkscod = (frame[4]! >> 4) & 3
    return (fscod === 3 ? 6 : [1, 2, 3, 6][numblkscod]!) * 256
  }
  if (codecId === 'A_MPEG/L3') {
    if (!frame || frame.length < 2) return 1152
    const version = (frame[1]! >> 3) & 3 // 3 = MPEG-1
    return version === 3 ? 1152 : 576
  }
  return 1024
}

function ac3Config(frame: Uint8Array) {
  if (frame.length < 7 || frame[0] !== 0x0B || frame[1] !== 0x77) throw new Fmp4Error('bad_ac3')
  const bits = new Bits(frame.subarray(4))
  const fscod = bits.read(2)
  const frmsizecod = bits.read(6)
  const bsid = bits.read(5)
  const bsmod = bits.read(3)
  const acmod = bits.read(3)
  if ((acmod & 1) && acmod !== 1) bits.read(2)
  if (acmod & 4) bits.read(2)
  if (acmod === 2) bits.read(2)
  const lfeon = bits.read(1)
  const packed = (fscod << 22) | (bsid << 17) | (bsmod << 14) | (acmod << 11) | (lfeon << 10) | ((frmsizecod >> 1) << 5)
  const sampleRate = [48000, 44100, 32000][fscod] || 48000
  const channels = [2, 1, 2, 3, 3, 4, 4, 5][acmod]! + lfeon
  return { box: box('dac3', u24(packed)), sampleRate, channels }
}

function eac3Config(frame: Uint8Array) {
  if (frame.length < 6 || frame[0] !== 0x0B || frame[1] !== 0x77) throw new Fmp4Error('bad_eac3')
  const bits = new Bits(frame.subarray(2))
  bits.read(2) // strmtyp
  bits.read(3) // substreamid
  const frmsiz = bits.read(11)
  const fscod = bits.read(2)
  const numblkscod = bits.read(2)
  const acmod = bits.read(3)
  const lfeon = bits.read(1)
  const bsid = bits.read(5)
  const sampleRate = fscod === 3 ? [24000, 22050, 16000][numblkscod] || 24000 : [48000, 44100, 32000][fscod] || 48000
  const blocks = fscod === 3 ? 6 : [1, 2, 3, 6][numblkscod]!
  const bytes = (frmsiz + 1) * 2
  const kbps = Math.round(bytes * 8 * sampleRate / (blocks * 256) / 1000)
  const dec3 = concat([
    u16(((kbps & 0x1FFF) << 3) | 0), // data_rate, num_ind_sub = 0 (one substream)
    u8(((fscod === 3 ? 0 : fscod) << 6) | (bsid << 1)),
    u8((acmod << 1) | lfeon), // asvc = 0, bsmod = 0
    u8(0), // num_dep_sub = 0
  ])
  const channels = [2, 1, 2, 3, 3, 4, 4, 5][acmod]! + lfeon
  return { box: box('dec3', dec3), sampleRate, channels }
}

export function codecNeedsFirstFrame(track: MkvTrack) {
  return track.codecId === 'A_AC3' || track.codecId === 'A_EAC3'
}

/**
 * Describe a Matroska track as an MP4 track, or throw Fmp4Error('unsupported_codec').
 * AC-3/E-AC-3 need their first frame, since only it carries the channel layout.
 */
export function buildTrack(track: MkvTrack, mp4Id: number, firstFrame: Uint8Array | null = null): Fmp4Track {
  if (track.unsupportedEncoding) throw new Fmp4Error('unsupported_encoding')
  const codecId = track.codecId
  let entry: Uint8Array
  let codec: string
  let timescale: number
  let frameSamples = 0
  let kind: 'video' | 'audio'

  if (codecId === 'V_MPEG4/ISO/AVC') {
    const cp = track.codecPrivate
    if (!cp || cp.length < 7 || cp[0] !== 1) throw new Fmp4Error('unsupported_codec', 'avc without avcC')
    kind = 'video'
    codec = avcCodec(cp)
    entry = visualSampleEntry('avc1', track, box('avcC', cp))
    timescale = 90000
  }
  else if (codecId === 'V_MPEGH/ISO/HEVC') {
    const cp = track.codecPrivate
    if (!cp || cp.length < 23) throw new Fmp4Error('unsupported_codec', 'hevc without hvcC')
    kind = 'video'
    codec = hevcCodec(cp)
    entry = visualSampleEntry('hvc1', track, box('hvcC', cp))
    timescale = 90000
  }
  else if (codecId.startsWith('A_AAC')) {
    kind = 'audio'
    const asc = track.codecPrivate && track.codecPrivate.length >= 2 ? track.codecPrivate : synthAsc(track)
    codec = `mp4a.40.${aacObjectType(asc)}`
    timescale = track.sampleRate || 48000
    frameSamples = 1024
    entry = audioSampleEntry('mp4a', Math.max(1, track.channels || 2), timescale, esds(0x40, asc))
  }
  else if (codecId === 'A_AC3' || codecId === 'A_EAC3') {
    if (!firstFrame) throw new Fmp4Error('needs_frame')
    kind = 'audio'
    const config = codecId === 'A_AC3' ? ac3Config(firstFrame) : eac3Config(firstFrame)
    codec = codecId === 'A_AC3' ? 'ac-3' : 'ec-3'
    timescale = config.sampleRate
    frameSamples = audioFrameSamples(codecId, firstFrame)
    entry = audioSampleEntry(codec, 2, config.sampleRate, config.box)
  }
  else if (codecId === 'A_MPEG/L3') {
    kind = 'audio'
    codec = 'mp4a.6B'
    timescale = track.sampleRate || 44100
    frameSamples = audioFrameSamples(codecId, firstFrame)
    entry = audioSampleEntry('mp4a', Math.max(1, track.channels || 2), timescale, esds(0x6B, null))
  }
  else {
    throw new Fmp4Error('unsupported_codec', codecId)
  }

  const init = buildInit(mp4Id, kind, timescale, track, entry)
  return {
    id: mp4Id,
    kind,
    source: track.number,
    timescale,
    codec,
    mime: `${kind}/mp4; codecs="${codec}"`,
    init,
    frameSamples,
  }
}

function buildInit(id: number, kind: 'video' | 'audio', timescale: number, track: MkvTrack, entry: Uint8Array): Uint8Array {
  const video = kind === 'video'
  const width = video ? (track.displayWidth || track.width) : 0
  const height = video ? (track.displayHeight || track.height) : 0
  const ftyp = box('ftyp', fourcc('isom'), u32(0x200), fourcc('isom'), fourcc('iso6'), fourcc('mp41'))
  const mvhd = fullBox(
    'mvhd', 0, 0,
    u32(0), u32(0), u32(1000), u32(0),
    u32(0x00010000), u16(0x0100), zeros(10),
    MATRIX, zeros(24), u32(id + 1),
  )
  const tkhd = fullBox(
    'tkhd', 0, 3,
    u32(0), u32(0), u32(id), u32(0), u32(0), zeros(8),
    u16(0), u16(0), u16(video ? 0 : 0x0100), u16(0),
    MATRIX, u32(width * 0x10000), u32(height * 0x10000),
  )
  const mdhd = fullBox('mdhd', 0, 0, u32(0), u32(0), u32(timescale), u32(0), u16(0x55C4), u16(0))
  const hdlr = fullBox(
    'hdlr', 0, 0,
    u32(0), fourcc(video ? 'vide' : 'soun'), zeros(12),
    encoder.encode(video ? 'VideoHandler\0' : 'SoundHandler\0'),
  )
  const header = video ? fullBox('vmhd', 0, 1, zeros(8)) : fullBox('smhd', 0, 0, zeros(4))
  const dinf = box('dinf', fullBox('dref', 0, 0, u32(1), fullBox('url ', 0, 1)))
  const stbl = box(
    'stbl',
    fullBox('stsd', 0, 0, u32(1), entry),
    fullBox('stts', 0, 0, u32(0)),
    fullBox('stsc', 0, 0, u32(0)),
    fullBox('stsz', 0, 0, u32(0), u32(0)),
    fullBox('stco', 0, 0, u32(0)),
  )
  const trak = box('trak', tkhd, box('mdia', mdhd, hdlr, box('minf', header, dinf, stbl)))
  const mvex = box('mvex', fullBox('trex', 0, 0, u32(id), u32(1), u32(0), u32(0), u32(0)))
  return concat([ftyp, box('moov', mvhd, trak, mvex)])
}

// ---------------------------------------------------------------------------
// Fragments

interface Sample {
  duration: number
  size: number
  flags: number
  cto: number
}

const FLAGS_SYNC = 0x02000000
const FLAGS_NON_SYNC = 0x01010000

function buildFragment(trackId: number, sequence: number, baseDts: number, samples: readonly Sample[], payload: readonly Uint8Array[]): Uint8Array {
  const entries: Uint8Array[] = []
  for (const sample of samples) {
    entries.push(u32(sample.duration), u32(sample.size), u32(sample.flags), i32(sample.cto))
  }
  const trunBody = [u32(samples.length), i32(0), ...entries]
  const build = (dataOffset: number) => {
    trunBody[1] = i32(dataOffset)
    const trun = fullBox('trun', 1, 0x000F01, ...trunBody)
    const traf = box(
      'traf',
      fullBox('tfhd', 0, 0x020000, u32(trackId)),
      fullBox('tfdt', 1, 0, u64(baseDts)),
      trun,
    )
    return box('moof', fullBox('mfhd', 0, 0, u32(sequence)), traf)
  }
  const sizing = build(0)
  const moof = build(sizing.length + 8)
  const data = concat(payload)
  return concat([moof, u32(data.length + 8), fourcc('mdat'), data])
}

export interface Fmp4Fragment {
  data: Uint8Array
  /** Seconds covered, in presentation time. */
  start: number
  end: number
}

interface PendingVideo {
  pts: number
  key: boolean
  data: Uint8Array
}

/**
 * Collects video frames and emits one fragment per GOP, cut at keyframes so
 * every fragment is independently decodable — which is what lets a seek, an
 * eviction or a restart begin at any fragment.
 */
export class VideoFragmenter {
  private track: Fmp4Track
  private toTicks: number
  private frameTicks: number
  private pending: PendingVideo[] = []
  private sequence = 1
  private reorderDelay = 0
  private lastDts = -1
  private waitingForKey = true

  constructor(track: Fmp4Track, timecodeScale: number, defaultDurationNs: number) {
    this.track = track
    this.toTicks = timecodeScale * track.timescale / 1e9
    this.frameTicks = defaultDurationNs > 0 ? Math.round(defaultDurationNs * track.timescale / 1e9) : 0
  }

  /** Forget decode history — after a seek the next fragment starts a new run. */
  reset() {
    this.pending = []
    this.lastDts = -1
    this.waitingForKey = true
  }

  push(frame: MkvFrame): Fmp4Fragment | null {
    if (this.waitingForKey) {
      if (!frame.keyframe) return null
      this.waitingForKey = false
    }
    let out: Fmp4Fragment | null = null
    if (frame.keyframe && this.pending.length) out = this.flush()
    this.pending.push({ pts: Math.round(frame.time * this.toTicks), key: frame.keyframe, data: frame.data })
    return out
  }

  flush(): Fmp4Fragment | null {
    const frames = this.pending
    if (!frames.length) return null
    this.pending = []
    const sorted = frames.map(frame => frame.pts).sort((a, b) => a - b)
    let delay = 0
    for (let i = 0; i < frames.length; i++) delay = Math.max(delay, sorted[i]! - frames[i]!.pts)
    if (delay > this.reorderDelay) this.reorderDelay = delay
    if (!this.frameTicks && sorted.length > 1) {
      const gaps: number[] = []
      for (let i = 1; i < sorted.length; i++) gaps.push(sorted[i]! - sorted[i - 1]!)
      gaps.sort((a, b) => a - b)
      this.frameTicks = gaps[gaps.length >> 1]! || 3754
    }
    const frameTicks = this.frameTicks || 3754
    const dts: number[] = []
    let prev = this.lastDts
    for (let i = 0; i < frames.length; i++) {
      let value = sorted[i]! - this.reorderDelay
      if (value <= prev) value = prev + 1
      dts.push(value)
      prev = value
    }
    this.lastDts = prev
    const samples: Sample[] = frames.map((frame, i) => ({
      duration: i + 1 < frames.length ? dts[i + 1]! - dts[i]! : frameTicks,
      size: frame.data.length,
      flags: frame.key ? FLAGS_SYNC : FLAGS_NON_SYNC,
      cto: frame.pts - dts[i]!,
    }))
    const data = buildFragment(this.track.id, this.sequence++, dts[0]!, samples, frames.map(frame => frame.data))
    return {
      data,
      start: sorted[0]! / this.track.timescale,
      end: (sorted[sorted.length - 1]! + frameTicks) / this.track.timescale,
    }
  }
}

/**
 * Collects audio frames into fragments of about a second on a continuous,
 * sample-exact clock (see the module comment for why not the file's own).
 */
export class AudioFragmenter {
  private track: Fmp4Track
  private toTicks: number
  private codecId: string
  private next = -1
  private base = 0
  private samples: Sample[] = []
  private payload: Uint8Array[] = []
  private sequence = 1
  private target: number

  constructor(track: Fmp4Track, timecodeScale: number, codecId: string, fragmentSeconds = 1) {
    this.track = track
    this.toTicks = timecodeScale * track.timescale / 1e9
    this.codecId = codecId
    this.target = Math.round(fragmentSeconds * track.timescale)
  }

  reset() {
    this.next = -1
    this.samples = []
    this.payload = []
  }

  push(frame: MkvFrame): Fmp4Fragment[] {
    const out: Fmp4Fragment[] = []
    const duration = this.track.frameSamples || audioFrameSamples(this.codecId, frame.data)
    const actual = Math.round(frame.time * this.toTicks) + frame.lace * duration
    // Re-anchor on a real jump (a gap or overlap in the file) — never on the
    // millisecond rounding that every Matroska timestamp carries.
    if (this.next < 0 || Math.abs(actual - this.next) > this.track.timescale * 0.1) {
      const flushed = this.flush()
      if (flushed) out.push(flushed)
      this.next = actual
      this.base = actual
    }
    this.samples.push({ duration, size: frame.data.length, flags: FLAGS_SYNC, cto: 0 })
    this.payload.push(frame.data)
    this.next += duration
    if (this.next - this.base >= this.target) {
      const flushed = this.flush()
      if (flushed) out.push(flushed)
    }
    return out
  }

  flush(): Fmp4Fragment | null {
    if (!this.samples.length) return null
    const base = this.base
    const data = buildFragment(this.track.id, this.sequence++, Math.max(0, base), this.samples, this.payload)
    this.samples = []
    this.payload = []
    this.base = this.next
    return { data, start: base / this.track.timescale, end: this.next / this.track.timescale }
  }
}
