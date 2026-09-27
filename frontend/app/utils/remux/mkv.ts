/**
 * Matroska (MKV/WebM) reading for the in-browser remuxer.
 *
 * Almost the whole catalog is MKV, and Safari — every browser on iOS — cannot
 * open an MKV at all. The bytes inside are nearly always H.264/HEVC + AAC/AC-3,
 * which Safari decodes happily once they sit in an MP4 box instead. So the
 * player reads the MKV straight from the CDN, and this module pulls the frames
 * out; `fmp4.ts` puts them back into fragmented MP4 for Media Source.
 *
 * Deliberately free of DOM and runtime imports so it runs unchanged under Node
 * for tests against real catalog files.
 */

export const MKV_ID = {
  EBML: 0x1A45DFA3,
  DocType: 0x4282,
  Segment: 0x18538067,
  SeekHead: 0x114D9B74,
  Seek: 0x4DBB,
  SeekID: 0x53AB,
  SeekPosition: 0x53AC,
  Info: 0x1549A966,
  TimecodeScale: 0x2AD7B1,
  Duration: 0x4489,
  Tracks: 0x1654AE6B,
  TrackEntry: 0xAE,
  TrackNumber: 0xD7,
  TrackType: 0x83,
  CodecID: 0x86,
  CodecPrivate: 0x63A2,
  DefaultDuration: 0x23E383,
  Language: 0x22B59C,
  LanguageIETF: 0x22B59D,
  Name: 0x536E,
  FlagDefault: 0x88,
  FlagEnabled: 0xB9,
  FlagForced: 0x55AA,
  Video: 0xE0,
  PixelWidth: 0xB0,
  PixelHeight: 0xBA,
  DisplayWidth: 0x54B0,
  DisplayHeight: 0x54BA,
  DisplayUnit: 0x54B2,
  Audio: 0xE1,
  SamplingFrequency: 0xB5,
  OutputSamplingFrequency: 0x78B5,
  Channels: 0x9F,
  BitDepth: 0x6264,
  ContentEncodings: 0x6D80,
  ContentEncoding: 0x6240,
  ContentCompression: 0x5034,
  ContentCompAlgo: 0x4254,
  ContentCompSettings: 0x4255,
  ContentEncryption: 0x5035,
  Cues: 0x1C53BB6B,
  CuePoint: 0xBB,
  CueTime: 0xB3,
  CueTrackPositions: 0xB7,
  CueTrack: 0xF7,
  CueClusterPosition: 0xF1,
  Cluster: 0x1F43B675,
  Timecode: 0xE7,
  SimpleBlock: 0xA3,
  BlockGroup: 0xA0,
  Block: 0xA1,
  BlockDuration: 0x9B,
  ReferenceBlock: 0xFB,
  Void: 0xEC,
  CRC32: 0xBF,
  Chapters: 0x1043A770,
  Attachments: 0x1941A469,
  Tags: 0x1254C367,
} as const

/** Element IDs that may legitimately appear between frames and are simply skipped. */
const SKIPPABLE = new Set<number>([
  MKV_ID.Void, MKV_ID.CRC32, MKV_ID.Cues, MKV_ID.Tags, MKV_ID.SeekHead, MKV_ID.Info,
  MKV_ID.Tracks, MKV_ID.Chapters, MKV_ID.Attachments,
  0xA7, // Position
  0xAB, // PrevSize
  0xAF, // EncryptedBlock
  0x5854, // SilentTracks
])

/** No single frame is anywhere near this; a bigger size means we are reading garbage. */
const MAX_BLOCK_BYTES = 48 * 1024 * 1024

export class MkvError extends Error {
  code: string
  constructor(code: string, message?: string) {
    super(message || code)
    this.code = code
  }
}

