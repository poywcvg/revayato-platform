/** Auto-report missing SoftSub on the online player and urgently extract the
 *  current movie/episode file before SubtitleStar → Subzone.ir fallbacks.
 */

import type { ContentType, PlaybackTextTrack } from '~/types'

export interface PlaybackSubtitleEnsureResult {
  status: 'ready' | 'queued' | 'unavailable' | 'missing' | 'invalid' | string
  reported?: boolean
  queued?: boolean
  has_subtitle_tracks?: boolean
  subtitle_tracks?: PlaybackTextTrack[]
  episode_id?: number | null
  report_id?: number
  message?: string
  synced?: boolean
  synced_episodes?: number
}

/**
 * When online SoftSub cues are missing, report the gap and ask the backend
 * to extract its embedded Persian track, then try provider fallbacks.
 */
export function usePlaybackSubtitleEnsure() {
  const { api } = useApi()

  async function ensurePlaybackSubtitles(input: {
    type: ContentType
    slug: string
    episodeId?: number | null
    version?: string
    sourceUrl?: string
    sync?: boolean
  }) {
    return api<PlaybackSubtitleEnsureResult>('/catalog/playback-subtitle-ensure/', {
      method: 'POST',
      body: {
        content_type: input.type,
        slug: input.slug,
        episode_id: input.episodeId || 0,
        version: input.version || '',
        source_url: input.sourceUrl || '',
        sync: input.sync !== false,
      },
      // Remote ffmpeg continues on the urgent worker; provider-only sync is short.
      timeout: 16_000,
    })
  }

  async function getPlaybackSubtitleStatus(input: {
    type: ContentType
    slug: string
    episodeId?: number | null
    reportId?: number | null
  }) {
    return api<PlaybackSubtitleEnsureResult>('/catalog/playback-subtitle-status/', {
      query: {
        content_type: input.type,
        slug: input.slug,
        episode_id: input.episodeId || 0,
        ...(input.reportId ? { report_id: input.reportId } : {}),
      },
      timeout: 8_000,
    })
  }

  return { ensurePlaybackSubtitles, getPlaybackSubtitleStatus }
}
