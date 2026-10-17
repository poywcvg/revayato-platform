<script setup lang="ts">
/**
 * PillNav — Vue port of React Bits' <PillNav /> (TypeScript + Tailwind + gsap).
 *
 * Differences from the React original, all deliberate:
 * - NuxtLink instead of react-router's Link (external/hash hrefs render <a>).
 * - gsap is imported lazily (idle time or first hover) so the header, which
 *   is on every page, does not pay for it in the critical bundle. Until it
 *   arrives, CSS keeps the hover layers hidden so nothing flashes.
 * - The wrapper is in normal flow (the host places it) and the logo is
 *   optional, so it can sit inside an existing header next to AppLogo.
 * - No menubar/menuitem roles (they promise arrow-key handling the component
 *   never had); the active pill gets aria-current="page" instead.
 * - prefers-reduced-motion skips every tween.
 */
import type { gsap as GsapType } from 'gsap'

export interface PillNavItem {
  label: string
  href: string
  ariaLabel?: string
}

const props = withDefaults(defineProps<{
  logo?: string
  logoAlt?: string
  items: PillNavItem[]
  activeHref?: string
  ease?: string
  baseColor?: string
  pillColor?: string
  hoveredPillTextColor?: string
  pillTextColor?: string
  initialLoadAnimation?: boolean
  /** Render the hamburger + dropdown below md. Off when the host has its own mobile nav. */
  mobileMenu?: boolean
}>(), {
  logo: undefined,
  logoAlt: 'Logo',
  activeHref: undefined,
  ease: 'power3.out',
  baseColor: '#fff',
  pillColor: '#120F17',
  hoveredPillTextColor: '#120F17',
  pillTextColor: undefined,
  initialLoadAnimation: true,
  mobileMenu: true,
})

const emit = defineEmits<{ mobileMenuClick: [] }>()

type Gsap = typeof GsapType
type Timeline = ReturnType<Gsap['timeline']>
type Tween = ReturnType<Gsap['to']>

let gsap: Gsap | null = null
let gsapPromise: Promise<Gsap> | null = null
function loadGsap(): Promise<Gsap> {
  gsapPromise ??= import('gsap').then((mod) => {
    gsap = mod.gsap
    return gsap
  })
  return gsapPromise
}

const route = useRoute()
const reducedMotion = useMediaQuery('(prefers-reduced-motion: reduce)')

const isMobileMenuOpen = ref(false)
const circleRefs: (HTMLElement | null)[] = []
const tlRefs: (Timeline | null)[] = []
const activeTweenRefs: (Tween | null)[] = []
const logoImgRef = ref<HTMLImageElement | null>(null)
const logoRef = ref<{ $el: HTMLElement } | null>(null)
const hamburgerRef = ref<HTMLButtonElement | null>(null)
const mobileMenuRef = ref<HTMLElement | null>(null)
const navItemsRef = ref<HTMLElement | null>(null)
let logoTween: Tween | null = null

const cssVars = computed(() => ({
  '--base': props.baseColor,
  '--pill-bg': props.pillColor,
  '--hover-text': props.hoveredPillTextColor,
  '--pill-text': props.pillTextColor ?? props.baseColor,
}))

const isExternalLink = (href: string) =>
  /^(?:https?:)?\/\//.test(href) || /^(?:mailto|tel):/.test(href) || href.startsWith('#')

function setCircleRef(i: number, el: unknown) {
  circleRefs[i] = el as HTMLElement | null
}

