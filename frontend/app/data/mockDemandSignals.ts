import type { AggregateDemandSignal } from '~/types'

/**
 * Fictional, site-level demand signals. These records intentionally contain
 * no user ID, session ID, device data, external browsing history or raw logs.
 */
export const mockAggregateDemandSignals: AggregateDemandSignal[] = [
  {
    source: 'search_console_aggregate',
    query: 'فیلم علمی تخیلی جدید',
    genre_slugs: ['sci-fi'],
    score: 9.2,
    impressions: 1840,
    clicks: 276,
    period_start: '2026-07-01',
    period_end: '2026-07-07',
    site_scope_only: true,
  },
  {
    source: 'site_search_aggregate',
    query: 'سریال معمایی',
    genre_slugs: ['mystery', 'crime'],
    score: 8.4,
    period_start: '2026-07-01',
    period_end: '2026-07-07',
    site_scope_only: true,
  },
  {
    source: 'editorial_trend',
    query: 'درام خانوادگی تابستان',
    genre_slugs: ['drama', 'family'],
    score: 6.8,
    period_start: '2026-07-01',
    period_end: '2026-08-31',
    site_scope_only: true,
  },
]
