<script setup lang="ts">
import { gsap } from 'gsap'
import type { CinematicIconName } from '~/types'

export interface StaggeredMenuItem {
  label: string
  ariaLabel: string
  link: string
  icon?: CinematicIconName
  exact?: boolean
}

export interface StaggeredMenuSocialItem {
  label: string
  link: string
  icon?: CinematicIconName
}

const props = withDefaults(defineProps<{
  position?: 'left' | 'right'
  colors?: string[]
  items?: StaggeredMenuItem[]
  socialItems?: StaggeredMenuSocialItem[]
  displaySocials?: boolean
  displayItemNumbering?: boolean
  className?: string
  logoUrl?: string
  menuButtonColor?: string
  openMenuButtonColor?: string
  accentColor?: string
  isFixed?: boolean
  changeMenuColorOnOpen?: boolean
  closeOnClickAway?: boolean
  /** Hide built-in logo + toggle when the parent header owns the trigger. */
  hideChrome?: boolean
  openLabel?: string
  closeLabel?: string
  socialsTitle?: string
}>(), {
  position: 'right',
  colors: () => ['#285a48', '#b0e4cc'],
  items: () => [],
  socialItems: () => [],
  displaySocials: true,
  displayItemNumbering: true,
  className: '',
  logoUrl: '/assets/brand/logo.svg',
  menuButtonColor: '#fff',
  openMenuButtonColor: '#17211c',
  accentColor: '#b0e4cc',
  isFixed: true,
  changeMenuColorOnOpen: true,
  closeOnClickAway: true,
  hideChrome: false,
  openLabel: 'منو',
  closeLabel: 'بستن',
  socialsTitle: 'پیوندها',
})

const open = defineModel<boolean>('open', { default: false })
const route = useRoute()

const emit = defineEmits<{
  menuOpen: []
  menuClose: []
}>()

const panelRef = useTemplateRef<HTMLElement>('panel')
const preLayersRef = useTemplateRef<HTMLElement>('preLayers')
const plusHRef = useTemplateRef<HTMLElement>('plusH')
const plusVRef = useTemplateRef<HTMLElement>('plusV')
const iconRef = useTemplateRef<HTMLElement>('icon')
const textInnerRef = useTemplateRef<HTMLElement>('textInner')
const toggleBtnRef = useTemplateRef<HTMLButtonElement>('toggleBtn')

const textLines = ref<string[]>([props.openLabel, props.closeLabel])
const preLayerEls = shallowRef<HTMLElement[]>([])
const busy = ref(false)
const openRef = ref(false)

let openTl: gsap.core.Timeline | null = null
let closeTween: gsap.core.Tween | null = null
let spinTween: gsap.core.Timeline | null = null
let textCycleAnim: gsap.core.Tween | null = null
let colorTween: gsap.core.Tween | null = null

const layerColors = computed(() => {
  const raw = (props.colors?.length ? props.colors.slice(0, 4) : ['#1e1e22', '#35353c'])
  const arr = [...raw]
  if (arr.length >= 3) {
    arr.splice(Math.floor(arr.length / 2), 1)
  }
  return arr
})

const slideClosed = computed(() => (
  props.position === 'left' ? 'translate3d(-100%,0,0)' : 'translate3d(100%,0,0)'
))

