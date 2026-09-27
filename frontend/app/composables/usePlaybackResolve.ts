/**
 * Get a playable URL for a title at the moment someone asks to watch it.
 *
 * Almost every link in this catalog is signed and short-lived: the providers
 * hand out `…?md5=<token>&expires=<unix>` and the token lapses in about thirteen
 * hours. Nothing re-signed it on the way to the player, so a viewer opening a
 * title more than half a day after it was crawled got «پخش ویدیو ممکن نشد» on a
 * film that was perfectly fine and still sitting on the origin.
 *
 * The old answer was the banner below this one — "links are being refreshed,
 * please wait" — pointing at a background task that re-crawls 120 titles every
 * half hour. Against tens of thousands of rows whose tokens lapse twice a day
 * that never catches up, so the banner was a promise the backend could not keep.
 *
 * This asks instead, on the only signal that actually means *this* link needs to
 * work *now*: someone pressed play. `POST /api/playback/resolve/` answers from a
 * string parse when the token is still good (the overwhelmingly common case, and
 * the reason this is safe to call on every open), and re-crawls the providers
 * when it is not.
 *
 * It never fails closed. If the re-crawl finds nothing, or runs past the
 * backend's deadline and is handed off to finish in the background, the reply
 * still carries the stale URL and `stale: true` — playing that and failing is no
 * worse than what happens today, and it is often not what happens at all.
 */

import type { ContentType } from '~/types'

export interface PlaybackResolution {
  /** The URL to play. Never empty when the title has any link at all. */
  videoUrl: string
  /** Backend's verdict for it: 'direct' | 'gateway' | 'unverified' | 'none'. */
  playbackMode: string
  /** Why this answer — 'fresh', 'refreshed', 'signature_expired', 'cooldown'… */
  reason: string
  /** A lapsed token was actually replaced with a working one. */
  refreshed: boolean
  /** The URL is known to be lapsed and could not be re-signed right now. */
  stale: boolean
}

interface ResolveResponse {
  video_url?: string
  playback_mode?: string
  reason?: string
  refreshed?: boolean
  stale?: boolean
}

export function usePlaybackResolve() {
  const { api } = useApi()

  /** True while a re-crawl is in flight, for the player's «در حال آماده‌سازی» state. */
  const resolving = ref(false)
  /** The last answer, or null if nothing has been asked yet. */
  const resolution = ref<PlaybackResolution | null>(null)

  /**
   * Ask for a usable URL for `kind`/`id`.
   *
   * Returns null only when the call itself failed — a network error or a
   * throttle — which the caller should treat as "carry on with what you have",
   * never as "this film is gone".
   */
  async function resolve(input: {
    kind: ContentType | string
    id: number
    episodeId?: number | null
    /** Skip the re-crawl and just report on the stored URL. */
    refresh?: boolean
  }): Promise<PlaybackResolution | null> {
    if (!input.id) return null
    resolving.value = true
    try {
      const response = await api<ResolveResponse>('/playback/resolve/', {
        method: 'POST',
        body: {
          kind: input.kind === 'series' ? 'series' : 'movie',
          id: input.id,
          ...(input.episodeId ? { episode: input.episodeId } : {}),
          refresh: input.refresh !== false,
        },
        // The backend caps its own work at ~25s and hands the crawl off to
        // finish in the background past that, so this only has to outlast the
        // deadline plus the round trip — not the crawl.
        timeout: 35_000,
      })
      const resolved: PlaybackResolution = {
        videoUrl: String(response?.video_url || '').trim(),
        playbackMode: String(response?.playback_mode || ''),
        reason: String(response?.reason || ''),
        refreshed: Boolean(response?.refreshed),
        stale: Boolean(response?.stale),
      }
      resolution.value = resolved
      return resolved
    } catch {
      // Deliberately silent. This is an optimisation on top of a URL the page
      // already has; turning its failure into a visible error would replace a
      // film that might play with a message that definitely does not.
      return null
    } finally {
      resolving.value = false
    }
  }

  return { resolve, resolving, resolution }
}
