import { mockAggregateDemandSignals } from '~/data/mockDemandSignals'
import { buildBehaviorProfile, rankRecommendations } from '~/utils/recommendationScoring'

export function usePersonalizedRecommendations(limit = 8) {
  const { catalog } = useCatalog()
  const { personalizationEnabled, preferences, events } = useAnalyticsEvent()
  const behaviorProfile = computed(() => buildBehaviorProfile(events.value, catalog.value))
  const hasExplicitPreferences = computed(() => preferences.value.favorite_genres.length
    + preferences.value.disliked_genres.length
    + preferences.value.preferred_countries.length
    + preferences.value.preferred_languages.length
    + preferences.value.preferred_age_ratings.length
    + Number(preferences.value.playback_preference !== 'any')
    + Number(preferences.value.content_sensitivity !== 'any') > 0)
  const isPersonalized = computed(() => personalizationEnabled.value
    && (hasExplicitPreferences.value || behaviorProfile.value.confidence >= 0.05))
  const personalizationLevel = computed(() => {
    if (!isPersonalized.value) return 'cold_start' as const
    if (behaviorProfile.value.confidence < 0.35) return 'learning' as const
    if (behaviorProfile.value.confidence < 0.7) return 'growing' as const
    return 'tuned' as const
  })

  const rankedRecommendations = computed(() => {
    if (!personalizationEnabled.value) {
      return catalog.value
        .filter(item => item.is_recommended)
        .slice(0, limit)
        .map(item => ({ item, score: 0, reasons: [item.recommendation_reason || 'انتخاب تحریریه براساس کیفیت و محبوبیت'] }))
    }

    return rankRecommendations(catalog.value, preferences.value, events.value, mockAggregateDemandSignals, limit)
  })
  const recommendations = computed(() => rankedRecommendations.value.map(entry => entry.item))

  return {
    recommendations,
    rankedRecommendations,
    isPersonalized,
    personalizationLevel,
    recommendationConfidence: computed(() => behaviorProfile.value.confidence),
  }
}
