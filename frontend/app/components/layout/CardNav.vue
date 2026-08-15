<script setup lang="ts">
import { gsap } from 'gsap'

export type CardNavLink = {
  label: string
  href: string
  ariaLabel: string
}

export type CardNavItem = {
  label: string
  bgColor: string
  textColor: string
  links: CardNavLink[]
}

const props = withDefaults(defineProps<{
  logo?: string
  logoAlt?: string
  items: CardNavItem[]
  className?: string
  ease?: string
  baseColor?: string
  menuColor?: string
  buttonBgColor?: string
  buttonTextColor?: string
  ctaLabel?: string
  ctaTo?: string
  /**
   * `floating` = React Bits absolute header bar.
   * `dropdown` = safe panel for sticky headers (no absolute shell).
   */
  variant?: 'floating' | 'dropdown'
  /** Hide logo / hamburger / CTA when a parent trigger owns open state. */
  hideChrome?: boolean
}>(), {
  logo: '/assets/brand/logo.svg',
  logoAlt: 'لوگو',
  className: '',
  ease: 'power3.out',
  baseColor: 'color-mix(in srgb, var(--theme-bg-surface) 96%, transparent)',
  menuColor: 'var(--theme-text-primary)',
  buttonBgColor: '#2a2a2e',
  buttonTextColor: '#f4f4f5',
  ctaLabel: 'شروع کنید',
  ctaTo: '/movies',
  variant: 'dropdown',
  hideChrome: false,
})

const open = defineModel<boolean>('open', { default: false })
const emit = defineEmits<{
  select: [href?: string]
}>()

const navRef = useTemplateRef<HTMLElement>('nav')
const cardsRef = shallowRef<HTMLElement[]>([])
const isHamburgerOpen = ref(false)
const isExpanded = ref(false)

let tl: gsap.core.Timeline | null = null
let reduceMotion = false

/** Parent owns chrome + scroll; avoid GSAP height fights with responsive sheets. */
const isPanelMode = computed(() => props.hideChrome && props.variant === 'dropdown')

const visibleItems = computed(() => (props.items || []).slice(0, 3))

function setCardRef(el: Element | null, idx: number) {
  if (!el) return
  const next = cardsRef.value.slice()
  next[idx] = el as HTMLElement
  cardsRef.value = next
}

function calculateHeight() {
  const navEl = navRef.value
  if (!navEl) return props.hideChrome ? 220 : 260

  const isMobile = window.matchMedia('(max-width: 1023px)').matches
  if (isMobile || props.variant === 'dropdown') {
    const contentEl = navEl.querySelector('.card-nav-content') as HTMLElement | null
    if (contentEl) {
      const prev = {
        visibility: contentEl.style.visibility,
        pointerEvents: contentEl.style.pointerEvents,
        position: contentEl.style.position,
        height: contentEl.style.height,
      }
      contentEl.style.visibility = 'visible'
      contentEl.style.pointerEvents = 'auto'
      contentEl.style.position = 'static'
      contentEl.style.height = 'auto'
      contentEl.offsetHeight
      const topBar = props.hideChrome ? 0 : 60
      const padding = props.hideChrome ? 8 : 16
      const contentHeight = contentEl.scrollHeight
      contentEl.style.visibility = prev.visibility
      contentEl.style.pointerEvents = prev.pointerEvents
      contentEl.style.position = prev.position
      contentEl.style.height = prev.height
      return topBar + contentHeight + padding
    }
  }
  return props.hideChrome ? 220 : 260
}

function createTimeline() {
  const navEl = navRef.value
  if (!navEl || isPanelMode.value) return null

  const collapsed = props.hideChrome ? 0 : 60
  gsap.set(navEl, { height: collapsed, overflow: 'hidden' })
  gsap.set(cardsRef.value.filter(Boolean), { y: 36, opacity: 0 })

  const timeline = gsap.timeline({ paused: true })
  timeline.to(navEl, {
    height: calculateHeight,
    duration: 0.4,
    ease: props.ease,
  })
  timeline.to(
    cardsRef.value.filter(Boolean),
    { y: 0, opacity: 1, duration: 0.4, ease: props.ease, stagger: 0.08 },
    '-=0.1',
  )
  return timeline
}

