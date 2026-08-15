/**
 * Optional hook to re-scan the DOM for scroll-reveal targets
 * after client-only content mounts outside route transitions.
 */
export function useScrollReveal() {
  const nuxtApp = useNuxtApp()

  function refresh() {
    const api = nuxtApp.$scrollReveal as { refresh?: () => void } | undefined
    api?.refresh?.()
  }

  return { refresh }
}
