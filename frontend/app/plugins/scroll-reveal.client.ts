/**
 * Site-wide scroll reveal via IntersectionObserver.
 * Auto-marks common content containers with .reveal / .is-visible.
 * Re-scans after route changes and late DOM mounts (DeferredContent, Lazy*).
 */

const REVEAL_SELECTORS = [
  '.content-section',
  '.cinema-rail',
  '.page-section:not(.cinema-page)',
  '.site-footer',
  // Grids reveal with their parent section — skip per-card stagger cost on large catalogs.
  '.reveal-stagger',
  '[data-reveal]',
].join(', ')

/** Hero and explicit opt-outs — already animated or must stay still. */
const SKIP_CLOSEST = '.hero-movie-slider, [data-reveal-skip]'

function prefersReducedMotion(): boolean {
  return window.matchMedia('(prefers-reduced-motion: reduce)').matches
}

function isInsideSkip(el: Element): boolean {
  return Boolean(el.closest(SKIP_CLOSEST))
}

function collectTargets(): Element[] {
  const nodes = Array.from(document.querySelectorAll(REVEAL_SELECTORS)).filter((el) => {
    if (isInsideSkip(el)) return false
    // Avoid double-fade: rail inside a section that will reveal as a unit.
    if (
      el.matches('.cinema-rail')
      && el.closest('.content-section, .page-section:not(.cinema-page), [data-reveal]')
    ) {
      return false
    }
    return true
  })

  // Prefer outermost among remaining matches (section over nested grid).
  return nodes.filter(
    (el) => !nodes.some((other) => other !== el && other.contains(el)),
  )
}

function prepareStagger(parent: Element, reduced: boolean) {
  // Never stagger individual catalog/person/country cards — too many nodes.
  if (parent.matches('.catalog-grid, .people-grid, .country-grid')) return
  if (parent.querySelector(':scope > .catalog-grid, :scope > .people-grid, :scope > .country-grid')) {
    return
  }
  const children = Array.from(parent.children) as HTMLElement[]
  children.forEach((child, i) => {
    child.classList.add('reveal-stagger-item')
    child.style.setProperty('--reveal-delay', `calc(var(--motion-stagger, 40ms) * ${Math.min(i, 12)})`)
    if (reduced) child.classList.add('is-visible')
  })
}