export interface MkvTrack {
  number: number
  type: 'video' | 'audio' | 'subtitle' | 'other'
  codecId: string
  codecPrivate: Uint8Array | null
  /** Nanoseconds per frame, 0 when the file does not say. */
  defaultDurationNs: number
  language: string
  name: string
  isDefault: boolean
  enabled: boolean
  forced: boolean
  width: number
  height: number
  displayWidth: number
  displayHeight: number
  sampleRate: number
  outputSampleRate: number
  channels: number
  bitDepth: number
  /** Header-stripping compression: bytes to put back in front of every frame. */
  headerStrip: Uint8Array | null
  /** zlib/bzip/lzo compression or encryption — nothing we can undo in a browser. */
  unsupportedEncoding: boolean
  /**
   * The only encoding is zlib. Useless for audio/video, but mkvmerge zlibs text
   * subtitles by default and those are small enough to inflate per block.
   */
  zlib: boolean
}

export interface MkvHead {
  segmentStart: number
  timecodeScale: number
  durationSeconds: number
  tracks: MkvTrack[]
  /** Absolute byte offset of the Cues element, -1 when unknown. */
  cuesOffset: number
  firstClusterOffset: number
}

export interface MkvCue {
  /** Seconds. */
  time: number
  /** Absolute byte offset of the cluster. */
  offset: number
}

export interface ByteReader {
  /** Up to `length` bytes starting at `offset`; fewer only at end of file. */
  read(offset: number, length: number): Promise<Uint8Array>
}

// ---------------------------------------------------------------------------
// EBML primitives

export function vintLength(first: number): number {
  for (let i = 0; i < 8; i++) {
    if (first & (0x80 >> i)) return i + 1
  }
  return 0
}

/** Element ID (marker bits kept, as the spec writes them) or null when too short. */
export function readId(buf: Uint8Array, pos: number): { id: number, len: number } | null {
  if (pos >= buf.length) return null
  const len = vintLength(buf[pos]!)
  if (!len || len > 4) return { id: -1, len: 0 }
  if (pos + len > buf.length) return null
  let id = 0
  for (let i = 0; i < len; i++) id = id * 256 + buf[pos + i]!
  return { id, len }
}

/** Element size, -1 for "unknown", or null when too short. */
export function readSize(buf: Uint8Array, pos: number): { size: number, len: number } | null {
  if (pos >= buf.length) return null
  const first = buf[pos]!
  const len = vintLength(first)
  if (!len) return { size: -2, len: 0 }
  if (pos + len > buf.length) return null
  let value = first & (0xFF >> len)
  let allOnes = value === (0xFF >> len)
  for (let i = 1; i < len; i++) {
    const byte = buf[pos + i]!
    if (byte !== 0xFF) allOnes = false
    value = value * 256 + byte
  }
  return { size: allOnes ? -1 : value, len }
}

function readUint(buf: Uint8Array, pos: number, len: number): number {
  let value = 0
  for (let i = 0; i < len; i++) value = value * 256 + buf[pos + i]!
  return value
}

function readFloat(buf: Uint8Array, pos: number, len: number): number {
  const view = new DataView(buf.buffer, buf.byteOffset + pos, len)
  if (len === 4) return view.getFloat32(0)
  if (len === 8) return view.getFloat64(0)
  return 0
}

function readString(buf: Uint8Array, pos: number, len: number): string {
  let end = pos + len
  while (end > pos && buf[end - 1] === 0) end--
  return new TextDecoder().decode(buf.subarray(pos, end))
}

/** Walk the direct children of a fully-buffered master element. */
function eachChild(buf: Uint8Array, start: number, end: number, visit: (id: number, data: number, size: number) => void) {
  let pos = start
  while (pos < end) {
    const id = readId(buf, pos)
    if (!id || id.id < 0) return
    const size = readSize(buf, pos + id.len)
    if (!size || size.size < 0) return
    const data = pos + id.len + size.len
    if (data + size.size > end) return
    visit(id.id, data, size.size)
    pos = data + size.size
  }
}

// ---------------------------------------------------------------------------
// Header

class WindowedReader {
  private window: Uint8Array = new Uint8Array(0)
  private start = 0
  private reader: ByteReader
  constructor(reader: ByteReader) {
    this.reader = reader
  }

