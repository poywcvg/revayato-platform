import type {
  AnalyticsContentData,
  AnalyticsEngagementData,
  AnalyticsEnvelope,
  AnalyticsOverviewData,
  AnalyticsPeriodKey,
  AnalyticsUsersData,
} from '~/types/analytics'
import type { AdminDashboardResponse } from '~/types/admin'
import { useAnalyticsStore } from '~/stores/analytics'

const PERIOD_DAYS: Record<AnalyticsPeriodKey, number> = { '7d': 7, '30d': 30, '90d': 90 }

function errorMessage(error: unknown) {
  if (!error || typeof error !== 'object') return 'خطا در دریافت آمار'
  const candidate = error as { data?: { detail?: string }, message?: string, statusMessage?: string }
  return candidate.data?.detail || candidate.statusMessage || candidate.message || 'خطا در دریافت آمار'
}

export function useAnalytics() {
  const { api } = useApi()
  const store = useAnalyticsStore()

  async function fetchOverview(force = false) {
    const period = store.period
    if (!force && store.isFresh(store.overview, period) && store.overview) {
      return store.overview.payload
    }
    store.loading.overview = true
    store.errors.overview = ''
    try {
      const payload = await api<AnalyticsEnvelope<AnalyticsOverviewData>>('/analytics/overview/', {
        query: { period },
      })
      store.overview = { payload, fetchedAt: Date.now() }
      return payload
    } catch (error) {
      store.errors.overview = errorMessage(error)
      throw error
    } finally {
      store.loading.overview = false
    }
  }

  async function fetchUsers(force = false) {
    const period = store.period
    const granularity = store.granularity
    if (
      !force
      && store.users
      && store.users.payload.data.registrations.granularity === granularity
      && store.isFresh(store.users, period)
    ) {
      return store.users.payload
    }
    store.loading.users = true
    store.errors.users = ''
    try {
      const payload = await api<AnalyticsEnvelope<AnalyticsUsersData>>('/analytics/users/', {
        query: { period, granularity },
      })
      store.users = { payload, fetchedAt: Date.now() }
      return payload
    } catch (error) {
      store.errors.users = errorMessage(error)
      throw error
    } finally {
      store.loading.users = false
    }
  }

  async function fetchContent(force = false) {
    const period = store.period
    if (!force && store.isFresh(store.content, period) && store.content) {
      return store.content.payload
    }
    store.loading.content = true
    store.errors.content = ''
    try {
      const payload = await api<AnalyticsEnvelope<AnalyticsContentData>>('/analytics/content/top/', {
        query: { period },
      })
      store.content = { payload, fetchedAt: Date.now() }
      return payload
    } catch (error) {
      store.errors.content = errorMessage(error)
      throw error
    } finally {
      store.loading.content = false
    }
  }

  async function fetchEngagement(force = false) {
    const period = store.period
    if (!force && store.isFresh(store.engagement, period) && store.engagement) {
      return store.engagement.payload
    }
    store.loading.engagement = true
    store.errors.engagement = ''
    try {
      const payload = await api<AnalyticsEnvelope<AnalyticsEngagementData>>('/analytics/engagement/', {
        query: { period },
      })
      store.engagement = { payload, fetchedAt: Date.now() }
      return payload
    } catch (error) {
      store.errors.engagement = errorMessage(error)
      throw error
    } finally {
      store.loading.engagement = false
    }
  }

  /** DB-backed catalog health + watchparty + funnel from /admin/dashboard. */
  async function fetchAdminHealth(force = false) {
    const period = store.period
    const days = PERIOD_DAYS[period] || 30
    if (!force && store.isFresh(store.health, String(days)) && store.health) {
      return store.health.payload
    }
    store.loading.health = true
    store.errors.health = ''
    try {
      const payload = await api<AdminDashboardResponse>('/admin/dashboard/', {
        query: { days },
      })
      store.health = { payload, fetchedAt: Date.now() }
      return payload
    } catch (error) {
      store.errors.health = errorMessage(error)
      throw error
    } finally {
      store.loading.health = false
    }
  }

  async function refreshAll(force = true) {
    await Promise.allSettled([
      fetchOverview(force),
      fetchUsers(force),
      fetchContent(force),
      fetchEngagement(force),
      fetchAdminHealth(force),
    ])
  }

  function setPeriod(period: AnalyticsPeriodKey) {
    store.setPeriod(period)
  }

  return {
    store,
    fetchOverview,
    fetchUsers,
    fetchContent,
    fetchEngagement,
    fetchAdminHealth,
    refreshAll,
    setPeriod,
  }
}
