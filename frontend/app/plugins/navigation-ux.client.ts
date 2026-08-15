export default defineNuxtPlugin((nuxtApp) => {
  const router = useRouter()
  let keyboardNavigation = false
  let shouldFocusMain = false
  let shouldScrollTop = false
  let isPopStateNav = false
  let busyTimer: ReturnType<typeof setTimeout> | undefined
  let initialScrollPinned = false
  let reduceMotion = false

  const mainContent = () =>
    document.querySelector<HTMLElement>('#main-content, #player-content, main')

  const prefersReducedMotion = () =>
    window.matchMedia('(prefers-reduced-motion: reduce)').matches

  const scrollWindowTop = (behavior: ScrollBehavior = 'auto') => {
    const root = document.scrollingElement || document.documentElement
    if (behavior === 'smooth' && 'scrollTo' in window) {
      window.scrollTo({ top: 0, left: 0, behavior: 'smooth' })
      return
    }
    root.scrollTop = 0
    document.body.scrollTop = 0
    window.scrollTo({ top: 0, left: 0, behavior: 'auto' })
  }

  // Stop the browser from restoring a mid-page scroll on refresh.
  try {
    if ('scrollRestoration' in history) history.scrollRestoration = 'manual'
  } catch {
    /* ignore */
  }

  const pinInitialScrollTop = () => {
    if (initialScrollPinned) return
    if (window.location.hash) return
    initialScrollPinned = true
    scrollWindowTop('auto')
    requestAnimationFrame(() => scrollWindowTop('auto'))
    // Late image/hero layout can push the viewport; re-assert once.
    window.setTimeout(() => scrollWindowTop('auto'), 50)
    window.setTimeout(() => scrollWindowTop('auto'), 180)
  }

  const setNavigationBusy = (busy: boolean) => {
    document.documentElement.toggleAttribute('data-page-navigating', busy)
    const main = mainContent()
    if (busy) main?.setAttribute('aria-busy', 'true')
    else main?.removeAttribute('aria-busy')

    if (busyTimer) {
      clearTimeout(busyTimer)
      busyTimer = undefined
    }
    // Safety: never leave the app stuck in "navigating" if a transition/Suspense
    // hand-off is interrupted (aborted route, chunk error, etc.).
    if (busy) {
      busyTimer = setTimeout(() => setNavigationBusy(false), 8_000)
    }
  }

  const markKeyboardNavigation = () => {
    keyboardNavigation = true
  }
  const markPointerNavigation = () => {
    keyboardNavigation = false
  }

  document.addEventListener('keydown', markKeyboardNavigation, { capture: true })
  document.addEventListener('pointerdown', markPointerNavigation, { capture: true })
  // Browser back/forward — keep history scroll position instead of forcing top.
  window.addEventListener('popstate', () => {
    isPopStateNav = true
  })

  reduceMotion = prefersReducedMotion()
  window.matchMedia('(prefers-reduced-motion: reduce)').addEventListener('change', (event) => {
    reduceMotion = event.matches
  })

  // Pin top ASAP — before/during hydration — so refresh never lands mid-page.
  pinInitialScrollTop()
  window.addEventListener('pageshow', (event) => {
    // bfcache restores scroll correctly; only re-pin on real reloads.
    if (!event.persisted) pinInitialScrollTop()
  })

  router.beforeEach((to, from) => {
    if (to.fullPath !== from.fullPath) setNavigationBusy(true)
  })

  router.afterEach((to, from, failure) => {
    shouldFocusMain = !failure && keyboardNavigation && to.path !== from.path
    shouldScrollTop = !failure && !to.hash && to.path !== from.path && !isPopStateNav
    isPopStateNav = false
    if (failure) setNavigationBusy(false)
  })
  router.onError(() => setNavigationBusy(false))

  nuxtApp.hook('app:mounted', () => {
    pinInitialScrollTop()
  })

  nuxtApp.hook('page:finish', async () => {
    setNavigationBusy(false)
    await nextTick()
    if (!window.location.hash) pinInitialScrollTop()
    if (shouldScrollTop) {
      shouldScrollTop = false
      // Instant jump to top first (avoids mid-page flash), then a short settle.
      scrollWindowTop('auto')
      requestAnimationFrame(() => {
        scrollWindowTop('auto')
        if (!reduceMotion) {
          // Tiny delayed settle after images/layout without fighting page fade.
          window.setTimeout(() => scrollWindowTop('auto'), 120)
        }
      })
    }
    if (!shouldFocusMain) return
    shouldFocusMain = false
    mainContent()?.focus({
      preventScroll: true,
    })
  })

  nuxtApp.hook('vue:error', () => setNavigationBusy(false))
  nuxtApp.hook('app:error', () => setNavigationBusy(false))

  // The Nuxt root and these listeners intentionally share the document lifetime.
})