function layout() {
  const g = gsap
  if (!g) return
  circleRefs.length = props.items.length
  circleRefs.forEach((circle, index) => {
    if (!circle?.parentElement) return
    const pill = circle.parentElement
    const { width: w, height: h } = pill.getBoundingClientRect()
    if (!w || !h) return
    const R = ((w * w) / 4 + h * h) / (2 * h)
    const D = Math.ceil(2 * R) + 2
    const delta = Math.ceil(R - Math.sqrt(Math.max(0, R * R - (w * w) / 4))) + 1
    const originY = D - delta

    circle.style.width = `${D}px`
    circle.style.height = `${D}px`
    circle.style.bottom = `-${delta}px`
    g.set(circle, { xPercent: -50, scale: 0, opacity: 1, transformOrigin: `50% ${originY}px` })

    const label = pill.querySelector<HTMLElement>('.pill-label')
    const hover = pill.querySelector<HTMLElement>('.pill-label-hover')
    if (label) g.set(label, { y: 0 })
    if (hover) g.set(hover, { y: Math.ceil(h + 100), opacity: 0 })

    tlRefs[index]?.kill()
    const tl = g.timeline({ paused: true })
    tl.to(circle, { scale: 1.2, xPercent: -50, duration: 2, ease: props.ease, overwrite: 'auto' }, 0)
    if (label) tl.to(label, { y: -(h + 8), duration: 2, ease: props.ease, overwrite: 'auto' }, 0)
    if (hover) tl.to(hover, { y: 0, opacity: 1, duration: 2, ease: props.ease, overwrite: 'auto' }, 0)
    tlRefs[index] = tl
  })
}

async function handleEnter(i: number) {
  if (reducedMotion.value) return
  if (!gsap) {
    await loadGsap()
    layout()
  }
  const tl = tlRefs[i]
  if (!tl) return
  activeTweenRefs[i]?.kill()
  activeTweenRefs[i] = tl.tweenTo(tl.duration(), { duration: 0.3, ease: props.ease, overwrite: 'auto' })
}

function handleLeave(i: number) {
  const tl = tlRefs[i]
  if (!tl) return
  activeTweenRefs[i]?.kill()
  activeTweenRefs[i] = tl.tweenTo(0, { duration: 0.2, ease: props.ease, overwrite: 'auto' })
}

function handleLogoEnter() {
  const img = logoImgRef.value
  if (!img || !gsap || reducedMotion.value) return
  logoTween?.kill()
  gsap.set(img, { rotate: 0 })
  logoTween = gsap.to(img, { rotate: 360, duration: 0.2, ease: props.ease, overwrite: 'auto' })
}

async function setMobileMenu(open: boolean) {
  if (open === isMobileMenuOpen.value) return
  isMobileMenuOpen.value = open
  const g = gsap ?? await loadGsap()
  const instant = reducedMotion.value ? 0 : 1

  const lines = hamburgerRef.value?.querySelectorAll('.hamburger-line')
  if (lines?.length === 2) {
    g.to(lines[0]!, { rotation: open ? 45 : 0, y: open ? 3 : 0, duration: 0.3 * instant, ease: props.ease })
    g.to(lines[1]!, { rotation: open ? -45 : 0, y: open ? -3 : 0, duration: 0.3 * instant, ease: props.ease })
  }

  const menu = mobileMenuRef.value
  if (!menu) return
  if (open) {
    g.set(menu, { visibility: 'visible' })
    g.fromTo(menu, { opacity: 0, y: 10 }, {
      opacity: 1, y: 0, duration: 0.3 * instant, ease: props.ease, transformOrigin: 'top center',
    })
  }
  else {
    g.to(menu, {
      opacity: 0,
      y: 10,
      duration: 0.2 * instant,
      ease: props.ease,
      transformOrigin: 'top center',
      onComplete: () => { g.set(menu, { visibility: 'hidden' }) },
    })
  }
}

function toggleMobileMenu() {
  void setMobileMenu(!isMobileMenuOpen.value)
  emit('mobileMenuClick')
}

function playInitialAnimation(g: Gsap) {
  if (!props.initialLoadAnimation || reducedMotion.value) return
  const logoEl = logoRef.value?.$el
  if (logoEl) {
    g.set(logoEl, { scale: 0 })
    g.to(logoEl, { scale: 1, duration: 0.6, ease: props.ease })
  }
  const navItems = navItemsRef.value
  if (navItems) {
    g.set(navItems, { width: 0, overflow: 'hidden' })
    g.to(navItems, { width: 'auto', duration: 0.6, ease: props.ease })
  }
}

