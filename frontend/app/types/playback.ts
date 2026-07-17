export type PlaybackQuality = 'auto' | '1080p' | '720p' | '480p'

export interface PlaybackTextTrack {
  id: string
  label: string
  language: string
  src: string
  default?: boolean
}

export interface PlaybackAudioTrack {
  id: string
  label: string
  language: string
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
