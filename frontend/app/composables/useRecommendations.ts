import type { ContentType } from '~/types'
import { adaptApiCatalogItem } from '~/data/catalogAdapter'
import type { ApiCatalogItem } from '~/data/catalogAdapter'

interface AccountRecommendationEntry {
  content_type: ContentType
  score: number
  reason: string
  item: ApiCatalogItem
}

interface AccountRecommendationResponse {
  personalized: boolean
  confidence: number
  signals_used: number
  taste_summary?: {
    top_genres?: Array<{ slug: string; title: string }>
    inferred_playback?: string
    completed_count?: number
    mode?: string
  }
  recommendations: AccountRecommendationEntry[]
}

/**
 * Account-only recommendations. Ranking is produced by the backend from
 * authenticated behavior, likes, ratings and watchlist rows stored in the DB.
 * Guest sessions never run a local recommendation algorithm.
 */
export function usePersonalizedRecommendations(limit = 8) {
  const authStore = useAuthStore()
  const config = useRuntimeConfig()
  const { api } = useApi()
  const { preferences } = useAnalyticsEvent()

  const { data, pending, error, refresh } = useLazyAsyncData<AccountRecommendationResponse | null>(
    `account-recommendations-${limit}`,
    () => {
      if (!authStore.isAuthenticated) return Promise.resolve(null)
      // Account recommendations run automatically after login — no preference quiz required.
      return api<AccountRecommendationResponse>('/recommendations/', {
        query: {
          limit,
          favorite_genres: preferences.value.favorite_genres.join(','),
          disliked_genres: preferences.value.disliked_genres.join(','),
          preferred_countries: preferences.value.preferred_countries.join(','),
          preferred_languages: preferences.value.preferred_languages.join(','),
          preferred_age_ratings: preferences.value.preferred_age_ratings.join(','),
          playback_preference: preferences.value.playback_preference,
          content_sensitivity: preferences.value.content_sensitivity,
        },
      })
    },
    {
      default: () => null,
      server: false,
      watch: [
        () => authStore.isAuthenticated,
        () => authStore.user?.id,
        () => JSON.stringify(preferences.value),
      ],
    },
  )

  const rankedRecommendations = computed(() => {
    if (!authStore.isAuthenticated || !data.value) return []
    const mediaBase = String(config.public.mediaCdnBaseUrl)
    return data.value.recommendations.map((entry) => {
      const item = adaptApiCatalogItem(entry.item, entry.content_type, mediaBase)
      item.recommendation_reason = entry.reason
      return {
        item,
        score: entry.score,
        reasons: [entry.reason],
      }
    })
  })

  const recommendations = computed(() => rankedRecommendations.value.map(entry => entry.item))
  const isPersonalized = computed(() => Boolean(
    authStore.isAuthenticated && data.value?.personalized,
  ))
  const personalizationLevel = computed(() => {
    const confidence = Number(data.value?.confidence || 0)
    if (!isPersonalized.value) return 'cold_start' as const
    if (confidence < 0.35) return 'learning' as const
    if (confidence < 0.7) return 'growing' as const
    return 'tuned' as const
  })

  return {
    recommendations,
    rankedRecommendations,
    isPersonalized,
    isAccountBased: computed(() => authStore.isAuthenticated),
    personalizationLevel,
    recommendationConfidence: computed(() => Number(data.value?.confidence || 0)),
    recommendationSignals: computed(() => Number(data.value?.signals_used || 0)),
    tasteSummary: computed(() => data.value?.taste_summary || null),
    recommendationsPending: pending,
    recommendationsError: error,
    refreshRecommendations: refresh,
  }
}
