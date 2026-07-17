export interface Rating {
  id: number
  username: string
  content_type: 'movie' | 'series'
  object_id: number
  score: string
  review: string
  is_spoiler: boolean
  created_at: string
  updated_at: string
}

export interface RatingSummary {
  average: number | null
  count: number
  my_rating: Rating | null
}

export interface WatchlistItemContent {
  title: string
  slug: string
  poster: string | null
}

export interface WatchlistItem {
  id: number
  content_type: 'movie' | 'series'
  object_id: number
  list_type: 'watchlist' | 'favorite' | 'watched'
  content: WatchlistItemContent | null
  created_at: string
}

export interface User {
  id: number
  email: string
  username: string
  is_verified: boolean
}

export interface Profile {
  avatar: string | null
  bio: string
  preferred_language: string
  is_email_verified: boolean
  created_at: string
  updated_at: string
}

export interface Me {
  id: number
  email: string
  username: string
  is_verified: boolean
  profile: Profile
}

export interface AuthTokens {
  access: string
  refresh: string
}

export interface AuthSession extends AuthTokens {
  user: Me
}
