/**
 * Client-side subtitle engine for the online player.
 * Supports WebVTT, SRT, and basic ASS/SSA so every SoftSub format we serve can render.
 */

export interface SubtitleCue {
  start: number
  end: number
  text: string
}

function stripMarkup(value: string) {
  return String(value || '')
    .replace(/<\/?[^>]+>/g, '')
    .replace(/\{.*?\}/g, '')
    // Strip bidi isolates/embeddings common in Persian SoftSub exports.
    .replace(/[\u200E\u200F\u202A-\u202E\u2066-\u2069]/g, '')
    .replace(/&nbsp;/gi, ' ')
    .replace(/&amp;/gi, '&')
    .replace(/&lt;/gi, '<')
    .replace(/&gt;/gi, '>')
    .trim()
}

function parseTimestamp(raw: string): number {
  const value = String(raw || '').trim().replace(',', '.')
  const match = value.match(/(?:(\d{1,2}):)?(\d{1,2}):(\d{2})(?:\.(\d{1,3}))?/)
  if (!match) return Number.NaN
  const hours = Number(match[1] || 0)
  const minutes = Number(match[2] || 0)
  const seconds = Number(match[3] || 0)
  const ms = Number((match[4] || '0').padEnd(3, '0').slice(0, 3))
  return hours * 3600 + minutes * 60 + seconds + ms / 1000
}

function pushCue(cues: SubtitleCue[], startRaw: string, endRaw: string, body: string) {
  const start = parseTimestamp(startRaw)
  const end = parseTimestamp(endRaw)
  const text = stripMarkup(body).replace(/\\N/g, '\n').replace(/\\n/g, '\n').trim()
  if (!Number.isFinite(start) || !Number.isFinite(end) || end <= start || !text) return
  cues.push({ start, end, text })
}

export function parseWebVtt(raw: string): SubtitleCue[] {
  const text = String(raw || '').replace(/^\uFEFF/, '').replace(/\r\n/g, '\n').replace(/\r/g, '\n')
  const body = text.replace(/^WEBVTT[^\n]*\n+/i, '')
  const blocks = body.split(/\n\s*\n/)
  const cues: SubtitleCue[] = []
  for (const block of blocks) {
    const lines = block.split('\n').map(line => line.trimEnd()).filter(line => line.trim() !== '')
    const firstLine = lines[0]
    if (!firstLine) continue
    // Skip NOTE / STYLE / REGION header blocks.
    if (/^(NOTE|STYLE|REGION)\b/i.test(firstLine)) continue
    let timingIndex = 0
    if (!firstLine.includes('-->') && lines[1]?.includes('-->')) timingIndex = 1
    const timing = lines[timingIndex] || ''
    if (!timing.includes('-->')) continue
    const [startPart = '', endPart = ''] = timing.split('-->')
    const startRaw = startPart.trim().split(/\s+/)[0] || ''
    const endRaw = endPart.trim().split(/\s+/)[0] || ''
    const payload = lines.slice(timingIndex + 1).join('\n')
    pushCue(cues, startRaw, endRaw, payload)
  }
  return cues
}

export function parseSrt(raw: string): SubtitleCue[] {
  const text = String(raw || '').replace(/^\uFEFF/, '').replace(/\r\n/g, '\n').replace(/\r/g, '\n').trim()
  const blocks = text.split(/\n\s*\n/)
  const cues: SubtitleCue[] = []
  for (const block of blocks) {
    const lines = block.split('\n').map(line => line.trimEnd()).filter(line => line.trim() !== '')
    const firstLine = lines[0]
    if (!firstLine) continue
    let offset = 0
    if (/^\d+$/.test(firstLine.trim())) offset = 1
    const timing = lines[offset] || ''
    if (!timing.includes('-->')) continue
    const [startPart = '', endPart = ''] = timing.split('-->')
    const startRaw = startPart.trim()
    const endRaw = endPart.trim()
    pushCue(cues, startRaw, endRaw, lines.slice(offset + 1).join('\n'))
  }
  return cues
}

export function parseAss(raw: string): SubtitleCue[] {
  const cues: SubtitleCue[] = []
  for (const line of String(raw || '').replace(/\r\n/g, '\n').split('\n')) {
    if (!/^dialogue:/i.test(line.trim())) continue
    const payload = line.split(':').slice(1).join(':').trim()
    const parts = payload.split(',')
    if (parts.length < 10) continue
    const startRaw = parts[1]?.trim() || ''
    const endRaw = parts[2]?.trim() || ''
    const body = parts.slice(9).join(',')
    pushCue(cues, startRaw, endRaw, body)
  }
  return cues
}