  /** A view of [offset, offset+length) — shorter only at end of file. */
  async bytes(offset: number, length: number, readAhead = 64 * 1024): Promise<Uint8Array> {
    const end = offset + length
    if (offset >= this.start && end <= this.start + this.window.length) {
      return this.window.subarray(offset - this.start, end - this.start)
    }
    this.window = await this.reader.read(offset, Math.max(length, readAhead))
    this.start = offset
    return this.window.subarray(0, Math.min(length, this.window.length))
  }
}

function parseTrack(buf: Uint8Array, start: number, end: number): MkvTrack {
  const track: MkvTrack = {
    number: 0,
    type: 'other',
    codecId: '',
    codecPrivate: null,
    defaultDurationNs: 0,
    language: 'eng',
    name: '',
    isDefault: true,
    enabled: true,
    forced: false,
    width: 0,
    height: 0,
    displayWidth: 0,
    displayHeight: 0,
    sampleRate: 8000,
    outputSampleRate: 0,
    channels: 1,
    bitDepth: 0,
    headerStrip: null,
    unsupportedEncoding: false,
    zlib: false,
  }
  let languageIetf = ''
  let encrypted = false
  eachChild(buf, start, end, (id, data, size) => {
    switch (id) {
      case MKV_ID.TrackNumber: track.number = readUint(buf, data, size); break
      case MKV_ID.TrackType: {
        const kind = readUint(buf, data, size)
        track.type = kind === 1 ? 'video' : kind === 2 ? 'audio' : kind === 17 ? 'subtitle' : 'other'
        break
      }
      case MKV_ID.CodecID: track.codecId = readString(buf, data, size); break
      case MKV_ID.CodecPrivate: track.codecPrivate = buf.slice(data, data + size); break
      case MKV_ID.DefaultDuration: track.defaultDurationNs = readUint(buf, data, size); break
      case MKV_ID.Language: track.language = readString(buf, data, size) || track.language; break
      case MKV_ID.LanguageIETF: languageIetf = readString(buf, data, size); break
      case MKV_ID.Name: track.name = readString(buf, data, size); break
      case MKV_ID.FlagDefault: track.isDefault = readUint(buf, data, size) !== 0; break
      case MKV_ID.FlagEnabled: track.enabled = readUint(buf, data, size) !== 0; break
      case MKV_ID.FlagForced: track.forced = readUint(buf, data, size) !== 0; break
      case MKV_ID.Video:
        eachChild(buf, data, data + size, (vid, vdata, vsize) => {
          if (vid === MKV_ID.PixelWidth) track.width = readUint(buf, vdata, vsize)
          else if (vid === MKV_ID.PixelHeight) track.height = readUint(buf, vdata, vsize)
          else if (vid === MKV_ID.DisplayWidth) track.displayWidth = readUint(buf, vdata, vsize)
          else if (vid === MKV_ID.DisplayHeight) track.displayHeight = readUint(buf, vdata, vsize)
        })
        break
      case MKV_ID.Audio:
        eachChild(buf, data, data + size, (aid, adata, asize) => {
          if (aid === MKV_ID.SamplingFrequency) track.sampleRate = Math.round(readFloat(buf, adata, asize))
          else if (aid === MKV_ID.OutputSamplingFrequency) track.outputSampleRate = Math.round(readFloat(buf, adata, asize))
          else if (aid === MKV_ID.Channels) track.channels = readUint(buf, adata, asize)
          else if (aid === MKV_ID.BitDepth) track.bitDepth = readUint(buf, adata, asize)
        })
        break
      case MKV_ID.ContentEncodings:
        eachChild(buf, data, data + size, (eid, edata, esize) => {
          if (eid !== MKV_ID.ContentEncoding) return
          eachChild(buf, edata, edata + esize, (cid, cdata, csize) => {
            if (cid === MKV_ID.ContentEncryption) {
              track.unsupportedEncoding = true
              encrypted = true
            }
            else if (cid === MKV_ID.ContentCompression) {
              let algo = 0 // zlib is the spec default
              let settings: Uint8Array | null = null
              eachChild(buf, cdata, cdata + csize, (kid, kdata, ksize) => {
                if (kid === MKV_ID.ContentCompAlgo) algo = readUint(buf, kdata, ksize)
                else if (kid === MKV_ID.ContentCompSettings) settings = buf.slice(kdata, kdata + ksize)
              })
              if (algo === 3 && settings) track.headerStrip = settings
              else {
                track.unsupportedEncoding = true
                if (algo === 0) track.zlib = true
              }
            }
          })
        })
        break
    }
  })
  if (encrypted) track.zlib = false
  if (languageIetf) track.language = languageIetf
  if (!track.displayWidth) track.displayWidth = track.width
  if (!track.displayHeight) track.displayHeight = track.height
  return track
}

