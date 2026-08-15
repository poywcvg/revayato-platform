export interface Rating {
  id: number
  username: string
  content_type: 'movie' | 'series'
  object_id: number
  score: string
  review: string
  is_spoiler: boolean
  is_hidden?: boolean
  created_at: string
  updated_at: string
}

export interface RatingSummary {
  average: number | null
  count: number
  my_rating: Rating | null
  reviews?: Rating[]
}

export type SupportCategory =
  | 'content_request'
  | 'bug'
  | 'content_fix'
  | 'suggestion'
  | 'support'
  | 'cooperation'

export type SupportStatus =
  | 'open'
  | 'in_progress'
  | 'waiting_user'
  | 'resolved'
  | 'closed'

export interface SupportMessage {
  id: number
  body: string
  is_staff_reply: boolean
  author_username: string
  created_at: string
}

export interface SupportTicketListItem {
  id: number
  tracking_code: string
  category: SupportCategory
  category_label: string
  subject: string
  related_title: string
  status: SupportStatus
  status_label: string
  unread_by_staff: boolean
  unread_by_user: boolean
  username: string
  message_count: number
  last_message_at: string
  created_at: string
}

export interface SupportTicket extends SupportTicketListItem {
  body: string
  related_year: number | null
  related_url: string
  messages: SupportMessage[]
  updated_at: string
  staff_note?: string
  user_email?: string
}

export interface SupportTicketCreatePayload {
  category: SupportCategory
  subject: string
  body: string
  related_title?: string
  related_year?: number | null
  related_url?: string
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
  is_staff: boolean
  is_superuser?: boolean
  profile: Profile
}

export interface AuthTokens {
  access: string
  refresh: string
}

export interface AuthSession extends AuthTokens {
  user: Me
}
