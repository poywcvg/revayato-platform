import type { AnalyticsEvent, PersonalizationConsent } from '~/types'

/**
 * Lightweight personalization state for layout and display-only components.
 * Event transport, storage hydration and preference editing remain isolated in
 * useAnalyticsEvent so they are not pulled into every route through the layout.
 */
export function usePersonalizationState() {
  const authStore = useAuthStore()
  // Do not set a default cookie on SSR — writing Set-Cookie makes Cloudflare DYNAMIC
  // and prevents edge caching of the home HTML.
  const consent = useCookie<PersonalizationConsent | null>('revayato_personalization', {
    sameSite: 'lax',
    maxAge: 60 * 60 * 24 * 365,
  })
  const events = useState<AnalyticsEvent[]>('privacy-safe-behavior-events', () => [])
  const consentValue = computed<PersonalizationConsent>(() => consent.value || 'unset')
  /**
   * Logged-in members get automatic behavior analysis unless they explicitly
   * opted out. Guests never train the account recommender.
   */
  const personalizationEnabled = computed(() => {
    if (authStore.isAuthenticated) return consentValue.value !== 'disabled'
    return consentValue.value === 'enabled'
  })
  const eventCount = computed(() => events.value.length)

  function ensureAccountPersonalization() {
    if (!authStore.isAuthenticated) return
    if (consentValue.value === 'disabled') return
    if (consent.value !== 'enabled') consent.value = 'enabled'
  }

  return {
    consent,
    consentValue,
    events,
    personalizationEnabled,
    eventCount,
    ensureAccountPersonalization,
  }
}
