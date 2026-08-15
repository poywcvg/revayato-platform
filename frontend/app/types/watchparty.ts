import type { PlaybackSnapshot, PlaybackTextTrack } from './playback'

export type WatchRoomStatus = 'active' | 'ended' | 'expired'
export type WatchPartyConnectionStatus = 'idle' | 'connecting' | 'connected' | 'reconnecting' | 'disconnected' | 'error'
export type WatchPartyPlaybackEventType =
  | 'playback.state'
  | 'playback.play'
  | 'playback.pause'
  | 'playback.seek'
  | 'playback.sync'
  | 'playback.sync.response'

export interface WatchPartyUser {
  id: number
  display_name: string
  avatar: string | null
}

export interface WatchPartyMember {
  user: WatchPartyUser
  role: 'host' | 'member'
  joined_at: string
  last_seen_at: string
  is_online: boolean
}

export interface WatchPartyMessage {
  id: number
  user: WatchPartyUser
  message: string
  created_at: string
}

export interface WatchPartyPlaybackState extends PlaybackSnapshot {
  updated_by: WatchPartyUser | null
  updated_at: string
  server_time_ms?: number
  stream_url?: string | null
}

export interface WatchPartyStreamLink {
  label: string
  quality?: string
  size_label?: string
  url: string
  kind?: string
  subtitle_type?: string
}

export interface WatchPartyContent {
  type: 'movie' | 'episode'
  id: number
  slug: string
  title: string
  secondary_title?: string
  description: string
  duration_seconds: number
  video_url: string | null
  stream_links?: WatchPartyStreamLink[]
  subtitle_tracks?: PlaybackTextTrack[]
  download_url?: string | null
  poster_url: string | null
  backdrop_url: string | null
  age_rating: string
  is_uncensored: boolean
  series?: {
    id: number
    slug: string
    title: string
    season_number: number
    episode_number: number
  }
}

export interface WatchRoom {
  invite_code: string
  status: WatchRoomStatus
  host: WatchPartyUser
  content: WatchPartyContent
  created_at: string
  expires_at: string
  member_count: number
  is_host: boolean
  is_member: boolean
  my_role: 'host' | 'member' | null
  playback_state?: WatchPartyPlaybackState | null
}

export interface WatchPartyPlaybackEvent {
  sequence: number
  type: WatchPartyPlaybackEventType
  state: WatchPartyPlaybackState
}

export interface WatchPartySocketError {
  code: string
  message: string
}
