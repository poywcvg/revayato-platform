export type PlaybackQuality = 'auto' | `${number}p`

export type PlaybackVersionKind = 'dub' | 'softsub' | 'hardsub' | 'original'

export interface PlaybackTextTrack {
  id: string
  label: string
  language: string
  src: string
  default?: boolean
  /** Absolute URL of the video this VTT was extracted from (for sync). */
  source_url?: string
  /** Present on series-level SoftSub mirrors for episode matching. */
  season_number?: number
  episode_number?: number
  /** e.g. subtitlestar — IMDb-matched sidecar safe to show on Soft/Hard. */
  provider?: string
  /** 1=embedded exact source, 2=SubtitleStar, 3=next provider fallback. */
  source_priority?: number
  /** exact-source, release-match, or title-fallback. */
  sync_confidence?: string
}

export interface PlaybackAudioTrack {
  id: string
  label: string
  language: string
}

export interface PlaybackVersion {
  id: string
  kind: PlaybackVersionKind
  label: string
  url: string
  quality?: string
  /** Only tracks extracted from / synced to this stream. */
  subtitleTracks: PlaybackTextTrack[]
  /** Hardsub has Persian text burned into the video. */
  burnedInSubtitles?: boolean
}

/** Minimal season/episode metadata rendered inside the online player. */
export interface PlaybackEpisodeOption {
  id: number
  title: string
  season_number: number
  episode_number: number
  duration_minutes?: number
  thumbnail_url?: string
}

/**
 * Transport-friendly playback contract.
 * A future API can return a short-lived signed URL without leaking storage paths
 * into catalog cards or detail responses.
 */
export interface PlaybackSource {
  hls_url?: string
  signed_playback_url?: string
  poster_url?: string
  subtitle_tracks?: PlaybackTextTrack[]
  audio_tracks?: PlaybackAudioTrack[]
  expires_at?: string
}

export interface PlaybackSnapshot {
  is_playing: boolean
  position_seconds: number
  duration_seconds: number
  playback_rate: number
}