/**
 * Read the EBML header, Info and Tracks, stopping at the first Cluster.
 * Usually a single 256 KB range covers all of it; big font Attachments are
 * jumped over without being downloaded.
 */
export async function parseMkvHead(reader: ByteReader): Promise<MkvHead> {
  const win = new WindowedReader(reader)
  const first = await win.bytes(0, 64, 256 * 1024)
  const ebml = readId(first, 0)
  if (!ebml || ebml.id !== MKV_ID.EBML) throw new MkvError('not_mkv')
  const ebmlSize = readSize(first, ebml.len)
  if (!ebmlSize || ebmlSize.size < 0) throw new MkvError('not_mkv')
  const ebmlData = ebml.len + ebmlSize.len
  const header = await win.bytes(0, ebmlData + ebmlSize.size)
  let docType = 'matroska'
  eachChild(header, ebmlData, ebmlData + ebmlSize.size, (id, data, size) => {
    if (id === MKV_ID.DocType) docType = readString(header, data, size)
  })
  if (docType !== 'matroska' && docType !== 'webm') throw new MkvError('not_mkv')

  let pos = ebmlData + ebmlSize.size
  const segHead = await win.bytes(pos, 12)
  const seg = readId(segHead, 0)
  if (!seg || seg.id !== MKV_ID.Segment) throw new MkvError('not_mkv')
  const segSize = readSize(segHead, seg.len)
  if (!segSize) throw new MkvError('not_mkv')
  const segmentStart = pos + seg.len + segSize.len
  pos = segmentStart

  const head: MkvHead = {
    segmentStart,
    timecodeScale: 1_000_000,
    durationSeconds: 0,
    tracks: [],
    cuesOffset: -1,
    firstClusterOffset: -1,
  }
  let rawDuration = 0
  let tracksOffset = -1
  let sawTracks = false

  const readMaster = async (at: number, visit: (buf: Uint8Array, start: number, end: number) => void) => {
    const hdr = await win.bytes(at, 12)
    const id = readId(hdr, 0)
    const size = id && id.id >= 0 ? readSize(hdr, id.len) : null
    if (!id || !size || size.size < 0 || size.size > 32 * 1024 * 1024) throw new MkvError('bad_header')
    const hlen = id.len + size.len
    const body = await win.bytes(at, hlen + size.size, hlen + size.size)
    if (body.length < hlen + size.size) throw new MkvError('truncated')
    visit(body, hlen, hlen + size.size)
    return id.id
  }

  for (let guard = 0; guard < 256; guard++) {
    const hdr = await win.bytes(pos, 12)
    if (hdr.length < 2) break
    const id = readId(hdr, 0)
    const size = id && id.id >= 0 ? readSize(hdr, id.len) : null
    if (!id || id.id < 0 || !size || size.size === -2) throw new MkvError('bad_header')
    if (id.id === MKV_ID.Cluster) {
      head.firstClusterOffset = pos
      break
    }
    if (size.size < 0) throw new MkvError('bad_header')
    const hlen = id.len + size.len
    if (id.id === MKV_ID.SeekHead) {
      await readMaster(pos, (buf, start, end) => {
        eachChild(buf, start, end, (sid, sdata, ssize) => {
          if (sid !== MKV_ID.Seek) return
          let target = 0
          let offset = -1
          eachChild(buf, sdata, sdata + ssize, (kid, kdata, ksize) => {
            if (kid === MKV_ID.SeekID) target = readUint(buf, kdata, ksize)
            else if (kid === MKV_ID.SeekPosition) offset = readUint(buf, kdata, ksize)
          })
          if (offset < 0) return
          if (target === MKV_ID.Cues) head.cuesOffset = segmentStart + offset
          else if (target === MKV_ID.Tracks) tracksOffset = segmentStart + offset
        })
      })
    }
    else if (id.id === MKV_ID.Info) {
      await readMaster(pos, (buf, start, end) => {
        eachChild(buf, start, end, (iid, idata, isize) => {
          if (iid === MKV_ID.TimecodeScale) head.timecodeScale = readUint(buf, idata, isize) || 1_000_000
          else if (iid === MKV_ID.Duration) rawDuration = readFloat(buf, idata, isize)
        })
      })
    }
    else if (id.id === MKV_ID.Tracks) {
      sawTracks = true
      await readMaster(pos, (buf, start, end) => {
        eachChild(buf, start, end, (tid, tdata, tsize) => {
          if (tid === MKV_ID.TrackEntry) head.tracks.push(parseTrack(buf, tdata, tdata + tsize))
        })
      })
    }
    else if (id.id === MKV_ID.Cues && head.cuesOffset < 0) {
      head.cuesOffset = pos
    }
    pos += hlen + size.size
  }

  if (!sawTracks && tracksOffset > 0) {
    await readMaster(tracksOffset, (buf, start, end) => {
      eachChild(buf, start, end, (tid, tdata, tsize) => {
        if (tid === MKV_ID.TrackEntry) head.tracks.push(parseTrack(buf, tdata, tdata + tsize))
      })
    })
  }
  if (head.firstClusterOffset < 0) throw new MkvError('no_clusters')
  if (!head.tracks.length) throw new MkvError('no_tracks')
  head.durationSeconds = rawDuration * head.timecodeScale / 1e9
  return head
}

