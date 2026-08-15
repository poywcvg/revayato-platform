import type { ContentType, Movie } from '~/types'

export interface WatchTimeMilestone {
  key: string
  label: string
  blurb: string
  minutes_threshold: number
  next_label: string | null
  minutes_to_next: number | null
}

export interface WatchTimeEquivalent {
  id: string
  label: string
  value: number
  display: string
  unit: string
}

export interface WatchTimeStats {
  total_minutes: number
  total_hours: number
  hours: number
  minutes: number
  week_minutes: number
  week_hours_part: number
  week_minutes_part: number
  titles_started: number
  titles_completed: number
  titles_in_progress: number
  equivalents: WatchTimeEquivalent[]
  milestone: WatchTimeMilestone
  weekly_goal_minutes: number
  source: 'local' | 'activity_events' | 'merged'
  generated_at: string
}

interface LedgerEntry {
  content_type: ContentType
  object_id: number
  max_progress: number
  duration_minutes: number
  minutes_watched: number
  updated_at: string
}

interface LedgerFile {
  entries: Record<string, LedgerEntry>
  /** Progress snapshots at the start of the rolling week window. */
  week_baseline: Record<string, number>
  week_anchor: string
}

const LEDGER_KEY = 'revayato:watch-time:v1'
const DEFAULT_MOVIE_MINUTES = 110
const DEFAULT_SERIES_MINUTES = 45
const WEEKLY_GOAL = 300

function storageKeyFor(userId: number | string | null | undefined) {
  return userId ? `${LEDGER_KEY}:u${userId}` : `${LEDGER_KEY}:guest`
}

function titleKey(contentType: ContentType, objectId: number) {
  return `${contentType}:${objectId}`
}

function clampProgress(value: number) {
  return Math.min(100, Math.max(0, value))
}

function emptyLedger(): LedgerFile {
  return { entries: {}, week_baseline: {}, week_anchor: new Date().toISOString() }
}

function milestonesFor(totalMinutes: number): WatchTimeMilestone {
  const tiers: Array<[number, string, string]> = [
    [0, 'تازه‌وارد پرده', 'اولین دقیقه‌ها را روی روایتو ثبت کن.'],
    [30, 'جرقه اول', 'نیم ساعت تماشا؛ قلاب زده شد.'],
    [60, 'یک ساعت با روایت', 'اولین ساعت کامل تماشایت ثبت شد.'],
    [180, 'تماشاگر شبانه', 'سه ساعت — انگار یک شب سینما بود.'],
    [600, 'پردهٔ شخصی', 'ده ساعت تماشا؛ سلیقه‌ات دارد شکل می‌گیرد.'],
    [1800, 'روایت‌باز', 'سی ساعت — دیگر فقط رهگذر نیستی.'],
    [3600, 'ساکن روایتو', 'شصت ساعت تماشا؛ این خانه مال توست.'],
  ]
  let current = tiers[0]!
  let next: typeof tiers[number] | null = tiers[1] || null
  for (let i = 0; i < tiers.length; i++) {
    const tier = tiers[i]!
    if (totalMinutes >= tier[0]) {
      current = tier
      next = tiers[i + 1] || null
    }
  }
  return {
    key: current[1],
    label: current[1],
    blurb: current[2],
    minutes_threshold: current[0],
    next_label: next?.[1] || null,
    minutes_to_next: next ? Math.max(0, Math.round(next[0] - totalMinutes)) : null,
  }
}

function equivalentsFor(totalMinutes: number): WatchTimeEquivalent[] {
  const film = totalMinutes / 110
  const nights = totalMinutes / 120
  const rides = totalMinutes / 45
  const fmt = (n: number) => {
    if (!n) return '۰'
    const rounded = Math.round(n * 10) / 10
    return rounded.toLocaleString('fa-IR')
  }
  return [
    { id: 'films', label: 'معادل فیلم سینمایی', value: film, display: fmt(film), unit: 'فیلم' },
    { id: 'nights', label: 'شب سینمایی', value: nights, display: fmt(nights), unit: 'شب' },
    { id: 'rides', label: 'مسیر مترو', value: rides, display: fmt(rides), unit: 'مسیر' },
  ]
}

function buildStatsFromLedger(ledger: LedgerFile, source: WatchTimeStats['source']): WatchTimeStats {
  const weekStart = Date.now() - 7 * 24 * 60 * 60 * 1000
  let total = 0
  let week = 0
  let started = 0
  let completed = 0
  let inProgress = 0

  for (const entry of Object.values(ledger.entries)) {
    total += entry.minutes_watched
    const priorProgress = ledger.week_baseline[titleKey(entry.content_type, entry.object_id)] || 0
    const priorMinutes = entry.duration_minutes * (priorProgress / 100)
    const touchedThisWeek = Date.parse(entry.updated_at) >= weekStart
    if (touchedThisWeek) {
      week += Math.max(0, entry.minutes_watched - priorMinutes)
    }
    if (entry.max_progress >= 5) started += 1
    if (entry.max_progress >= 95) completed += 1
    else if (entry.max_progress >= 5) inProgress += 1
  }

  total = Math.round(total * 10) / 10
  week = Math.round(week * 10) / 10
  return {
    total_minutes: total,
    total_hours: Math.round((total / 60) * 100) / 100,
    hours: Math.floor(total / 60),
    minutes: Math.round(total % 60),
    week_minutes: week,
    week_hours_part: Math.floor(week / 60),
    week_minutes_part: Math.round(week % 60),
    titles_started: started,
    titles_completed: completed,
    titles_in_progress: inProgress,
    equivalents: equivalentsFor(total),
    milestone: milestonesFor(total),
    weekly_goal_minutes: WEEKLY_GOAL,
    source,
    generated_at: new Date().toISOString(),
  }
}