function isActive(item: StaggeredMenuItem) {
  const path = item.link.split(/[?#]/, 1)[0] || '/'
  if (item.exact || path === '/') return route.path === path
  return route.path === path || route.path.startsWith(`${path}/`)
}

function syncLayerEls() {
  const preContainer = preLayersRef.value
  preLayerEls.value = preContainer
    ? Array.from(preContainer.querySelectorAll('.sm-prelayer')) as HTMLElement[]
    : []
}

onMounted(async () => {
  if (!import.meta.client) return
  await nextTick()
  const ctx = gsap.context(() => {
    const panel = panelRef.value
    if (!panel) return

    syncLayerEls()

    const plusH = plusHRef.value
    const plusV = plusVRef.value
    const icon = iconRef.value
    const textInner = textInnerRef.value
    if (plusH && plusV && icon) {
      gsap.set(plusH, { transformOrigin: '50% 50%', rotate: 0 })
      gsap.set(plusV, { transformOrigin: '50% 50%', rotate: 90 })
      gsap.set(icon, { rotate: 0, transformOrigin: '50% 50%' })
    }
    if (textInner) gsap.set(textInner, { yPercent: 0 })
    if (toggleBtnRef.value) gsap.set(toggleBtnRef.value, { color: props.menuButtonColor })

    const itemEls = Array.from(panel.querySelectorAll('.sm-panel-itemLabel')) as HTMLElement[]
    if (itemEls.length) gsap.set(itemEls, { yPercent: 140, rotate: 8 })
  })
  onBeforeUnmount(() => ctx.revert())
})

watch(() => [props.menuButtonColor, props.position] as const, () => {
  if (toggleBtnRef.value && !props.changeMenuColorOnOpen && !openRef.value) {
    gsap.set(toggleBtnRef.value, { color: props.menuButtonColor })
  }
})

function buildOpenTimeline() {
  const panel = panelRef.value
  if (!panel) return null

  openTl?.kill()
  closeTween?.kill()
  closeTween = null

  const itemEls = Array.from(panel.querySelectorAll('.sm-panel-itemLabel')) as HTMLElement[]
  const numberEls = Array.from(
    panel.querySelectorAll('.sm-panel-list[data-numbering] .sm-panel-item'),
  ) as HTMLElement[]
  const socialTitle = panel.querySelector('.sm-socials-title') as HTMLElement | null
  const socialLinks = Array.from(panel.querySelectorAll('.sm-socials-link')) as HTMLElement[]
  const headEls = Array.from(panel.querySelectorAll('.sm-panel-head > *')) as HTMLElement[]

  if (itemEls.length) gsap.set(itemEls, { yPercent: 140, rotate: 8 })
  if (numberEls.length) gsap.set(numberEls, { '--sm-num-opacity': 0 })
  if (socialTitle) gsap.set(socialTitle, { opacity: 0 })
  if (socialLinks.length) gsap.set(socialLinks, { y: 18, opacity: 0 })
  if (headEls.length) gsap.set(headEls, { y: -10, opacity: 0 })

  const tl = gsap.timeline({ paused: true })
  const itemsStart = 0.16

  if (headEls.length) {
    tl.to(headEls, { y: 0, opacity: 1, duration: 0.4, ease: 'power3.out', stagger: 0.06 }, 0.05)
  }

  if (itemEls.length) {
    tl.to(
      itemEls,
      { yPercent: 0, rotate: 0, duration: 0.85, ease: 'power4.out', stagger: { each: 0.07, from: 'start' } },
      itemsStart,
    )
    if (numberEls.length) {
      tl.to(
        numberEls,
        { duration: 0.5, ease: 'power2.out', '--sm-num-opacity': 1, stagger: { each: 0.06, from: 'start' } },
        itemsStart + 0.08,
      )
    }
  }

  if (socialTitle || socialLinks.length) {
    const socialsStart = itemsStart + 0.28
    if (socialTitle) tl.to(socialTitle, { opacity: 1, duration: 0.4, ease: 'power2.out' }, socialsStart)
    if (socialLinks.length) {
      tl.to(
        socialLinks,
        {
          y: 0,
          opacity: 1,
          duration: 0.45,
          ease: 'power3.out',
          stagger: { each: 0.06, from: 'start' },
          onComplete: () => gsap.set(socialLinks, { clearProps: 'opacity' }),
        },
        socialsStart + 0.04,
      )
    }
  }

  openTl = tl
  return tl
}

function playOpen() {
  busy.value = true
  const tl = buildOpenTimeline()
  if (!tl) {
    busy.value = false
    return
  }
  if (tl.getChildren().length === 0) {
    busy.value = false
    return
  }
  tl.eventCallback('onComplete', () => {
    busy.value = false
  })
  tl.play(0)
}

function playClose() {
  openTl?.kill()
  openTl = null
  const panel = panelRef.value
  if (!panel) {
    busy.value = false
    return
  }

  const itemEls = Array.from(panel.querySelectorAll('.sm-panel-itemLabel')) as HTMLElement[]
  if (itemEls.length) gsap.set(itemEls, { yPercent: 140, rotate: 8 })
  const numberEls = Array.from(
    panel.querySelectorAll('.sm-panel-list[data-numbering] .sm-panel-item'),
  ) as HTMLElement[]
  if (numberEls.length) gsap.set(numberEls, { '--sm-num-opacity': 0 })
  const socialTitle = panel.querySelector('.sm-socials-title') as HTMLElement | null
  const socialLinks = Array.from(panel.querySelectorAll('.sm-socials-link')) as HTMLElement[]
  if (socialTitle) gsap.set(socialTitle, { opacity: 0 })
  if (socialLinks.length) gsap.set(socialLinks, { y: 18, opacity: 0 })
  busy.value = false
}

function animateIcon(opening: boolean) {
  const icon = iconRef.value
  const h = plusHRef.value
  const v = plusVRef.value
  if (!icon || !h || !v) return
  spinTween?.kill()
  if (opening) {
    gsap.set(icon, { rotate: 0, transformOrigin: '50% 50%' })
    spinTween = gsap.timeline({ defaults: { ease: 'power4.out' } })
      .to(h, { rotate: 45, duration: 0.5 }, 0)
      .to(v, { rotate: -45, duration: 0.5 }, 0)
  }
  else {
    spinTween = gsap.timeline({ defaults: { ease: 'power3.inOut' } })
      .to(h, { rotate: 0, duration: 0.35 }, 0)
      .to(v, { rotate: 90, duration: 0.35 }, 0)
      .to(icon, { rotate: 0, duration: 0.001 }, 0)
  }
}

function animateColor(opening: boolean) {
  const btn = toggleBtnRef.value
  if (!btn) return
  colorTween?.kill()
  if (props.changeMenuColorOnOpen) {
    colorTween = gsap.to(btn, {
      color: opening ? props.openMenuButtonColor : props.menuButtonColor,
      delay: 0.18,
      duration: 0.3,
      ease: 'power2.out',
    })
  }
  else {
    gsap.set(btn, { color: props.menuButtonColor })
  }
}

function animateText(opening: boolean) {
  const inner = textInnerRef.value
  if (!inner) return
  textCycleAnim?.kill()

  const currentLabel = opening ? props.openLabel : props.closeLabel
  const targetLabel = opening ? props.closeLabel : props.openLabel
  const seq: string[] = [currentLabel]
  let last = currentLabel
  for (let i = 0; i < 3; i++) {
    last = last === props.openLabel ? props.closeLabel : props.openLabel
    seq.push(last)
  }
  if (last !== targetLabel) seq.push(targetLabel)
  seq.push(targetLabel)
  textLines.value = seq
  gsap.set(inner, { yPercent: 0 })
  const finalShift = ((seq.length - 1) / seq.length) * 100
  textCycleAnim = gsap.to(inner, {
    yPercent: -finalShift,
    duration: 0.5 + seq.length * 0.07,
    ease: 'power4.out',
  })
}

async function setOpenState(target: boolean) {
  if (openRef.value === target) return
  openRef.value = target
  open.value = target
  if (import.meta.client) {
    document.documentElement.style.overflow = target ? 'hidden' : ''
  }
  animateIcon(target)
  animateColor(target)
  animateText(target)
  await nextTick()
  if (target) {
    emit('menuOpen')
    playOpen()
  }
  else {
    emit('menuClose')
    playClose()
  }
}

function toggleMenu() {
  setOpenState(!openRef.value)
}

function closeMenu() {
  setOpenState(false)
}

watch(open, (value) => {
  if (value === openRef.value) return
  setOpenState(value)
})

onMounted(() => {
  if (open.value) setOpenState(true)
})

onBeforeUnmount(() => {
  openTl?.kill()
  closeTween?.kill()
  spinTween?.kill()
  textCycleAnim?.kill()
  colorTween?.kill()
  if (import.meta.client) document.documentElement.style.overflow = ''
})

onKeyStroke('Escape', () => {
  if (openRef.value) closeMenu()
})

watch([() => props.closeOnClickAway, open], ([enabled, isOpen], _prev, onCleanup) => {
  if (!import.meta.client || !enabled || !isOpen) return
  let remove: (() => void) | undefined
  const timer = window.setTimeout(() => {
    const handlePointerDown = (event: PointerEvent) => {
      const target = event.target as HTMLElement | null
      if (!target) return
      if (panelRef.value?.contains(target)) return
      if (toggleBtnRef.value?.contains(target)) return
      if (target.closest?.('[data-staggered-menu-trigger]')) return
      closeMenu()
    }
    document.addEventListener('pointerdown', handlePointerDown)
    remove = () => document.removeEventListener('pointerdown', handlePointerDown)
  }, 0)
  onCleanup(() => {
    window.clearTimeout(timer)
    remove?.()
  })
})

defineExpose({ open: () => setOpenState(true), close: closeMenu, toggle: toggleMenu })
</script>

<template>
  <Teleport to="body" :disabled="!isFixed">
    <div
      class="sm-scope z-[70] pointer-events-none"
      :class="isFixed
        ? (open ? 'fixed inset-0 overflow-hidden' : 'fixed inset-y-0 end-0 w-0 overflow-hidden')
        : 'relative h-full w-full'"
      :aria-hidden="!open"
    >
      <button
        v-show="open"
        type="button"
        class="sm-backdrop pointer-events-auto absolute inset-0 z-[1] border-0 p-0"
        aria-label="بستن منو"
        @click="closeMenu"
      />

      <div
        class="staggered-menu-wrapper pointer-events-none relative z-40 h-full w-full"
        :class="className"
        :style="accentColor ? { '--sm-accent': accentColor } : undefined"
        :data-position="position"
        :data-open="open || undefined"
        :data-hide-chrome="hideChrome || undefined"
      >
        <div
          ref="preLayers"
          class="sm-prelayers pointer-events-none absolute inset-y-0 z-[5]"
          :class="position === 'left' ? 'left-0' : 'right-0'"
          aria-hidden="true"
        >
          <div
            v-for="(color, i) in layerColors"
            :key="i"
            class="sm-prelayer absolute inset-y-0 right-0 h-full w-full"
            :style="{
              background: color,
              transform: open ? 'translate3d(0,0,0)' : slideClosed,
              transitionDelay: open ? `${i * 55}ms` : '0ms',
            }"
          />
        </div>

        <header
          v-if="!hideChrome"
          class="staggered-menu-header pointer-events-none absolute inset-x-0 top-0 z-20 flex w-full items-center justify-between bg-transparent p-[1.25rem_1.25rem] sm:p-[2em]"
          aria-label="ناوبری اصلی"
        >
          <div class="sm-logo pointer-events-auto flex select-none items-center" aria-label="لوگو">
            <img
              :src="logoUrl"
              alt=""
              class="sm-logo-img block h-9 w-auto object-contain sm:h-10"
              draggable="false"
              width="40"
              height="40"
            >
          </div>

          <button
            ref="toggleBtn"
            type="button"
            class="sm-toggle pointer-events-auto relative inline-flex cursor-pointer items-center gap-[0.3rem] overflow-visible border-0 bg-transparent font-medium leading-none"
            :aria-label="open ? closeLabel : openLabel"
            :aria-expanded="open"
            aria-controls="staggered-menu-panel"
            @click="toggleMenu"
          >
            <span
              class="sm-toggle-textWrap relative inline-block h-[1em] min-w-[var(--sm-toggle-width,auto)] w-[var(--sm-toggle-width,auto)] overflow-hidden whitespace-nowrap"
              aria-hidden="true"
            >
              <span ref="textInner" class="sm-toggle-textInner flex flex-col leading-none">
                <span v-for="(line, i) in textLines" :key="`${line}-${i}`" class="sm-toggle-line block h-[1em] leading-none">
                  {{ line }}
                </span>
              </span>
            </span>
            <span
              ref="icon"
              class="sm-icon relative inline-flex h-[14px] w-[14px] shrink-0 items-center justify-center [will-change:transform]"
              aria-hidden="true"
            >
              <span ref="plusH" class="sm-icon-line absolute left-1/2 top-1/2 h-[2px] w-full -translate-x-1/2 -translate-y-1/2 rounded-[2px] bg-current [will-change:transform]" />
              <span ref="plusV" class="sm-icon-line sm-icon-line-v absolute left-1/2 top-1/2 h-[2px] w-full -translate-x-1/2 -translate-y-1/2 rounded-[2px] bg-current [will-change:transform]" />
            </span>
          </button>
        </header>

        <aside
          id="staggered-menu-panel"
          ref="panel"
          class="staggered-menu-panel absolute top-0 z-10 flex h-full flex-col"
          :class="[
            position === 'left' ? 'left-0' : 'right-0',
            open ? 'pointer-events-auto' : 'pointer-events-none',
          ]"
          :style="{
            transform: open ? 'translate3d(0,0,0)' : slideClosed,
            transitionDelay: open ? '90ms' : '0ms',
          }"
          role="dialog"
          aria-modal="true"
          aria-label="منوی اصلی"
          dir="rtl"
          :aria-hidden="!open"
        >
          <div class="sm-panel-inner soft-scrollbar flex min-h-0 flex-1 flex-col overflow-y-auto">
            <div class="sm-panel-head">
              <AppLogo class="sm-panel-brand" :compact-on-mobile="false" @click="closeMenu" />
              <button
                type="button"
                class="sm-panel-close"
                aria-label="بستن منو"
                @click="closeMenu"
              >
                <CinematicIcon name="x" class="size-5" />
              </button>
            </div>

            <p class="sm-panel-kicker">
              کاوش در روایتو
            </p>

            <ul
              class="sm-panel-list"
              role="list"
              :data-numbering="displayItemNumbering || undefined"
            >
              <li
                v-for="(item, idx) in items"
                :key="`${item.label}-${idx}`"
                class="sm-panel-itemWrap"
              >
                <NuxtLink
                  class="sm-panel-item"
                  :class="isActive(item) && 'sm-panel-item--active'"
                  :to="item.link"
                  :aria-label="item.ariaLabel"
                  :aria-current="isActive(item) ? 'page' : undefined"
                  :data-index="idx + 1"
                  @click="closeMenu"
                >
                  <span v-if="item.icon" class="sm-panel-itemIcon" aria-hidden="true">
                    <CinematicIcon
                      :name="item.icon"
                      class="size-[1.05em]"
                      :stroke-width="isActive(item) ? 2.1 : 1.7"
                    />
                  </span>
                  <span class="sm-panel-itemLabel">
                    {{ item.label }}
                  </span>
                </NuxtLink>
              </li>
              <li
                v-if="!items.length"
                class="sm-panel-itemWrap"
                aria-hidden="true"
              >
                <span class="sm-panel-item">
                  <span class="sm-panel-itemLabel">خالی</span>
                </span>
              </li>
            </ul>

            <div
              v-if="displaySocials && socialItems.length"
              class="sm-socials"
              aria-label="پیوندهای مرتبط"
            >
              <h3 class="sm-socials-title">
                {{ socialsTitle }}
              </h3>
              <ul class="sm-socials-list" role="list">
                <li v-for="(social, i) in socialItems" :key="`${social.label}-${i}`" class="sm-socials-item">
                  <NuxtLink
                    class="sm-socials-link"
                    :class="!social.icon && 'sm-socials-link--text'"
                    :to="social.link"
                    :aria-label="social.label"
                    :title="social.label"
                    @click="closeMenu"
                  >
                    <CinematicIcon
                      v-if="social.icon"
                      :name="social.icon"
                      class="size-5"
                    />
                    <span v-else>{{ social.label }}</span>
                  </NuxtLink>
                </li>
              </ul>
            </div>
          </div>
        </aside>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.sm-backdrop {
  background:
    radial-gradient(ellipse 80% 55% at 50% 0%, rgb(176 228 204 / 10%), transparent 55%),
    rgb(5 8 7 / 55%);
  -webkit-backdrop-filter: blur(2px);
  backdrop-filter: blur(2px);
  opacity: 0;
  animation: sm-backdrop-in 280ms ease forwards;
}

