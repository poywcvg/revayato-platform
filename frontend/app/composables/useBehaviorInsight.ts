import type { ContentType, Movie } from '~/types'
import { adaptApiCatalogItem, type ApiCatalogItem } from '~/data/catalogAdapter'

interface BehaviorInsightEntry {
  content_type: ContentType
  score: number
  reason: string
  item: ApiCatalogItem
}

interface BehaviorInsightResponse {
  message: string
  recommendations: BehaviorInsightEntry[]
  taste_summary?: {
    top_genres?: Array<{ slug: string; title: string; score?: number }>
    inferred_playback?: string
    completed_count?: number
  }
  personalized: boolean
  confidence: number
  signals_used: number
  model: string | null
  ai_available: boolean
}

export function useBehaviorInsight(limit = 6) {
  const authStore = useAuthStore()
  const config = useRuntimeConfig()
  const { api } = useApi()
  const data = shallowRef<BehaviorInsightResponse | null>(null)
  const pending = ref(false)
  const error = ref<string | null>(null)

  const recommendations = computed<Array<{ item: Movie; reason: string }>>(() => {
    const mediaBase = String(config.public.mediaCdnBaseUrl)
    return (data.value?.recommendations || []).map(entry => ({
      item: adaptApiCatalogItem(entry.item, entry.content_type, mediaBase),
      reason: entry.reason,
    }))
  })

  async function analyze() {
    if (!authStore.isAuthenticated || pending.value) return
    pending.value = true
    error.value = null
    try {
      data.value = await api<BehaviorInsightResponse>('/assistant/insight/', {
        query: { limit },
        timeout: 35_000,
      })
    } catch (cause) {
      error.value = getAppError(cause, 'تحلیل رفتار در حال حاضر در دسترس نیست.').reason
        || 'تحلیل رفتار در حال حاضر در دسترس نیست.'
    } finally {
      pending.value = false
    }
  }

  return {
    insight: readonly(data),
    recommendations,
    pending: readonly(pending),
    error: readonly(error),
    analyze,
  }
}