function rebuildTimeline(progress = 0) {
  tl?.kill()
  tl = createTimeline()
  if (tl && progress > 0) tl.progress(progress)
}

function animatePanelCards() {
  const cards = cardsRef.value.filter(Boolean)
  if (!cards.length || reduceMotion) {
    gsap.set(cards, { clearProps: 'transform,opacity' })
    return
  }
  gsap.fromTo(
    cards,
    { y: 14, opacity: 0 },
    { y: 0, opacity: 1, duration: 0.32, ease: props.ease, stagger: 0.055, clearProps: 'transform' },
  )
}

function playOpen() {
  isHamburgerOpen.value = true
  isExpanded.value = true
  if (isPanelMode.value) {
    nextTick(() => animatePanelCards())
    return
  }
  if (!tl) rebuildTimeline(0)
  tl?.play(0)
}

function playClose() {
  if (isPanelMode.value) {
    isHamburgerOpen.value = false
    isExpanded.value = false
    return
  }
  if (!tl) {
    isHamburgerOpen.value = false
    isExpanded.value = false
    return
  }
  isHamburgerOpen.value = false
  tl.eventCallback('onReverseComplete', () => {
    isExpanded.value = false
  })
  tl.reverse()
}

function toggleMenu() {
  open.value = !open.value
}

function onSelect(href?: string) {
  emit('select', href)
  open.value = false
}

watch(open, async (value) => {
  if (value) {
    await nextTick()
    if (!isPanelMode.value) rebuildTimeline(0)
    playOpen()
  }
  else if (isExpanded.value || isHamburgerOpen.value) {
    playClose()
  }
})

watch(() => [props.ease, props.items, props.hideChrome, props.variant] as const, async () => {
  await nextTick()
  if (isPanelMode.value) {
    if (open.value) {
      isExpanded.value = true
      isHamburgerOpen.value = true
      animatePanelCards()
    }
    return
  }
  rebuildTimeline(open.value ? 1 : 0)
  if (open.value) {
    isExpanded.value = true
    isHamburgerOpen.value = true
  }
})

onMounted(async () => {
  reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches
  await nextTick()
  if (isPanelMode.value) {
    if (open.value) playOpen()
    return
  }
  rebuildTimeline(0)
  if (open.value) playOpen()
})

onBeforeUnmount(() => {
  tl?.kill()
  tl = null
})

useEventListener(window, 'resize', () => {
  if (isPanelMode.value || !tl) return
  if (isExpanded.value) {
    gsap.set(navRef.value, { height: calculateHeight() })
    rebuildTimeline(1)
  }
  else {
    rebuildTimeline(0)
  }
})
</script>