@keyframes sm-backdrop-in {
  to { opacity: 1; }
}

:global(html[data-theme="light"] .sm-backdrop) {
  background:
    radial-gradient(ellipse 80% 55% at 50% 0%, rgb(23 107 80 / 12%), transparent 55%),
    rgb(20 35 28 / 28%);
}

.staggered-menu-panel,
.sm-prelayer {
  transition: transform 0.55s cubic-bezier(0.16, 1, 0.3, 1);
  will-change: transform;
}

.staggered-menu-wrapper:not([data-open]) .staggered-menu-panel,
.staggered-menu-wrapper:not([data-open]) .sm-prelayer {
  transition-duration: 0.32s;
  transition-timing-function: cubic-bezier(0.55, 0, 0.85, 0.45);
}

.sm-prelayers,
.staggered-menu-panel {
  width: min(22rem, calc(100dvw - 0.75rem));
}

.staggered-menu-panel {
  padding-top: env(safe-area-inset-top, 0px);
  padding-bottom: env(safe-area-inset-bottom, 0px);
  border-inline-start: 1px solid color-mix(in srgb, var(--theme-border) 50%, transparent);
  background:
    linear-gradient(
      165deg,
      color-mix(in srgb, var(--theme-accent-primary) 10%, var(--theme-bg-surface)) 0%,
      var(--theme-bg-surface) 9rem,
      color-mix(in srgb, var(--theme-bg-elevated) 92%, black) 100%
    );
  box-shadow: -16px 0 48px rgb(0 0 0 / 34%);
  -webkit-backdrop-filter: blur(16px) saturate(120%);
  backdrop-filter: blur(16px) saturate(120%);
}

