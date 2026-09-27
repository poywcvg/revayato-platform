/** Report the subtitle timing offset a viewer settled on, feeding the backend
 *  crowd-sync consensus that bakes corrections into the served VTT files.
 */

import type { ContentType, SubtitleSyncFeedback } from '~/types'

export function useSubtitleSyncReport() {
  const { api } = useApi()

  async function reportSubtitleSync(input: {
    type: ContentType
    objectId: number
    episodeId?: number | null
    feedback: SubtitleSyncFeedback
  }) {
    const objectId = Number(input.objectId) || 0
    const { trackId, offset, sig } = input.feedback
    // Nothing to converge on without a target, a file signature, or a shift.
    if (!objectId || !trackId || !sig || !Number.isFinite(offset)) return
    try {
      await api('/catalog/subtitle-sync/report/', {
        method: 'POST',
        body: {
          content_type: input.type,
          object_id: objectId,
          episode_id: input.type === 'series' ? input.episodeId || 0 : 0,
          track_id: trackId,
          sig,
          offset,
        },
        // Pure telemetry — never let it stall or surface in the player UI.
        timeout: 6_000,
      })
    } catch {
      /* best-effort: a dropped vote just doesn't count toward consensus */
    }
  }

  return { reportSubtitleSync }
}
