import type { AnalyticsEvent, PersonalizationConsent } from '~/types'

/**
 * Lightweight personalization state for layout and display-only components.
 * Event transport, storage hydration and preference editing remain isolated in
 * useAnalyticsEvent so they are not pulled into every route through the layout.
 */
export function usePersonalizationState() {
  const consent = useCookie<PersonalizationConsent>('revayato_personalization', {
    default: () => 'unset',
    sameSite: 'lax',
    maxAge: 60 * 60 * 24 * 365,
  })
  const events = useState<AnalyticsEvent[]>('privacy-safe-behavior-events', () => [])
  const personalizationEnabled = computed(() => consent.value === 'enabled')
  const eventCount = computed(() => events.value.length)

  return {
    consent,
    events,
    personalizationEnabled,
    eventCount,
  }
}