:global(html[data-theme="light"] .staggered-menu-panel) {
  background:
    radial-gradient(circle at 100% 0, rgb(23 107 80 / 12%), transparent 14rem),
    linear-gradient(180deg, #f7fbf8, var(--theme-bg-surface) 8rem);
  border-inline-start-color: var(--theme-border);
  box-shadow: -18px 0 48px rgb(23 50 38 / 14%);
}

.sm-panel-inner {
  gap: 0.85rem;
  padding: 0.85rem 1rem 1.25rem;
}

.sm-panel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
  margin-bottom: 0.35rem;
}

.sm-panel-brand {
  min-width: 0;
}

.sm-panel-close {
  display: grid;
  flex: none;
  width: var(--touch-target);
  height: var(--touch-target);
  place-items: center;
  border-radius: 0.75rem;
  color: var(--theme-text-muted);
  transition: color 140ms ease, background-color 140ms ease;
}

.sm-panel-close:hover,
.sm-panel-close:focus-visible {
  background: color-mix(in srgb, var(--theme-bg-elevated) 70%, transparent);
  color: var(--theme-text-primary);
}

.sm-panel-kicker {
  margin: 0 0 0.35rem;
  font-size: 0.78rem;
  font-weight: 500;
  letter-spacing: 0.04em;
  color: color-mix(in srgb, var(--sm-accent, var(--theme-accent-primary)) 75%, var(--theme-text-muted));
}