/**
 * The seek index. Positions are made absolute and sorted by time; entries of
 * `preferTrack` (the video track) win, since those are the keyframes we can
 * actually start decoding from.
 */
export async function loadMkvCues(reader: ByteReader, head: MkvHead, preferTrack: number): Promise<MkvCue[]> {
  if (head.cuesOffset < 0) return []
  const win = new WindowedReader(reader)
  const hdr = await win.bytes(head.cuesOffset, 12, 256 * 1024)
  const id = readId(hdr, 0)
  const size = id && id.id >= 0 ? readSize(hdr, id.len) : null
  if (!id || id.id !== MKV_ID.Cues || !size || size.size < 0 || size.size > 64 * 1024 * 1024) return []
  const hlen = id.len + size.len
  const body = await win.bytes(head.cuesOffset, hlen + size.size, hlen + size.size)
  const scale = head.timecodeScale / 1e9
  const preferred: MkvCue[] = []
  const other: MkvCue[] = []
  eachChild(body, hlen, Math.min(body.length, hlen + size.size), (cid, cdata, csize) => {
    if (cid !== MKV_ID.CuePoint) return
    let time = -1
    eachChild(body, cdata, cdata + csize, (pid, pdata, psize) => {
      if (pid === MKV_ID.CueTime) {
        time = readUint(body, pdata, psize)
      }
      else if (pid === MKV_ID.CueTrackPositions && time >= 0) {
        let track = 0
        let position = -1
        eachChild(body, pdata, pdata + psize, (kid, kdata, ksize) => {
          if (kid === MKV_ID.CueTrack) track = readUint(body, kdata, ksize)
          else if (kid === MKV_ID.CueClusterPosition) position = readUint(body, kdata, ksize)
        })
        if (position < 0) return
        const cue = { time: time * scale, offset: head.segmentStart + position }
        if (track === preferTrack) preferred.push(cue)
        else other.push(cue)
      }
    })
  })
  const cues = preferred.length ? preferred : other
  return cues.sort((a, b) => a.time - b.time)
}

