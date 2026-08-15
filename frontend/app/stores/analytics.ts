import { defineStore } from 'pinia'
import type {
  AnalyticsContentData,
  AnalyticsEngagementData,
  AnalyticsEnvelope,
  AnalyticsOverviewData,
  AnalyticsPeriodKey,
  AnalyticsUsersData,
} from '~/types/analytics'
import type { AdminDashboardResponse } from '~/types/admin'

type Granularity = 'daily' | 'weekly' | 'monthly'

interface CacheEntry<T> {
  payload: T
  fetchedAt: number
}

interface EnvelopeCacheEntry<T> extends CacheEntry<AnalyticsEnvelope<T>> {}

const CACHE_TTL_MS = 60_000

export const useAnalyticsStore = defineStore('analytics', () => {
  const period = ref<AnalyticsPeriodKey>('30d')
  const granularity = ref<Granularity>('daily')

  const overview = ref<EnvelopeCacheEntry<AnalyticsOverviewData> | null>(null)
  const users = ref<EnvelopeCacheEntry<AnalyticsUsersData> | null>(null)
  const content = ref<EnvelopeCacheEntry<AnalyticsContentData> | null>(null)
  const engagement = ref<EnvelopeCacheEntry<AnalyticsEngagementData> | null>(null)
  /** DB-backed catalog health from the legacy /admin/dashboard endpoint. */
  const health = ref<CacheEntry<AdminDashboardResponse> | null>(null)

  const loading = ref({
    overview: false,
    users: false,
    content: false,
    engagement: false,
    health: false,
  })
  const errors = ref({
    overview: '' as string,
    users: '' as string,
    content: '' as string,
    engagement: '' as string,
    health: '' as string,
  })

  function isFresh<T>(entry: CacheEntry<T> | null, key: string) {
    if (!entry) return false
    const period = (entry.payload as { period?: { key?: string; label?: string; days?: number } }).period
    if (period && period.key !== key && period.label !== key) {
      // also accept days match
      const days = Number.parseInt(key, 10) || Number.parseInt(key.replace('d', ''), 10)
      if (period.days !== undefined && period.days !== days) return false
    }
    return Date.now() - entry.fetchedAt < CACHE_TTL_MS
  }

  function setPeriod(next: AnalyticsPeriodKey) {
    period.value = next
  }

  function setGranularity(next: Granularity) {
    granularity.value = next
  }

  function clearErrors() {
    errors.value = { overview: '', users: '', content: '', engagement: '', health: '' }
  }

  return {
    period,
    granularity,
    overview,
    users,
    content,
    engagement,
    health,
    loading,
    errors,
    isFresh,
    setPeriod,
    setGranularity,
    clearErrors,
  }
})