.sm-panel-list {
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: 0.2rem;
  margin: 0;
  padding: 0;
  list-style: none;
  counter-reset: smItem;
}

.sm-panel-itemWrap {
  position: relative;
  overflow: hidden;
  line-height: 1.1;
}

.sm-panel-item {
  position: relative;
  display: flex;
  align-items: center;
  gap: 0.7rem;
  width: 100%;
  min-height: 2.75rem;
  padding: 0.55rem 0.7rem;
  border-radius: 0.85rem;
  color: var(--theme-text-primary);
  font-size: clamp(1.15rem, 4.6vw, 1.55rem);
  font-weight: 600;
  letter-spacing: -0.02em;
  text-decoration: none;
  transition:
    color 150ms ease,
    background-color 150ms ease,
    transform 150ms ease;
}

.sm-panel-itemIcon {
  display: grid;
  flex: none;
  width: 1.85rem;
  height: 1.85rem;
  place-items: center;
  border-radius: 0.65rem;
  background: color-mix(in srgb, var(--theme-accent-primary) 10%, transparent);
  color: var(--sm-accent, var(--theme-accent-primary));
}

.sm-panel-itemLabel {
  display: inline-block;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  will-change: transform;
  transform-origin: 50% 100%;
}

.sm-panel-list[data-numbering] .sm-panel-item::after {
  counter-increment: smItem;
  content: counter(smItem, decimal-leading-zero);
  margin-inline-start: auto;
  font-size: 0.72rem;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  letter-spacing: 0.02em;
  color: var(--sm-accent, var(--theme-accent-primary));
  opacity: var(--sm-num-opacity, 0);
  pointer-events: none;
  user-select: none;
}

