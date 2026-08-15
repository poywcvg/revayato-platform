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

export function subtitleReadyNotice(hasCues: boolean) {
  return hasCues ? 'زیرنویس فارسی فعال شد' : ''
}

export function subtitleFindingNotice() {
  return 'زیرنویس در حال بارگذاری است…'
}

export type SoftsubBannerTone = 'finding' | 'ready' | 'retrying' | 'failed'

export function softsubBannerCopy(tone: SoftsubBannerTone) {
  if (tone === 'ready') {
    return {
      title: 'زیرنویس فارسی آماده شد',
      detail: 'زیرنویس به‌صورت خودکار به پخش اضافه و روشن شد.',
    }
  }
  if (tone === 'retrying') {
    return {
      title: 'زیرنویس هنوز در حال بارگذاری است…',
      detail: 'پخش را ادامه دهید؛ به‌محض آماده شدن، زیرنویس خودش فعال می‌شود.',
    }
  }
  if (tone === 'failed') {
    return {
      title: 'زیرنویس این عنوان فعلاً پیدا نشد',
      detail: 'اگر بعداً دوباره وارد پخش شوید، دوباره به‌صورت خودکار جستجو می‌کنیم.',
    }
  }
  return {
    title: 'زیرنویس در حال بارگذاری است…',
    detail: 'ابتدا زیرنویس داخل همین فایل پخش استخراج می‌شود؛ اگر موجود نباشد منابع زیرنویس بررسی می‌شوند. پخش را ادامه دهید.',
  }
}