export default defineNuxtPlugin((nuxtApp) => {
  if (!import.meta.client || typeof IntersectionObserver === 'undefined') return

  let observer: IntersectionObserver | null = null
  let debounceTimer: ReturnType<typeof setTimeout> | null = null
  let mo: MutationObserver | null = null
  let failsafeTimer: ReturnType<typeof setTimeout> | null = null

  /**
   * Failsafe: if the observer/IO ever fails mid-way (partial hydration, a thrown
   * error, a tab backgrounded before intersect), force-show any stranded targets
   * after 4s so content can never stay permanently invisible.
   */
  function armFailsafe() {
    if (failsafeTimer) return
    failsafeTimer = setTimeout(() => {
      document
        .querySelectorAll('.reveal:not(.is-visible)')
        .forEach((el) => el.classList.add('is-visible'))
      failsafeTimer = null
    }, 4000)
  }

  function ensureVisible(el: Element) {
    el.classList.add('reveal', 'is-visible')
  }

  function onIntersect(entries: IntersectionObserverEntry[]) {
    for (const entry of entries) {
      if (!entry.isIntersecting) continue
      entry.target.classList.add('is-visible')
      observer?.unobserve(entry.target)
    }
  }

  function setupObserver() {
    observer?.disconnect()
    observer = new IntersectionObserver(onIntersect, {
      root: null,
      // Reveal early so rails don't "pop in" late while scrolling.
      rootMargin: '0px 0px -4% 0px',
      threshold: 0.04,
    })
  }

  function observeAll() {
    if (!observer) setupObserver()

    try {
      document.documentElement.setAttribute('data-scroll-reveal', '')
    }
    catch {
      // Attribute set is non-critical; the failsafe below still reveals content.
    }
    armFailsafe()

    const reduced = prefersReducedMotion()
    const targets = collectTargets()
    const vh = window.innerHeight || document.documentElement.clientHeight

    for (const el of targets) {
      if (el.classList.contains('is-visible')) continue

      el.classList.add('reveal')

      if (reduced) {
        ensureVisible(el)
        continue
      }

      // Above / in the fold — show immediately so page enter + first paint stay clean.
      const rect = el.getBoundingClientRect()
      if (rect.top < vh * 0.92 && rect.bottom > 0) {
        ensureVisible(el)
        continue
      }

      observer!.observe(el)
    }

    document.querySelectorAll('.reveal-stagger').forEach((parent) => {
      if (isInsideSkip(parent)) return
      prepareStagger(parent, reduced)
    })
  }

  /**
   * Incrementally observe only newly-added nodes (from a MutationObserver
   * `addedNodes` batch) instead of re-scanning the whole document. This avoids
   * the full querySelectorAll + getBoundingClientRect pass on every hydration
   * tick that caused layout thrash.
   */
  function observeAdded(added: Node[]) {
    if (!observer) setupObserver()
    armFailsafe()
    const reduced = prefersReducedMotion()
    const vh = window.innerHeight || document.documentElement.clientHeight

    const candidates: Element[] = []
    for (const node of added) {
      if (node.nodeType !== Node.ELEMENT_NODE) continue
      const el = node as Element
      if (el.matches(REVEAL_SELECTORS)) candidates.push(el)
      // New containers may carry matching descendants too.
      el.querySelectorAll(REVEAL_SELECTORS).forEach((c) => candidates.push(c))
    }

    for (const el of candidates) {
      if (isInsideSkip(el)) continue
      // Skip a rail nested inside a section that reveals as a unit.
      if (
        el.matches('.cinema-rail')
        && el.closest('.content-section, .page-section:not(.cinema-page), [data-reveal]')
      ) {
        continue
      }
      if (el.classList.contains('is-visible')) continue

      el.classList.add('reveal')

      if (reduced) {
        ensureVisible(el)
        continue
      }

      const rect = el.getBoundingClientRect()
      if (rect.top < vh * 0.92 && rect.bottom > 0) {
        ensureVisible(el)
        continue
      }

      observer!.observe(el)
    }

    // Re-prepare stagger wrappers that mounted inside the added subtree.
    for (const node of added) {
      if (node.nodeType !== Node.ELEMENT_NODE) continue
      const el = node as Element
      const parents = [el, ...el.querySelectorAll('.reveal-stagger')]
      for (const parent of parents) {
        if (parent.matches('.reveal-stagger') && !isInsideSkip(parent)) {
          prepareStagger(parent, reduced)
        }
      }
    }
  }

  function scheduleObserve(resetObserver = false) {
    if (debounceTimer) clearTimeout(debounceTimer)
    debounceTimer = setTimeout(() => {
      nextTick(() => {
        requestAnimationFrame(() => {
          if (resetObserver) setupObserver()
          observeAll()
        })
      })
    }, 120)
  }

  setupObserver()

  nuxtApp.hook('app:mounted', () => {
    scheduleObserve()
    if (typeof MutationObserver === 'undefined') return
    let pending = false
    let batch: Node[] = []
    mo = new MutationObserver((mutations) => {
      // Accumulate only the newly-added nodes; defer a single incremental pass.
      for (const m of mutations) {
        for (const n of m.addedNodes) batch.push(n)
      }
      if (pending) return
      pending = true
      requestAnimationFrame(() => {
        pending = false
        const added = batch
        batch = []
        if (added.length) observeAdded(added)
      })
    })
    // Only watch main content mounts — body-wide subtree was thrashing on every rail hydrate.
    const root = document.getElementById('main-content') || document.body
    mo.observe(root, { childList: true, subtree: true })
  })

  nuxtApp.hook('page:finish', () => {
    scheduleObserve(true)
  })

  return {
    provide: {
      scrollReveal: {
        refresh: () => scheduleObserve(),
      },
    },
  }
})