/** The last cue at or before `seconds` (the first cue when none is). */
export function cueBefore(cues: readonly MkvCue[], seconds: number): MkvCue | null {
  if (!cues.length) return null
  let lo = 0
  let hi = cues.length - 1
  if (cues[0]!.time > seconds) return cues[0]!
  while (lo < hi) {
    const mid = (lo + hi + 1) >> 1
    if (cues[mid]!.time <= seconds) lo = mid
    else hi = mid - 1
  }
  return cues[lo]!
}

// ---------------------------------------------------------------------------
// Streaming cluster demuxer

export interface MkvFrame {
  track: number
  /** Timecode units, absolute (cluster + block). */
  time: number
  keyframe: boolean
  data: Uint8Array
  /** Position inside a laced block: 0 for the first/only frame. */
  lace: number
  /** BlockDuration in timecode units, -1 when the block does not carry one. */
  duration: number
}

/**
 * Feed it bytes starting exactly at a Cluster (or anywhere — it resyncs on the
 * next Cluster ID) and it hands back frames in file order. Nothing but the
 * current partial element is ever held, so memory stays flat however long the
 * film.
 */
export class MkvClusterDemuxer {
  /** Absolute file offset of the next byte `push` expects. */
  position: number
  /** Absolute offset of the Cluster currently being read, -1 before the first. */
  clusterOffset = -1
  /** Seconds of the Cluster currently being read, -1 before the first. */
  clusterSeconds = -1
  private buf = new Uint8Array(1 << 20)
  private start = 0
  private end = 0
  private skip = 0
  private clusterTime = -1
  private headerStrip = new Map<number, Uint8Array>()
  private head: MkvHead
  private wanted: ReadonlySet<number>

  constructor(head: MkvHead, wanted: ReadonlySet<number>, startOffset: number) {
    this.head = head
    this.wanted = wanted
    this.position = startOffset
    for (const track of head.tracks) {
      if (track.headerStrip) this.headerStrip.set(track.number, track.headerStrip)
    }
  }

  push(chunk: Uint8Array): MkvFrame[] {
    this.append(chunk)
    this.position += chunk.length
    const frames: MkvFrame[] = []
    this.parse(frames)
    return frames
  }

  private append(chunk: Uint8Array) {
    const pending = this.end - this.start
    if (this.start > 0 && (this.end + chunk.length > this.buf.length || this.start > this.buf.length / 2)) {
      this.buf.copyWithin(0, this.start, this.end)
      this.end = pending
      this.start = 0
    }
    if (this.end + chunk.length > this.buf.length) {
      let capacity = this.buf.length
      while (capacity < this.end + chunk.length) capacity *= 2
      const grown = new Uint8Array(capacity)
      grown.set(this.buf.subarray(0, this.end))
      this.buf = grown
    }
    this.buf.set(chunk, this.end)
    this.end += chunk.length
  }

  /** Absolute file offset of buf[i]. */
  private absolute(i: number) {
    return this.position - (this.end - i)
  }

  private resync() {
    const buf = this.buf
    for (let i = this.start + 1; i + 3 < this.end; i++) {
      if (buf[i] === 0x1F && buf[i + 1] === 0x43 && buf[i + 2] === 0xB6 && buf[i + 3] === 0x75) {
        this.start = i
        return
      }
    }
    this.start = Math.max(this.start, this.end - 3)
    this.clusterTime = -1
  }