onMounted(() => {
  const start = () => loadGsap().then((g) => {
    layout()
    playInitialAnimation(g)
    document.fonts?.ready.then(layout).catch(() => {})
  })
  // The initial reveal needs gsap straight away; plain hover can wait for idle.
  if (props.initialLoadAnimation) void start()
  else if (typeof window.requestIdleCallback === 'function') window.requestIdleCallback(() => void start(), { timeout: 2500 })
  else setTimeout(() => void start(), 1200)
})

useEventListener('resize', layout, { passive: true })
watch(() => [props.items, props.ease], () => nextTick(layout), { deep: true })
watch(() => route.fullPath, () => void setMobileMenu(false))

onBeforeUnmount(() => {
  tlRefs.forEach(tl => tl?.kill())
  activeTweenRefs.forEach(tween => tween?.kill())
  logoTween?.kill()
})
</script>

<template>
  <div class="pill-nav relative z-[1000] w-full md:w-auto">
    <nav
      class="box-border flex w-full items-center justify-between md:w-max md:justify-start"
      :class="mobileMenu ? 'px-4 md:px-0' : ''"
      aria-label="منوی اصلی"
      :style="cssVars"
    >
      <NuxtLink
        v-if="logo"
        ref="logoRef"
        :to="items[0]?.href || '/'"
        :external="isExternalLink(items[0]?.href || '/')"
        aria-label="خانه"
        class="inline-flex items-center justify-center overflow-hidden rounded-full p-2"
        :style="{ width: 'var(--nav-h, 42px)', height: 'var(--nav-h, 42px)', background: 'var(--base, #000)' }"
        @mouseenter="handleLogoEnter"
      >
        <img ref="logoImgRef" :src="logo" :alt="logoAlt" class="block h-full w-full object-cover">
      </NuxtLink>

      <div
        ref="navItemsRef"
        class="pill-nav__track relative items-center rounded-full"
        :class="[mobileMenu ? 'hidden md:flex' : 'flex', logo ? 'ms-2' : '']"
        :style="{ height: 'var(--nav-h, 42px)' }"
      >
        <ul class="m-0 flex h-full list-none items-stretch p-[3px]" :style="{ gap: 'var(--pill-gap, 3px)' }">
          <li v-for="(item, i) in items" :key="item.href" class="flex h-full">
            <NuxtLink
              :to="item.href"
              :external="isExternalLink(item.href)"
              class="pill relative box-border inline-flex h-full cursor-pointer items-center justify-center overflow-hidden whitespace-nowrap rounded-full no-underline"
              :class="{ 'pill--active': activeHref === item.href }"
              :aria-label="item.ariaLabel || item.label"
              :aria-current="activeHref === item.href ? 'page' : undefined"
              @mouseenter="handleEnter(i)"
              @mouseleave="handleLeave(i)"
              @focus="handleEnter(i)"
              @blur="handleLeave(i)"
            >
              <span
                :ref="el => setCircleRef(i, el)"
                class="hover-circle pointer-events-none absolute bottom-0 left-1/2 z-[1] block rounded-full"
                aria-hidden="true"
              />
              <span class="label-stack relative z-[2] inline-block leading-[1]">
                <span class="pill-label relative z-[2] inline-block leading-[1]">{{ item.label }}</span>
                <span class="pill-label-hover absolute top-0 left-0 z-[3] inline-block" aria-hidden="true">
                  {{ item.label }}
                </span>
              </span>
              <span
                v-if="activeHref === item.href"
                class="pill__dot absolute left-1/2 z-[4] -translate-x-1/2 rounded-full"
                aria-hidden="true"
              />
            </NuxtLink>
          </li>
        </ul>
      </div>

      <button
        v-if="mobileMenu"
        ref="hamburgerRef"
        type="button"
        aria-label="باز و بسته کردن منو"
        :aria-expanded="isMobileMenuOpen"
        class="relative flex cursor-pointer flex-col items-center justify-center gap-1 rounded-full border-0 p-0 md:hidden"
        :style="{ width: 'var(--nav-h, 42px)', height: 'var(--nav-h, 42px)', background: 'var(--base, #000)' }"
        @click="toggleMobileMenu"
      >
        <span class="hamburger-line h-0.5 w-4 origin-center rounded" :style="{ background: 'var(--pill-bg, #fff)' }" />
        <span class="hamburger-line h-0.5 w-4 origin-center rounded" :style="{ background: 'var(--pill-bg, #fff)' }" />
      </button>
    </nav>

    <div
      v-if="mobileMenu"
      ref="mobileMenuRef"
      class="pill-nav__mobile absolute top-[3em] right-4 left-4 z-[998] origin-top rounded-[27px] md:hidden"
      :style="{ ...cssVars, background: 'var(--base, #f0f0f0)' }"
    >
      <ul class="m-0 flex list-none flex-col gap-[3px] p-[3px]">
        <li v-for="item in items" :key="item.href">
          <NuxtLink
            :to="item.href"
            :external="isExternalLink(item.href)"
            class="pill-nav__mobile-link block rounded-[50px] px-4 py-3 text-[16px] font-medium"
            :aria-current="activeHref === item.href ? 'page' : undefined"
            @click="setMobileMenu(false)"
          >
            {{ item.label }}
          </NuxtLink>
        </li>
      </ul>
    </div>
  </div>