export function parseSubtitleText(raw: string, hintUrl = ''): SubtitleCue[] {
  const text = String(raw || '').replace(/^\uFEFF/, '')
  const lower = `${hintUrl} ${text.slice(0, 80)}`.toLowerCase()
  if (lower.includes('webvtt') || /\.vtt(\?|$)/i.test(hintUrl)) return parseWebVtt(text)
  if (/\[script info\]/i.test(text) || /\[events\]/i.test(text) || /\.(ass|ssa)(\?|$)/i.test(hintUrl)) {
    return parseAss(text)
  }
  if (/^\s*\d+\s*\n\d{1,2}:\d{2}:\d{2}[,.]\d/m.test(text) || /\.srt(\?|$)/i.test(hintUrl)) {
    return parseSrt(text)
  }
  if (/-->/.test(text)) return parseWebVtt(text.includes('WEBVTT') ? text : `WEBVTT\n\n${text}`)
  return parseSrt(text)
}

/** Same-origin proxy for cross-origin SoftSub files (CDN CORS). */
export function subtitleFetchUrl(src: string): string {
  const url = String(src || '').trim()
  if (!url || !import.meta.client) return url
  if (url.startsWith('blob:') || url.startsWith('data:')) return url
  // Protocol-relative CDN URLs still need the same-origin proxy.
  if (url.startsWith('/') && !url.startsWith('//')) return url
  try {
    const parsed = new URL(url, window.location.origin)
    if (parsed.origin === window.location.origin) return `${parsed.pathname}${parsed.search}`
    // Prefer same-origin /media rewrite when CDN hosts our media path.
    if (parsed.pathname.startsWith('/media/')) return `${parsed.pathname}${parsed.search}`
    return `/subtitle?url=${encodeURIComponent(url)}`
  } catch {
    return url
  }
}

const cueCache = new Map<string, Promise<SubtitleCue[]>>()

/**
 * Subtitle sync offset range and step (seconds). Positive offset shifts cues
 * earlier on screen (subs GATELY LATE by <offset>); negative shows them later
 * (subs EARLY). Kept tight so a misplaced tap can't push subs fully off-media.
 */
export const SUBTITLE_OFFSET_MIN = -10
export const SUBTITLE_OFFSET_MAX = 10
export const SUBTITLE_OFFSET_STEP = 0.25

export async function loadSubtitleCues(src: string): Promise<SubtitleCue[]> {
  const url = String(src || '').trim()
  if (!url) return []
  const cached = cueCache.get(url)
  if (cached) return cached

  const request = (async () => {
    const fetchUrl = subtitleFetchUrl(url)
    const response = await fetch(fetchUrl, { credentials: 'omit', mode: 'cors' })
    if (!response.ok) throw new Error(`subtitle http ${response.status}`)
    const text = await response.text()
    return parseSubtitleText(text, url).sort((a, b) => a.start - b.start || a.end - b.end)
  })()

  cueCache.set(url, request)
  try {
    return await request
  } catch (error) {
    cueCache.delete(url)
    throw error
  }
}

export function activeCueText(cues: readonly SubtitleCue[], timeSeconds: number): string {
  return findActiveCue(cues, timeSeconds)?.text || ''
}

/**
 * Active cue at media time.
 * Uses last-start-wins among overlaps (common in ASS) so dialogue stays readable.
 */
export function findActiveCue(cues: readonly SubtitleCue[], timeSeconds: number): SubtitleCue | null {
  if (!cues.length || !Number.isFinite(timeSeconds)) return null

  let low = 0
  let high = cues.length - 1
  let lastStartIndex = -1
  while (low <= high) {
    const mid = (low + high) >> 1
    const cue = cues[mid]
    if (!cue) break
    if (cue.start <= timeSeconds) {
      lastStartIndex = mid
      low = mid + 1
    } else {
      high = mid - 1
    }
  }
  if (lastStartIndex < 0) return null

  let best: SubtitleCue | null = null
  for (let index = lastStartIndex; index >= 0; index -= 1) {
    const cue = cues[index]
    if (!cue) continue
    if (cue.start > timeSeconds) continue
    if (timeSeconds < cue.end) {
      if (!best || cue.start >= best.start) best = cue
    }
    // Stop once starts are far enough that further overlaps are unlikely.
    if (lastStartIndex - index > 12) break
  }
  return best
}