  private parse(out: MkvFrame[]) {
    const buf = this.buf
    for (;;) {
      if (this.skip > 0) {
        const n = Math.min(this.skip, this.end - this.start)
        this.start += n
        this.skip -= n
        if (this.skip > 0) return
      }
      if (this.end - this.start < 2) return
      const view = buf.subarray(0, this.end)
      const id = readId(view, this.start)
      if (!id) return
      if (id.id < 0) { this.resync(); continue }
      const size = readSize(view, this.start + id.len)
      if (!size) return
      if (size.size === -2) { this.resync(); continue }
      const hlen = id.len + size.len

      if (id.id === MKV_ID.Segment) {
        this.start += hlen
        continue
      }
      if (id.id === MKV_ID.Cluster) {
        this.clusterOffset = this.absolute(this.start)
        this.clusterTime = -1
        this.start += hlen
        continue
      }
      if (id.id === MKV_ID.Timecode || id.id === MKV_ID.SimpleBlock || id.id === MKV_ID.BlockGroup) {
        if (size.size < 0 || size.size > MAX_BLOCK_BYTES) { this.resync(); continue }
        if (this.end - this.start < hlen + size.size) return
        const data = this.start + hlen
        if (id.id === MKV_ID.Timecode) {
          this.clusterTime = readUint(buf, data, size.size)
          this.clusterSeconds = this.clusterTime * this.head.timecodeScale / 1e9
        }
        else if (id.id === MKV_ID.SimpleBlock) {
          this.block(buf, data, size.size, (buf[data + (vintLength(buf[data]!) || 1) + 2]! & 0x80) !== 0, -1, out)
        }
        else {
          let blockAt = -1
          let blockSize = 0
          let referenced = false
          let duration = -1
          eachChild(view, data, data + size.size, (gid, gdata, gsize) => {
            if (gid === MKV_ID.Block) { blockAt = gdata; blockSize = gsize }
            else if (gid === MKV_ID.ReferenceBlock) referenced = true
            else if (gid === MKV_ID.BlockDuration) duration = readUint(buf, gdata, gsize)
          })
          if (blockAt >= 0) this.block(buf, blockAt, blockSize, !referenced, duration, out)
        }
        this.start += hlen + size.size
        continue
      }
      if (size.size < 0) {
        // An unknown-size master we do not care about: step inside it.
        this.start += hlen
        continue
      }
      if (SKIPPABLE.has(id.id) || size.size < 64 * 1024) {
        this.start += hlen
        this.skip = size.size
        continue
      }
      this.resync()
    }
  }

  private block(buf: Uint8Array, at: number, size: number, keyframe: boolean, duration: number, out: MkvFrame[]) {
    if (this.clusterTime < 0 || size < 4) return
    const numLen = vintLength(buf[at]!)
    if (!numLen || numLen > 4) return
    const track = readUint(buf, at, numLen) - 0x80 * 2 ** (7 * (numLen - 1))
    if (!this.wanted.has(track)) return
    let rel = (buf[at + numLen]! << 8) | buf[at + numLen + 1]!
    if (rel & 0x8000) rel -= 0x10000
    const flags = buf[at + numLen + 2]!
    const time = this.clusterTime + rel
    const lacing = (flags >> 1) & 3
    let pos = at + numLen + 3
    const end = at + size
    const strip = this.headerStrip.get(track)
    const emit = (from: number, to: number, lace: number) => {
      if (to > end || from > to) return
      let data: Uint8Array
      if (strip) {
        data = new Uint8Array(strip.length + (to - from))
        data.set(strip, 0)
        data.set(buf.subarray(from, to), strip.length)
      }
      else {
        data = buf.slice(from, to)
      }
      out.push({ track, time, keyframe, data, lace, duration })
    }
    if (lacing === 0) {
      emit(pos, end, 0)
      return
    }
    const count = buf[pos]! + 1
    pos += 1
    const sizes: number[] = []
    if (lacing === 1) {
      for (let i = 0; i < count - 1; i++) {
        let value = 0
        let byte = 255
        while (byte === 255 && pos < end) {
          byte = buf[pos++]!
          value += byte
        }
        sizes.push(value)
      }
    }
    else if (lacing === 3) {
      const view = buf.subarray(0, end)
      const firstSize = readSize(view, pos)
      if (!firstSize || firstSize.size < 0) return
      sizes.push(firstSize.size)
      pos += firstSize.len
      for (let i = 1; i < count - 1; i++) {
        const raw = readSize(view, pos)
        if (!raw || raw.size < -1) return
        const unsigned = raw.size === -1 ? (2 ** (7 * raw.len) - 1) : raw.size
        const delta = unsigned - (2 ** (7 * raw.len - 1) - 1)
        sizes.push(sizes[i - 1]! + delta)
        pos += raw.len
      }
    }
    else {
      const each = Math.floor((end - pos) / count)
      for (let i = 0; i < count - 1; i++) sizes.push(each)
    }
    const used = sizes.reduce((sum, value) => sum + value, 0)
    sizes.push(end - pos - used)
    for (let i = 0; i < sizes.length; i++) {
      const length = sizes[i]!
      if (length < 0) return
      emit(pos, pos + length, i)
      pos += length
    }
  }
}

