/**
 * جدول پخش — shared types and labels for /schedule and the home rail.
 *
 * Dates come from TMDB (official broadcast / digital release day) and are
 * bucketed by the backend in Tehran time. The public schedule lists only
 * releases that are on روایتو right now (playable or downloadable); episodes of
 * one season that dropped on the same day share a card (`episode_numbers`).
 */

export type AiringStatus = 'upcoming' | 'waiting' | 'available' | 'missed'
export type ReleaseType = 'premiere' | 'finale' | 'mid_season' | 'standard' | 'digital'

export interface ScheduleEntry {
  type: 'episode' | 'movie'
  air_date: string
  released: boolean
  status: AiringStatus
  available: boolean
  available_at: string | null
  release_type: ReleaseType | ''
  series_slug: string
  series_title: string
  series_original_title: string
  poster_url: string | null
  still_url?: string
  network?: string
  runtime_minutes?: number | null
  season_number: number | null
  episode_number: number | null
  episode_numbers?: number[]
  episode_title: string | null
  imdb_rating: string | null
  site_rating?: string | null
  year?: number | null
  content_format: string
  is_dubbed: boolean
  has_subtitle: boolean
  is_published: boolean
}

export interface ScheduleDay {
  date: string
  weekday: number
  weekday_label: string
  is_today: boolean
  count: number
  available: number
  entries: ScheduleEntry[]
}

export interface ScheduleResponse {
  start: string
  end: string
  today: string
  timezone?: string
  days: ScheduleDay[]
  total: number
  generated_at: string
}

export function releaseBadge(entry: ScheduleEntry): string {
  switch (entry.release_type) {
    case 'premiere':
      return (entry.season_number ?? 1) <= 1 ? 'سریال تازه' : 'آغاز فصل'
    case 'finale':
      return 'قسمت پایانی'
    case 'mid_season':
      return 'پایان نیمه‌فصل'
    case 'digital':
      return 'نسخهٔ دیجیتال'
    default:
      return ''
  }
}

const fa = (n: number) => n.toLocaleString('fa-IR')

/** «قسمت ۵», «قسمت ۱ تا ۸» for a same-day drop, «قسمت ۲ و ۵» for a gap. */
export function episodeLabel(entry: ScheduleEntry): string {
  const numbers = entry.episode_numbers?.length ? entry.episode_numbers : [entry.episode_number ?? 0]
  const first = numbers[0]!
  const last = numbers[numbers.length - 1]!
  if (numbers.length === 1) return `قسمت ${fa(first)}`
  if (last - first + 1 === numbers.length) return `قسمت ${fa(first)} تا ${fa(last)}`
  if (numbers.length === 2) return `قسمت ${fa(first)} و ${fa(last)}`
  return `${fa(numbers.length)} قسمت`
}

export function episodeTag(entry: ScheduleEntry): string {
  if (entry.type === 'movie') return 'فیلم'
  return `فصل ${fa(entry.season_number ?? 0)} · ${episodeLabel(entry)}`
}

/** «امروز» / «دیروز» / the weekday. */
export function dayName(day: ScheduleDay, today: string): string {
  if (day.date === today) return 'امروز'
  const yesterday = new Date(`${today}T12:00:00`)
  yesterday.setDate(yesterday.getDate() - 1)
  if (day.date === yesterday.toISOString().slice(0, 10)) return 'دیروز'
  return day.weekday_label
}

/** The title page, opened on the season when it is an episode. */
export function scheduleLink(entry: ScheduleEntry): string | undefined {
  if (!entry.is_published || !entry.series_slug) return undefined
  if (entry.type === 'movie') return `/movies/${entry.series_slug}`
  return entry.season_number ? `/series/${entry.series_slug}#season-${entry.season_number}` : `/series/${entry.series_slug}`
}

export function jalaliParts(iso: string): { day: string, month: string } {
  // Noon avoids a DST/offset edge flipping the calendar day.
  const date = new Date(`${iso}T12:00:00`)
  return {
    day: new Intl.DateTimeFormat('fa-IR-u-ca-persian', { day: 'numeric' }).format(date),
    month: new Intl.DateTimeFormat('fa-IR-u-ca-persian', { month: 'long' }).format(date),
  }
}