<template>
  <div
    class="card-nav-shell"
    :class="[
      variant === 'floating' && 'card-nav-shell--floating',
      variant === 'dropdown' && 'card-nav-shell--dropdown',
      isPanelMode && 'card-nav-shell--panel',
      className,
    ]"
  >
    <nav
      ref="nav"
      class="card-nav"
      :class="isExpanded && 'card-nav--open'"
      :style="isPanelMode ? undefined : { backgroundColor: baseColor }"
      :aria-label="hideChrome ? undefined : 'ناوبری کارت‌ها'"
    >
      <div
        v-if="!hideChrome"
        class="card-nav-top"
      >
        <div
          class="hamburger-menu"
          :class="isHamburgerOpen && 'hamburger-menu--open'"
          role="button"
          tabindex="0"
          :aria-label="isExpanded ? 'بستن منو' : 'باز کردن منو'"
          :aria-expanded="isExpanded"
          :style="{ color: menuColor || '#000' }"
          @click="toggleMenu"
          @keydown.enter.prevent="toggleMenu"
          @keydown.space.prevent="toggleMenu"
        >
          <span
            class="hamburger-line"
            :class="isHamburgerOpen && 'hamburger-line--top-open'"
          />
          <span
            class="hamburger-line"
            :class="isHamburgerOpen && 'hamburger-line--bottom-open'"
          />
        </div>

        <div class="logo-container">
          <img :src="logo" :alt="logoAlt" class="logo" width="110" height="28">
        </div>

        <NuxtLink
          class="card-nav-cta-button"
          :to="ctaTo"
          :style="{ backgroundColor: buttonBgColor, color: buttonTextColor }"
          @click="onSelect()"
        >
          {{ ctaLabel }}
        </NuxtLink>
      </div>

      <div
        class="card-nav-content"
        :class="[
          isExpanded ? 'card-nav-content--open' : 'card-nav-content--closed',
          hideChrome && 'card-nav-content--flush',
        ]"
        :aria-hidden="!isExpanded"
      >
        <div
          v-for="(item, idx) in visibleItems"
          :key="`${item.label}-${idx}`"
          :ref="(el) => setCardRef(el as Element | null, idx)"
          class="nav-card"
          :style="{ backgroundColor: item.bgColor, color: item.textColor }"
        >
          <div class="nav-card-label">
            {{ item.label }}
          </div>
          <div class="nav-card-links">
            <NuxtLink
              v-for="(lnk, i) in item.links"
              :key="`${lnk.label}-${i}`"
              class="nav-card-link"
              :to="lnk.href"
              :aria-label="lnk.ariaLabel"
              @click="onSelect(lnk.href)"
            >
              <CinematicIcon name="arrow-up-right" class="nav-card-link-icon size-3.5 shrink-0" />
              <span class="truncate">{{ lnk.label }}</span>
            </NuxtLink>
          </div>
        </div>
      </div>
    </nav>
  </div>
</template>

<style scoped>
.card-nav-shell--floating {
  position: absolute;
  top: 1.2em;
  left: 50%;
  z-index: 99;
  width: 90%;
  max-width: 800px;
  transform: translateX(-50%);
}

@media (min-width: 768px) {
  .card-nav-shell--floating {
    top: 2em;
  }
}

.card-nav-shell--dropdown {
  position: relative;
  width: 100%;
}

.card-nav {
  position: relative;
  display: block;
  height: 60px;
  overflow: hidden;
  border-radius: 0.9rem;
  box-shadow: 0 10px 28px rgb(0 0 0 / 22%);
  will-change: height;
}

.card-nav-shell--dropdown .card-nav {
  box-shadow: none;
  background: transparent !important;
}

.card-nav-shell--panel .card-nav {
  height: auto !important;
  overflow: visible;
  border-radius: 0;
  will-change: auto;
}

.card-nav-shell--panel .card-nav:not(.card-nav--open) {
  height: 0 !important;
  overflow: hidden;
}

.card-nav-top {
  position: absolute;
  inset-inline: 0;
  top: 0;
  z-index: 2;
  display: flex;
  height: 60px;
  align-items: center;
  justify-content: space-between;
  padding: 0.5rem 0.5rem 0.5rem 1.1rem;
}

.hamburger-menu {
  display: flex;
  height: 100%;
  cursor: pointer;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 6px;
  order: 2;
}

@media (min-width: 768px) {
  .hamburger-menu {
    order: 0;
  }
}

.hamburger-line {
  width: 30px;
  height: 2px;
  background: currentColor;
  transform-origin: 50% 50%;
  transition: transform 300ms linear, opacity 300ms linear, margin 300ms linear;
}

.hamburger-line--top-open {
  transform: translateY(4px) rotate(45deg);
}

.hamburger-line--bottom-open {
  transform: translateY(-4px) rotate(-45deg);
}

.hamburger-menu:hover .hamburger-line {
  opacity: 0.75;
}

.logo-container {
  display: flex;
  align-items: center;
  order: 1;
}

@media (min-width: 768px) {
  .logo-container {
    position: absolute;
    top: 50%;
    left: 50%;
    order: 0;
    transform: translate(-50%, -50%);
  }
}

.logo {
  display: block;
  height: 36px;
  width: auto;
  object-fit: contain;
}

.card-nav-cta-button {
  display: none;
  height: 100%;
  align-items: center;
  border: 0;
  border-radius: calc(0.75rem - 0.2rem);
  padding-inline: 1rem;
  font-weight: 600;
  text-decoration: none;
  transition: filter 200ms ease;
}