.sm-panel-item:hover,
.sm-panel-item:focus-visible {
  background: color-mix(in srgb, var(--theme-accent-primary) 12%, transparent);
  color: var(--sm-accent, var(--theme-accent-primary));
}

.sm-panel-item--active {
  background: color-mix(in srgb, var(--theme-accent-primary) 16%, transparent);
  color: var(--sm-accent, var(--theme-accent-primary));
  box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--theme-accent-primary) 28%, transparent);
}

.sm-panel-item--active .sm-panel-itemIcon {
  background: color-mix(in srgb, var(--theme-accent-primary) 22%, transparent);
}

.sm-socials {
  display: flex;
  flex-direction: column;
  gap: 0.7rem;
  margin-top: auto;
  padding-top: 1.1rem;
  border-top: 1px solid color-mix(in srgb, var(--theme-border) 55%, transparent);
}

.sm-socials-title {
  margin: 0;
  font-size: 0.82rem;
  font-weight: 600;
  color: var(--sm-accent, var(--theme-accent-primary));
}

.sm-socials-list {
  display: flex;
  flex-wrap: wrap;
  gap: 0.45rem;
  margin: 0;
  padding: 0;
  list-style: none;
}

.sm-socials-link {
  display: inline-grid;
  width: var(--touch-target);
  height: var(--touch-target);
  place-items: center;
  border-radius: 0.85rem;
  border: 1px solid color-mix(in srgb, var(--theme-border) 70%, transparent);
  background: color-mix(in srgb, var(--theme-bg-elevated) 55%, transparent);
  color: var(--theme-text-secondary);
  text-decoration: none;
  transition: color 160ms ease, border-color 160ms ease, background-color 160ms ease, transform 160ms ease;
}

