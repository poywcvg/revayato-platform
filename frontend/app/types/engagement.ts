import type { ContentType } from './catalog'

export interface Rating {
  id: number
  username: string
  content_type: 'movie' | 'series'
  object_id: number
  score: string
  review: string
  is_spoiler: boolean
  is_hidden?: boolean
  admin_reply?: string
  admin_reply_at?: string | null
  admin_reply_by_name?: string
  is_featured?: boolean
  featured_at?: string | null
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

// --------------------------------------------------------------------------- //
//  User collections ("کالکشن") + public profiles
// --------------------------------------------------------------------------- //
export type CollectionVisibility = 'public' | 'unlisted' | 'private'

export interface CollectionOwner {
  username: string
  avatar: string | null
}

export interface CollectionItem {
  id: number
  content_type: ContentType
  title: string
  slug: string
  poster: string | null
  site_rating: number | null
  release_year?: number | null
  start_year?: number | null
  note: string
  position: number
  added_at: string
}

export interface UserCollection {
  id: number
  slug: string
  title: string
  description: string
  visibility: CollectionVisibility
  accent: string
  item_count: number
  covers: string[]
  owner: CollectionOwner
  share_token: string
  share_url: string
  is_mine: boolean
  created_at: string
  updated_at: string
  items?: CollectionItem[]
}

/** A lightweight row for the "add to collection" picker. */
export interface CollectionPickRow {
  id: number
  slug: string
  title: string
  visibility: CollectionVisibility
  accent: string
  item_count: number
  contains: boolean
}

export interface CollectionItemMutation {
  added?: boolean
  removed?: boolean
  item_count: number
}

export interface CollectionWritePayload {
  title: string
  description?: string
  visibility?: CollectionVisibility
  accent?: string
}

export interface PublicProfileReview {
  content_type: ContentType
  object_id: number
  content: {
    id: number
    content_type: ContentType
    title: string
    slug: string
    poster: string | null
    site_rating: number | null
    release_year?: number | null
    start_year?: number | null
  } | null
  score: number
  review: string
  is_spoiler: boolean
  created_at: string
}

export interface PublicProfileStats {
  collections: number
  public_titles: number
  ratings: number
  likes: number | null
}

export interface PublicProfile {
  username: string
  display_name: string
  avatar: string | null
  bio: string
  is_verified: boolean
  member_since: string
  is_private: boolean
  is_self: boolean
  stats?: PublicProfileStats
  collections?: UserCollection[]
  reviews?: PublicProfileReview[]
}
