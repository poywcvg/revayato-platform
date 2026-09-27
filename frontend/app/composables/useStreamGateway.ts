/**
 * Last-resort playback path.
 *
 * Direct CDN playback stays primary — this only engages once a browser has
 * actually failed to open a file, which is why every entry point here takes
 * the URL that just failed. The backend rewraps that file into fragmented-MP4
 * HLS on demand, which the player already knows how to play everywhere via
 * hls.js (and natively on Safari).
 *
 * A session covers a bounded stretch of the film rather than the whole thing,
 * so the caller must be ready to reopen at the playhead. That is not a special
 * case: it is the same call a seek makes.
 */

import type { ContentType } from '~/types'

export interface StreamGatewaySession {
  session: string
  /** Fully-qualified .m3u8 the player can load directly. */
  playlist: string
  /** Where in the film this session begins, in seconds. */
  start: number
  /** True duration of the whole film, not of this session. */
  duration: number
  mode: 'remux' | 'transcode'
  video: string
  audio: string
  width: number
  height: number
  /** How much film one session covers before it has to be reopened. */
  chunkSeconds: number
  /**
   * How much already-watched film the session still holds. The gateway deletes
   * segments behind the viewer as it serves them — disk on that box is scarce —
   * so a rewind further back than this has to reopen instead of asking for a
   * segment that is no longer there.
   */
  keepBehindSeconds: number
}

interface OpenResponse {
  ok?: boolean
  session?: string
  playlist?: string
  start?: number
  duration?: number
  mode?: string
  video?: string
  audio?: string
  width?: number
  height?: number
  chunk_seconds?: number
  keep_behind_seconds?: number
  code?: string
  detail?: string
}

/**
 * Persian text for each failure the gateway can report. These are shown to a
 * viewer who is already staring at a video that will not play, so each one
 * says what is happening rather than naming the fault.
 */
const GATEWAY_MESSAGES: Record<string, string> = {
  gateway_busy: 'در حال حاضر تعداد پخش‌های هم‌زمان زیاد است. چند لحظه دیگر دوباره تلاش کن.',
  probe_failed: 'فایل این نسخه در دسترس نیست. داریم نسخهٔ دیگری برایش پیدا می‌کنیم.',
  stream_start_failed: 'آماده‌سازی این فایل بیش از حد طول کشید. چند لحظه دیگر دوباره تلاش کن.',
  transcode_disabled: 'این نسخه با این مرورگر سازگار نیست. داریم نسخهٔ سازگار را آماده می‌کنیم.',
  unsupported_source: 'این منبع قابل تبدیل نیست.',
  unknown_source: 'این منبع دیگر به این عنوان تعلق ندارد. صفحه را تازه کن.',
  bad_request: 'اطلاعات این درخواست ناقص بود.',
}

export function gatewayMessageFor(code: string): string {
  return GATEWAY_MESSAGES[code] || 'پخش سازگار در دسترس نیست. کمی بعد دوباره تلاش کن.'
}

export function useStreamGateway() {
  const { api } = useApi()
  const config = useRuntimeConfig()

  /**
   * Build the playlist URL from our own API base rather than trusting the
   * absolute URL the backend assembled. Behind a proxy the backend's idea of
   * its public origin depends on forwarded headers; the client always knows.
   */
  function playlistUrlFor(session: string) {
    const base = String(config.public.apiBase || '/api').replace(/\/$/, '')
    return `${base}/stream/${session}/index.m3u8`
  }

  /**
   * Ask the gateway for a playable stream of `url` starting at `position`.
   *
   * Resolves to a session, or throws a `StreamGatewayError` carrying a code the
   * caller can turn into a message. The call is slow by design — it returns
   * only once the first segment exists — so callers should show progress.
   */
  async function openGatewayStream(input: {
    kind: ContentType | 'episode'
    id: number
    url: string
    position?: number
  }): Promise<StreamGatewaySession> {
    const response = await api<OpenResponse>('/stream/open/', {
      method: 'POST',
      body: {
        kind: input.kind,
        id: input.id,
        url: input.url,
        t: Math.max(0, Math.floor(input.position || 0)),
      },
      // Generous: the backend waits for ffmpeg to produce a real segment
      // before answering, and a cold remux of a remote file takes a moment.
      timeout: 45_000,
    })

    if (!response?.ok || !response.session) {
      const error = new Error(response?.detail || 'gateway failed') as Error & { code: string }
      error.code = response?.code || 'gateway_failed'
      throw error
    }

    return {
      session: response.session,
      playlist: playlistUrlFor(response.session),
      start: Number(response.start) || 0,
      duration: Number(response.duration) || 0,
      mode: response.mode === 'transcode' ? 'transcode' : 'remux',
      video: String(response.video || ''),
      audio: String(response.audio || ''),
      width: Number(response.width) || 0,
      height: Number(response.height) || 0,
      chunkSeconds: Number(response.chunk_seconds) || 1800,
      keepBehindSeconds: Number(response.keep_behind_seconds) || 120,
    }
  }

  /** Is this URL one the gateway produced? */
  function isGatewayUrl(url: string) {
    return /\/stream\/[A-Za-z0-9]+\/index\.m3u8(?:$|[?#])/.test(String(url || ''))
  }

  return { openGatewayStream, playlistUrlFor, isGatewayUrl, gatewayMessageFor }
}