</template>

<style scoped>
/* Size knobs (--nav-h, --pill-pad-x, --pill-gap, --pill-font-size) are read
   with fallbacks, not declared here, so a host class can set them without a
   specificity fight against this scoped block.
   Optional colour knobs (fallbacks keep the React Bits look): --track-bg and
   --track-border paint the rail, --pill-active-bg / --pill-active-text the
   current page's pill, --dot-bg / --dot-size / --dot-offset its marker dot. */
.pill-nav__track {
  background: var(--track-bg, var(--base, #000));
  box-shadow: inset 0 0 0 1px var(--track-border, transparent);
}

.pill {
  padding-inline: var(--pill-pad-x, 18px);
  background: var(--pill-bg, #fff);
  color: var(--pill-text, var(--base, #000));
  font-size: var(--pill-font-size, 16px);
  font-weight: 600;
  line-height: 0;
  letter-spacing: 0.2px;
  text-transform: uppercase;
}

.pill--active {
  background: var(--pill-active-bg, var(--pill-bg, #fff));
  color: var(--pill-active-text, var(--pill-text, var(--base, #000)));
}

.pill__dot {
  bottom: var(--dot-offset, -6px);
  width: var(--dot-size, 12px);
  height: var(--dot-size, 12px);
  background: var(--dot-bg, var(--base, #000));
}

.pill:focus-visible {
  outline: 2px solid var(--base, #000);
  outline-offset: 2px;
}

/* Hidden until gsap lays them out, so nothing flashes before it loads. */
.hover-circle {
  opacity: 0;
  background: var(--base, #000);
  will-change: transform;
}

.pill-label {
  will-change: transform;
}

.pill-label-hover {
  opacity: 0;
  color: var(--hover-text, #fff);
  will-change: transform, opacity;
}

.pill-nav__mobile {
  visibility: hidden;
  opacity: 0;
}

.pill-nav__mobile-link {
  background: var(--pill-bg, #fff);
  color: var(--pill-text, #fff);
  transition: background-color 200ms cubic-bezier(0.25, 0.1, 0.25, 1), color 200ms cubic-bezier(0.25, 0.1, 0.25, 1);
}

.pill-nav__mobile-link:hover,
.pill-nav__mobile-link:focus-visible {
  background: var(--base);
  color: var(--hover-text, #fff);
}

/* Reduced motion: no tweens run, so hover is a plain colour swap. */
@media (prefers-reduced-motion: reduce) {
  .pill:hover,
  .pill:focus-visible {
    background: var(--base, #000);
    color: var(--hover-text, #fff);
  }
}
</style>