.sm-socials-link--text {
  display: inline-flex;
  width: auto;
  min-height: 2.15rem;
  padding: 0.35rem 0.8rem;
  border-radius: 999px;
  font-size: 0.9rem;
  font-weight: 500;
}

.sm-socials-link:hover,
.sm-socials-link:focus-visible {
  border-color: color-mix(in srgb, var(--theme-accent-primary) 45%, transparent);
  background: color-mix(in srgb, var(--theme-accent-primary) 12%, transparent);
  color: var(--sm-accent, var(--theme-accent-primary));
  transform: translateY(-1px);
}

.sm-toggle:focus-visible {
  outline: 2px solid rgb(255 255 255 / 65%);
  outline-offset: 4px;
  border-radius: 4px;
}

@media (min-width: 480px) {
  .sm-prelayers,
  .staggered-menu-panel {
    width: min(24rem, calc(100dvw - 1.25rem));
  }

  .sm-panel-inner {
    padding: 1rem 1.15rem 1.4rem;
  }

  .sm-panel-item {
    font-size: clamp(1.25rem, 3.2vw, 1.7rem);
    min-height: 2.95rem;
  }
}

@media (min-width: 768px) {
  .sm-prelayers,
  .staggered-menu-panel {
    width: min(26rem, 42vw);
  }

  .sm-panel-inner {
    gap: 1rem;
    padding: 1.15rem 1.35rem 1.6rem;
  }

  .sm-panel-kicker {
    font-size: 0.84rem;
  }
}

@media (max-width: 359px) {
  .sm-panel-item {
    font-size: 1.05rem;
    gap: 0.55rem;
    padding-inline: 0.55rem;
  }

  .sm-panel-itemIcon {
    width: 1.65rem;
    height: 1.65rem;
  }

  .sm-panel-list[data-numbering] .sm-panel-item::after {
    display: none;
  }
}

@media (prefers-reduced-motion: reduce) {
  .staggered-menu-panel,
  .sm-prelayer,
  .sm-backdrop {
    transition: none !important;
    animation: none !important;
  }
}
</style>
