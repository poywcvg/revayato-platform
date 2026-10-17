/**
 * Online player subtitle policy.
 *
 * Full pipeline: docs/SUBTITLES.md
 *
 * Priority for what the viewer should see:
 * 1. SoftSub encode + WebVTT cues (toggleable)
 * 2. HardSub encode (Persian burned into the frame)
 * 3. Dub (Persian audio; sidecar only when paired)
 */
import type { PlaybackTextTrack, PlaybackVersion } from '~/types'

export const SUBTITLE_VERSION_PRIORITY = ['softsub', 'hardsub', 'dub'] as const

export function isPlayableSubtitleTrack(track: PlaybackTextTrack | null | undefined) {
  return Boolean(track?.src)
}

export function pickDefaultSubtitleTrack(tracks: readonly PlaybackTextTrack[]) {
  const usable = [...tracks]
    .filter(isPlayableSubtitleTrack)
    .sort((left, right) => (
      (left.source_priority || 99) - (right.source_priority || 99)
    ))
  return usable.find(track => track.default)
    || usable.find(track => (track.language || '').toLowerCase().startsWith('fa'))
    || usable.find(track => (track.language || '').toLowerCase().startsWith('per'))
    || usable[0]
    || null
}

/** Prefer SoftSub with cues, then burned-in Hard/Soft, then Dub. */
export function pickDefaultPlaybackVersion(versions: readonly PlaybackVersion[]) {
  const softWithCues = versions.find(version => (
    version.kind === 'softsub' && version.subtitleTracks.some(isPlayableSubtitleTrack)
  ))
  if (softWithCues) return softWithCues

  const burnedIn = versions.find(version => version.burnedInSubtitles)
  if (burnedIn) return burnedIn

  const softOrHard = versions.find(version => (
    version.kind === 'softsub'
    && version.subtitleTracks.some(isPlayableSubtitleTrack)
  )) || versions.find(version => version.kind === 'hardsub')
  if (softOrHard) return softOrHard

  // Never prefer empty SoftSub (no cues, not burned-in) over Dub — but Dub
  // still loses to any version that can show Persian text.
  const softEmpty = versions.find(version => version.kind === 'softsub')
  if (softEmpty?.burnedInSubtitles) return softEmpty

  return versions.find(version => version.kind === 'dub') || versions[0] || null
}

/** The one toast of the automatic subtitle hunt, shown once and only after
 *  Persian cues are really in the player. */
export function subtitleReadyNotice(hasCues: boolean) {
  return hasCues ? 'زیرنویس فارسی اضافه شد' : ''
}

/** Where the automatic subtitle hunt stands, shown in its own status card so
 *  the viewer knows to keep watching while the server fetches Persian cues:
 *  - searching: the ensure call is in flight
 *  - preparing: a worker is fetching/extracting; the player polls for it
 *  - background: this page stopped polling fast; a slow poll and the server
 *    hunt go on, and cues that land still appear here
 *  - missing: the server has searched every source (cooldown before retry) */
export type SubtitleHuntPhase = 'searching' | 'preparing' | 'background' | 'missing'

export interface SubtitleHuntStatus {
  phase: SubtitleHuntPhase
  title: string
  detail: string
  /** Busy phases stay up until the hunt moves on; the rest fade on their own. */
  busy: boolean
  durationMs: number
}

export function subtitleHuntStatus(phase: SubtitleHuntPhase, isEpisode = false): SubtitleHuntStatus {
  const subject = isEpisode ? 'این قسمت' : 'این فیلم'
  switch (phase) {
    case 'searching':
      return {
        phase,
        title: 'در حال پیدا کردن زیرنویس فارسی…',
        detail: 'پخش ادامه دارد؛ زیرنویس به‌محض آماده شدن خودکار اضافه می‌شود.',
        busy: true,
        durationMs: 0,
      }
    case 'preparing':
      return {
        phase,
        title: 'در حال آماده‌سازی زیرنویس فارسی…',
        detail: 'لطفاً در پلیر بمانید؛ زیرنویس بدون قطع پخش اضافه می‌شود.',
        busy: true,
        durationMs: 0,
      }
    case 'background':
      return {
        phase,
        title: 'زیرنویس هنوز آماده نشده',
        detail: 'جستجو در پس‌زمینه ادامه دارد؛ هر وقت آماده شد همین‌جا اضافه می‌شود.',
        busy: false,
        durationMs: 6_000,
      }
    case 'missing':
      return {
        phase,
        title: `زیرنویس فارسی برای ${subject} پیدا نشد`,
        detail: 'منابع زیرنویس بعداً دوباره بررسی می‌شوند.',
        busy: false,
        durationMs: 5_000,
      }
  }
}