.card-nav-cta-button:hover {
  filter: brightness(1.06);
}

@media (min-width: 768px) {
  .card-nav-cta-button {
    display: inline-flex;
  }
}

.card-nav-content {
  position: absolute;
  inset-inline: 0;
  top: 60px;
  bottom: 0;
  z-index: 1;
  display: flex;
  flex-direction: column;
  align-items: stretch;
  justify-content: flex-start;
  gap: 0.4rem;
  padding: 0.5rem;
}

.card-nav-content--flush {
  top: 0;
  padding: 0;
  gap: 0.45rem;
}

.card-nav-shell--panel .card-nav-content {
  position: static;
  inset: auto;
  height: auto;
}

.card-nav-content--closed {
  visibility: hidden;
  pointer-events: none;
}

.card-nav-content--open {
  visibility: visible;
  pointer-events: auto;
}

.card-nav-shell--dropdown .card-nav-content {
  flex-direction: column;
}

@media (min-width: 1024px) {
  .card-nav-shell--dropdown .card-nav-content {
    flex-direction: row;
    align-items: stretch;
    gap: 0.55rem;
  }
}

@media (min-width: 768px) {
  .card-nav-shell--floating .card-nav-content {
    flex-direction: row;
    align-items: stretch;
    gap: 12px;
  }
}

.nav-card {
  position: relative;
  display: flex;
  min-width: 0;
  min-height: 3.25rem;
  flex: 1 1 auto;
  user-select: none;
  flex-direction: column;
  gap: 0.4rem;
  border: 1px solid rgb(255 255 255 / 6%);
  border-radius: 0.85rem;
  padding: 0.75rem 0.85rem;
}

@media (min-width: 1024px) {
  .card-nav-shell--dropdown .nav-card {
    min-height: 0;
    flex: 1 1 0%;
    height: 100%;
    padding: 0.9rem 1rem;
  }
}

@media (min-width: 768px) {
  .card-nav-shell--floating .nav-card {
    min-height: 0;
    flex: 1 1 0%;
    height: 100%;
  }
}

.nav-card-label {
  font-size: 0.8125rem;
  font-weight: 700;
  letter-spacing: -0.01em;
  color: inherit;
  opacity: 0.72;
}

@media (min-width: 640px) {
  .nav-card-label {
    font-size: 0.9rem;
  }
}

@media (min-width: 1024px) {
  .nav-card-label {
    font-size: 0.95rem;
    opacity: 0.8;
  }
}

.nav-card-links {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0.15rem 0.45rem;
  margin-top: auto;
}

@media (min-width: 1024px) {
  .card-nav-shell--dropdown .nav-card-links {
    display: flex;
    flex-direction: column;
    gap: 1px;
  }
}

.card-nav-shell--floating .nav-card-links {
  display: flex;
  flex-direction: column;
  gap: 1px;
}

.nav-card-link {
  display: inline-flex;
  max-width: 100%;
  align-items: center;
  gap: 0.35rem;
  min-height: 2.5rem;
  padding-inline: 0.2rem;
  border-radius: 0.5rem;
  color: inherit;
  font-size: 0.8125rem;
  font-weight: 600;
  text-decoration: none;
  opacity: 0.9;
  transition: opacity 160ms ease, background-color 160ms ease;
}

.nav-card-link:hover,
.nav-card-link:focus-visible {
  opacity: 1;
  background: rgb(255 255 255 / 6%);
  outline: none;
}

.nav-card-link:focus-visible {
  box-shadow: inset 0 0 0 1px rgb(255 255 255 / 18%);
}

.nav-card-link-icon {
  opacity: 0.65;
}

@media (max-width: 379px) {
  .nav-card {
    padding: 0.65rem 0.7rem;
  }

  .nav-card-link {
    min-height: 2.35rem;
    font-size: 0.78rem;
  }
}

@media (min-width: 1024px) {
  .nav-card-link {
    min-height: 2rem;
    font-size: 0.875rem;
    font-weight: 500;
  }
}

@media (prefers-reduced-motion: reduce) {
  .card-nav,
  .hamburger-line,
  .nav-card-link {
    transition: none !important;
  }
}
</style>