function mergeStats(local: WatchTimeStats, remote: WatchTimeStats): WatchTimeStats {
  const total = Math.max(local.total_minutes, remote.total_minutes)
  const week = Math.max(local.week_minutes, remote.week_minutes)
  return {
    ...remote,
    total_minutes: total,
    total_hours: Math.round((total / 60) * 100) / 100,
    hours: Math.floor(total / 60),
    minutes: Math.round(total % 60),
    week_minutes: week,
    week_hours_part: Math.floor(week / 60),
    week_minutes_part: Math.round(week % 60),
    titles_started: Math.max(local.titles_started, remote.titles_started),
    titles_completed: Math.max(local.titles_completed, remote.titles_completed),
    titles_in_progress: Math.max(local.titles_in_progress, remote.titles_in_progress),
    equivalents: equivalentsFor(total),
    milestone: milestonesFor(total),
    source: 'merged',
  }
}

export function formatWatchDuration(hours: number, minutes: number) {
  const h = Math.max(0, hours)
  const m = Math.max(0, minutes)
  if (h <= 0 && m <= 0) return 'هنوز صفر'
  if (h <= 0) return `${m.toLocaleString('fa-IR')} دقیقه`
  if (m <= 0) return `${h.toLocaleString('fa-IR')} ساعت`
  return `${h.toLocaleString('fa-IR')} ساعت و ${m.toLocaleString('fa-IR')} دقیقه`
}

export function useWatchTime() {
  const authStore = useAuthStore()
  const { api } = useApi()
  const ledger = useState<LedgerFile>('watch-time-ledger', () => emptyLedger())
  const remote = useState<WatchTimeStats | null>('watch-time-remote', () => null)
  const hydrated = useState('watch-time-hydrated', () => false)
  const loading = useState('watch-time-loading', () => false)

  const storageKey = computed(() => storageKeyFor(authStore.user?.id || null))

  function persist() {
    if (!import.meta.client) return
    try {
      localStorage.setItem(storageKey.value, JSON.stringify(ledger.value))
    } catch { /* quota */ }
  }

  function ensureWeekBaseline() {
    const anchor = Date.parse(ledger.value.week_anchor || '') || 0
    if (Date.now() - anchor < 7 * 24 * 60 * 60 * 1000) return
    const baseline: Record<string, number> = {}
    for (const [key, entry] of Object.entries(ledger.value.entries)) {
      baseline[key] = entry.max_progress
    }
    ledger.value = {
      ...ledger.value,
      week_baseline: baseline,
      week_anchor: new Date().toISOString(),
    }
    persist()
  }

  function hydrate() {
    if (!import.meta.client || hydrated.value) return
    hydrated.value = true
    try {
      const raw = localStorage.getItem(storageKey.value)
      const parsed = raw ? JSON.parse(raw) : null
      if (parsed && typeof parsed === 'object' && parsed.entries) {
        ledger.value = {
          entries: parsed.entries || {},
          week_baseline: parsed.week_baseline || {},
          week_anchor: parsed.week_anchor || new Date().toISOString(),
        }
      } else {
        ledger.value = emptyLedger()
      }
    } catch {
      ledger.value = emptyLedger()
    }
    ensureWeekBaseline()
  }

  function recordProgress(
    item: Pick<Movie, 'id' | 'type' | 'duration_minutes'>,
    progressPercent: number,
  ) {
    hydrate()
    ensureWeekBaseline()
    const progress = clampProgress(progressPercent)
    if (progress < 1) return
    const key = titleKey(item.type, item.id)
    const duration = Math.max(
      1,
      Number(item.duration_minutes)
        || (item.type === 'series' ? DEFAULT_SERIES_MINUTES : DEFAULT_MOVIE_MINUTES),
    )
    const previous = ledger.value.entries[key]
    const maxProgress = Math.max(previous?.max_progress || 0, progress)
    const minutes = Math.round((duration * (maxProgress / 100)) * 10) / 10
    if (!ledger.value.week_baseline[key] && !previous) {
      ledger.value.week_baseline[key] = 0
    }
    ledger.value.entries[key] = {
      content_type: item.type,
      object_id: item.id,
      max_progress: maxProgress,
      duration_minutes: duration,
      minutes_watched: Math.max(previous?.minutes_watched || 0, minutes),
      updated_at: new Date().toISOString(),
    }
    persist()
  }

  async function refreshRemote() {
    if (!authStore.isAuthenticated) {
      remote.value = null
      return
    }
    loading.value = true
    try {
      remote.value = await api<WatchTimeStats>('/engagement/watch-stats/')
    } catch {
      /* keep local */
    } finally {
      loading.value = false
    }
  }

  const localStats = computed(() => buildStatsFromLedger(ledger.value, 'local'))

  const stats = computed<WatchTimeStats>(() => {
    if (remote.value) return mergeStats(localStats.value, remote.value)
    return localStats.value
  })

  watch(storageKey, () => {
    hydrated.value = false
    remote.value = null
    ledger.value = emptyLedger()
    hydrate()
    if (authStore.isAuthenticated) refreshRemote()
  })

  if (import.meta.client && !hydrated.value) {
    onNuxtReady(() => {
      hydrate()
      if (authStore.isAuthenticated) refreshRemote()
    })
  }

  return {
    stats,
    localStats,
    loading: readonly(loading),
    recordProgress,
    refreshRemote,
    hydrate,
    formatWatchDuration,
  }
}
