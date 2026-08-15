import type { RouterConfig } from 'nuxt/schema'

const headerOffset = 80

function prefersReducedMotion() {
  return typeof window !== 'undefined'
    && window.matchMedia('(prefers-reduced-motion: reduce)').matches
}

function isBrowserBack(to: { fullPath: string }, from: { fullPath?: string }, savedPosition: unknown) {
  return Boolean(savedPosition) && Boolean(from?.fullPath) && to.fullPath !== from.fullPath
}

export default <RouterConfig>{
  scrollBehavior(to, from, savedPosition) {
    // Hash targets: jump after layout, keep header clear.
    if (to.hash) {
      return {
        el: to.hash,
        top: headerOffset,
        behavior: prefersReducedMotion() ? 'auto' : 'smooth',
      }
    }

    // Back/forward: restore history position immediately (no transition delay).
    if (isBrowserBack(to, from, savedPosition) && savedPosition) {
      return savedPosition
    }

    // Fresh navigations and hard reloads always land at the top.
    if (!from || to.path !== from.path || !from.matched?.length) {
      return { left: 0, top: 0 }
    }

    return false
  },
}
