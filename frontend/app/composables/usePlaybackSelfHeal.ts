/**
 * Self-healing for every online playback: single watch page AND watch-party.
 *
 * When `<video>` fails for any reason the player knows *how* it failed
 * (media error code, HLS fatal, startup/stall watchdog, gateway code).
 * This composable files that failure once through
 * `POST /api/catalog/playback-failure/` — which classifies it onto the exact
 * `problem_type` a manual «گزارش خطا» would have used and runs the same
 * crawler repair — then polls `GET /api/catalog/report-issue/status/` until
 * the catalog serves something better and hands that URL back for an
 * immediate retry.
 *
 * Guarantees:
 * - one report per failed source (deduped by URL, not by flood);
 * - never loops: a fixed URL equal to the failed one is not retried;
 * - never breaks playback: every network error resolves to null, the caller
 *   keeps its existing mirror/gateway fallback;
 * - Persian notices only, suitable for direct toast display.
 */

export interface PlaybackFailureInput {
  type: 'movie' | 'series'
  objectId: number
  slug?: string
  episodeId?: number | null
  errorCode: string | number
  errorMessage?: string
  gatewayCode?: string
  sourceUrl: string
  version?: string
  /** watch-party invite code, when inside a room. */
  roomCode?: string
  playedSeconds?: number
  hadPlayed?: boolean
  problemType?: string
  player?: string
}

export interface PlaybackHealResult {
  ok: boolean
  reportId: number | null
  problemType: string
  status: string
  fixedUrl: string
  playbackMode: string
  shouldRetry: boolean
  roomNotified: boolean
  messageFa: string
}

const REPORTED_SOURCES = new Set<string>()
const MAX_TRACKED_SOURCES = 200

function healKey(input: PlaybackFailureInput) {
  return `${input.type}:${input.objectId}:${input.episodeId || 0}:${String(input.sourceUrl || '').slice(0, 200)}:${String(input.errorCode || '')}`
}

function rememberReported(key: string) {
  REPORTED_SOURCES.add(key)
  if (REPORTED_SOURCES.size > MAX_TRACKED_SOURCES) {
    const first = REPORTED_SOURCES.values().next().value
    if (first) REPORTED_SOURCES.delete(first)
  }
}

export function usePlaybackSelfHeal() {
  const { api } = useApi()

  /**
   * File the failure and return what the player should do next.
   * Resolves to null when there is nothing actionable (deduped, throttled,
   * unknown title) — the caller then continues with its local fallback.
   */
  async function healFailure(input: PlaybackFailureInput): Promise<PlaybackHealResult | null> {
    const source = String(input.sourceUrl || '').trim()
    if (!input.objectId && !input.slug) return null
    if (!source && !input.errorCode) return null
    const key = healKey(input)
    if (REPORTED_SOURCES.has(key)) return null
    rememberReported(key)

    try {
      const res = await api<{
        ok?: boolean
        report_id?: number | null
        problem_type?: string
        status?: string
        fixed_url?: string
        playback_mode?: string
        should_retry?: boolean
        room_notified?: boolean
        message_fa?: string
      }>('/catalog/playback-failure/', {
        method: 'POST',
        body: {
          content_type: input.type,
          object_id: input.objectId || 0,
          slug: input.slug || '',
          episode_id: input.type === 'series' ? input.episodeId || 0 : 0,
          error_code: String(input.errorCode ?? ''),
          error_message: (input.errorMessage || '').slice(0, 500),
          gateway_code: input.gatewayCode || '',
          source_url: source,
          version: input.version || '',
          player: input.player || (typeof navigator !== 'undefined' && /Android/i.test(navigator.userAgent || '') ? 'android' : 'web'),
          room_code: input.roomCode || '',
          played_seconds: Math.max(0, Number(input.playedSeconds) || 0),
          had_played: Boolean(input.hadPlayed || (Number(input.playedSeconds) || 0) > 1),
          problem_type: input.problemType || '',
        },
        timeout: 15_000,
      })
      if (!res?.ok) return null
      const fixed = String(res.fixed_url || '').trim()
      // Never hand back the URL that just failed as a "fix".
      const shouldRetry = Boolean(res.should_retry) && Boolean(fixed) && fixed !== source
      return {
        ok: true,
        reportId: res.report_id ?? null,
        problemType: String(res.problem_type || ''),
        status: String(res.status || 'open'),
        fixedUrl: shouldRetry || (fixed && fixed !== source) ? fixed : (fixed === source ? '' : fixed),
        playbackMode: String(res.playback_mode || ''),
        shouldRetry,
        roomNotified: Boolean(res.room_notified),
        messageFa: String(res.message_fa || 'خطای پخش ثبت شد؛ داریم نسخه سالم را آماده می‌کنیم…'),
      }
    }
    catch {
      // Best-effort: a failed heal report must never break the player.
      return null
    }
  }

  /**
   * Poll a filed report until the catalog serves a URL different from the
   * failed one. Resolves to that URL or '' after maxAttempts.
   */
  async function pollFixedUrl(reportId: number, failedSource: string, maxAttempts = 6): Promise<string> {
    const failed = String(failedSource || '').trim()
    for (let attempt = 0; attempt < maxAttempts; attempt++) {
      try {
        // Backoff: 3s, 5s, 8s, 12s, 15s, 15s — the worker needs seconds,
        // the viewer needs an answer within a minute.
        const delay = [3000, 5000, 8000, 12000, 15000, 15000][Math.min(attempt, 5)]
        await new Promise(resolve => setTimeout(resolve, delay))
        const res = await api<{
          ok?: boolean
          resolved?: boolean
          fixed_url?: string
          status?: string
        }>(`/catalog/report-issue/status/?report_id=${encodeURIComponent(reportId)}`, { timeout: 8000 })
        const fixed = String(res?.fixed_url || '').trim()
        if (fixed && fixed !== failed) return fixed
        if (res?.resolved && fixed) return fixed
        if (String(res?.status || '') === 'needs_review') return ''
      }
      catch {
        // A missed poll is harmless; the next one retries.
      }
    }
    return ''
  }

  /** Forget a source so a later distinct failure on it can be reported again. */
  function clearReported(input: Pick<PlaybackFailureInput, 'type' | 'objectId' | 'episodeId' | 'sourceUrl' | 'errorCode'>) {
    REPORTED_SOURCES.delete(healKey(input as PlaybackFailureInput))
  }

  return { healFailure, pollFixedUrl, clearReported }
}