/** Find the first Cluster at or after `from` inside `buf`; returns its index and timecode seconds. */
export function findClusterIn(buf: Uint8Array, from: number, timecodeScale: number): { index: number, seconds: number } | null {
  for (let i = Math.max(0, from); i + 12 < buf.length; i++) {
    if (buf[i] !== 0x1F || buf[i + 1] !== 0x43 || buf[i + 2] !== 0xB6 || buf[i + 3] !== 0x75) continue
    const size = readSize(buf, i + 4)
    if (!size || size.size === -2) continue
    const tcAt = i + 4 + size.len
    if (buf[tcAt] !== MKV_ID.Timecode) continue
    const tcSize = readSize(buf, tcAt + 1)
    if (!tcSize || tcSize.size < 1 || tcSize.size > 8 || tcAt + 1 + tcSize.len + tcSize.size > buf.length) continue
    const tc = readUint(buf, tcAt + 1 + tcSize.len, tcSize.size)
    return { index: i, seconds: tc * timecodeScale / 1e9 }
  }
  return null
}

// ---------------------------------------------------------------------------
// Embedded text subtitles

const TEXT_SUBTITLE_CODECS = new Set(['S_TEXT/UTF8', 'S_TEXT/ASCII', 'S_TEXT/ASS', 'S_TEXT/SSA', 'S_ASS', 'S_SSA', 'S_TEXT/WEBVTT'])

/** A subtitle track whose blocks are text we can show (not PGS/VobSub bitmaps). */
export function isTextSubtitleTrack(track: MkvTrack): boolean {
  if (track.type !== 'subtitle' || !TEXT_SUBTITLE_CODECS.has(track.codecId)) return false
  return !track.unsupportedEncoding || track.zlib
}

/** Persian by language tag, or by a track name when the tag was left at «und». */
export function isPersianTextTrack(track: MkvTrack): boolean {
  const lang = (track.language || '').toLowerCase()
  if (lang === 'fa' || lang.startsWith('fa-') || lang === 'per' || lang === 'fas') return true
  return /farsi|persian|فارسی|پارسی/i.test(track.name || '')
}

let textDecoder: TextDecoder | null = null

/**
 * One subtitle block as plain display text. ASS/SSA blocks carry
 * "ReadOrder,Layer,Style,Name,MarginL,MarginR,MarginV,Effect,Text": only the
 * last field is shown, with override tags and bidi controls removed.
 */
export function mkvSubtitleText(codecId: string, data: Uint8Array): string {
  textDecoder ||= new TextDecoder('utf-8')
  let text = textDecoder.decode(data)
  if (codecId.includes('ASS') || codecId.includes('SSA')) {
    let at = -1
    for (let commas = 0; commas < 8; commas++) {
      at = text.indexOf(',', at + 1)
      if (at < 0) break
    }
    if (at >= 0) text = text.slice(at + 1)
    text = text.replace(/\{[^}]*\}/g, '').replace(/\\[Nn]/g, '\n').replace(/\\h/g, ' ')
  }
  return text
    .replace(/<\/?[^>]+>/g, '')
    .replace(/[\u200E\u200F\u202A-\u202E\u2066-\u2069]/g, '')
    .replace(/&nbsp;/gi, ' ')
    .replace(/&lt;/gi, '<')
    .replace(/&gt;/gi, '>')
    .replace(/&amp;/gi, '&')
    .replace(/\r\n?/g, '\n')
    .split('\n').map(line => line.trim()).filter(Boolean).join('\n')
}
