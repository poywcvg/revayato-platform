<script setup lang="ts">
import { gsap } from 'gsap'
import type { LiquidNavItem } from '~/types'

const open = defineModel<boolean>('open', { default: false })

const route = useRoute()
const { watchlistIds } = useLibrary()
const authStore = useAuthStore()
const { open: openSupportModal } = useSupportModal()
const sidebar = useTemplateRef<HTMLElement>('sidebar')
const navigation = useTemplateRef<HTMLElement>('navigation')
let previouslyFocused: HTMLElement | null = null
const sidebarFocusable = 'a[href], button:not([disabled]), [tabindex]:not([tabindex="-1"])'
const reduceMotion = ref(false)

// Scroll affordance state for the sidebar navigation rail: drives the top/bottom
// edge fades and the inline scroll-progress bar so the user always sees that the
// menu scrolls and how far they are through it.
const atTop = ref(true)
const atBottom = ref(false)
const hasOverflow = ref(false)
const scrollProgress = ref(0)

function updateScroll() {
  const el = navigation.value
  if (!el) return
  const max = el.scrollHeight - el.clientHeight
  const top = el.scrollTop
  atTop.value = top <= 1
  atBottom.value = max <= 1 || top >= max - 1
  hasOverflow.value = max > 1
  scrollProgress.value = max > 0 ? Math.min(1, Math.max(0, top / max)) : 0
}

function spawnRipple(event: PointerEvent | MouseEvent, host: HTMLElement) {
  if (reduceMotion.value || !import.meta.client) return
  const rect = host.getBoundingClientRect()
  const x = (event.clientX || rect.left + rect.width / 2) - rect.left
  const y = (event.clientY || rect.top + rect.height / 2) - rect.top
  const size = Math.max(rect.width, rect.height) * 2.4
  const ripple = document.createElement('span')
  ripple.className = 'mobile-sidebar__ripple'
  ripple.style.setProperty('--ripple-x', `${x}px`)
  ripple.style.setProperty('--ripple-y', `${y}px`)
  ripple.style.width = `${size}px`
  ripple.style.height = `${size}px`
  host.appendChild(ripple)
  ripple.addEventListener('animationend', () => ripple.remove(), { once: true })
}

const homeItem: LiquidNavItem = { label: 'خانه', to: '/', icon: 'home', exact: true }
const navItems = computed<LiquidNavItem[]>(() => [
  homeItem,
  { label: 'فیلم‌ها', to: '/movies', icon: 'movie' },
  { label: 'سریال‌ها', to: '/series', icon: 'series' },
  { label: 'انیمیشن', to: '/movies?format=animation', icon: 'animation' },
  { label: 'تازه‌ها', to: '/new', icon: 'sparkles' },
  { label: 'تماشای گروهی', to: '/watch-party', icon: 'users' },
  { label: 'کشورها', to: '/countries', icon: 'globe' },
  { label: 'بازیگران', to: '/actors', icon: 'user' },
  {
    label: watchlistIds.value.length
      ? `لیست من (${watchlistIds.value.length.toLocaleString('fa-IR')})`
      : 'لیست من',
    to: '/watchlist',
    icon: 'bookmark',
  },
  ...(authStore.user?.is_staff
    ? [{ label: 'مدیریت', to: '/admin', icon: 'settings' as const }]
    : []),
])

// Section labels above the nav rail: کاوش (0) / جامعه (5) / کتابخانه من (8).
const navGroupHeaders = computed<Record<number, string>>(() => ({
  0: 'کاوش',
  5: 'جامعه',
  8: 'کتابخانه من',
}))

const lineSidebarItems = computed(() => navItems.value.map(item => item.label))
const lineSidebarIcons = computed(() => navItems.value.map(item => item.icon))

const profilePath = computed(() => authStore.isAuthenticated ? '/profile' : `/auth/login?redirect=${encodeURIComponent(route.fullPath)}`)
const avatarInitial = computed(() => authStore.user?.username?.trim().charAt(0).toUpperCase() || 'ر')

function isActive(item: LiquidNavItem) {
  const path = item.to.split(/[?#]/, 1)[0] || '/'
  const query = item.to.includes('?') ? new URLSearchParams(item.to.split('?')[1]) : null
  if (item.exact || path === '/') return route.path === path
  if (path === '/new') return route.path === '/new'
  if (query?.get('format') === 'animation') {
    return route.path === '/movies' && route.query.format === 'animation'
  }
  if (query?.get('sort')) {
    return route.path === path && route.query.sort === query.get('sort')
  }
  if (path === '/movies') {
    return ((route.path === '/movies' && !route.query.format && !route.query.sort)
      || route.path.startsWith('/movies/'))
  }
  return route.path === path || route.path.startsWith(`${path}/`)
}

const activeLineIndex = computed(() => {
  const index = navItems.value.findIndex(isActive)
  return index >= 0 ? index : null
})

function close() {
  open.value = false
}

// Swipe-to-close: the drawer lives on the trailing edge (right side in RTL),
// so a horizontal drag toward that edge dismisses it. The |dx| > |dy| gate
// keeps vertical scrolling of the nav rail untouched.
const SWIPE_CLOSE_THRESHOLD = 56
let closeSwipeStartX: number | null = null
let closeSwipeStartY: number | null = null

function handleCloseSwipeStart(event: TouchEvent) {
  if (event.touches.length !== 1) return
  const touch = event.touches[0]
  if (!touch) return
  closeSwipeStartX = touch.clientX
  closeSwipeStartY = touch.clientY
}

function handleCloseSwipeMove(event: TouchEvent) {
  if (closeSwipeStartX == null || closeSwipeStartY == null) return
  const touch = event.touches[0]
  if (!touch) return
  const dx = touch.clientX - closeSwipeStartX
  const dy = touch.clientY - closeSwipeStartY
  if (Math.abs(dx) > Math.abs(dy) && dx > SWIPE_CLOSE_THRESHOLD) {
    closeSwipeStartX = null
    closeSwipeStartY = null
    close()
  }
}

function handleCloseSwipeEnd() {
  closeSwipeStartX = null
  closeSwipeStartY = null
}

function handleLineSidebarClick(index: number, _label: string, event?: PointerEvent | MouseEvent) {
  const item = navItems.value[index]
  if (!item) return
  if (event && sidebar.value) spawnRipple(event, sidebar.value)
  close()
  void navigateTo(item.to)
}

function handleFooterClick(event: PointerEvent | MouseEvent, host: HTMLElement) {
  spawnRipple(event, host)
  close()
}

function openQuickSupport(category: 'content_request' | 'support', event?: PointerEvent | MouseEvent) {
  if (event && sidebar.value) spawnRipple(event, sidebar.value)
  close()
  openSupportModal(category)
}

watch(() => route.fullPath, close)
onKeyStroke('Escape', () => {
  if (open.value) close()
})

function trapSidebarFocus(event: KeyboardEvent) {
  if (event.key !== 'Tab' || !sidebar.value) return
  const controls = [...sidebar.value.querySelectorAll<HTMLElement>(sidebarFocusable)]
    .filter(control => control.getClientRects().length > 0)
  const first = controls[0]
  const last = controls.at(-1)
  if (!first || !last) return
  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault()
    last.focus()
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault()
    first.focus()
  }
}

// GSAP-backed entrance for inner content (the panel slide itself is handled by
// the Vue Transition). Nav items rise in a stagger, then the magnetic pill
// fades in. Skipped under prefers-reduced-motion (panel still appears instantly).
function playOpen() {
  if (!import.meta.client || reduceMotion.value || !sidebar.value) return
  const panel = sidebar.value
  const items = panel.querySelectorAll<HTMLElement>('.line-sidebar__item, .line-sidebar__group-header, .mobile-sidebar__foot > *')
  const pill = panel.querySelector<HTMLElement>('.line-sidebar__magnet-pill')
  gsap.killTweensOf([...items, pill].filter(Boolean))
  gsap.set(items, { autoAlpha: 0, y: 10 })
  if (pill) gsap.set(pill, { autoAlpha: 0 })
  gsap.to(items, { autoAlpha: 1, y: 0, duration: 0.32, ease: 'power2.out', stagger: 0.035, delay: 0.14 })
  if (pill) gsap.to(pill, { autoAlpha: 1, duration: 0.4, delay: 0.34 })
}

async function applyOpenState(value: boolean) {
  if (!import.meta.client) return
  document.documentElement.style.overflow = value ? 'hidden' : ''
  if (value) {
    previouslyFocused = document.activeElement instanceof HTMLElement ? document.activeElement : null
    await nextTick()
    sidebar.value?.querySelector<HTMLElement>(sidebarFocusable)?.focus()
    // Sync scroll affordances after the panel mounts/animates in, then keep
    // them live while the user scrolls the navigation rail.
    updateScroll()
    requestAnimationFrame(updateScroll)
    navigation.value?.addEventListener('scroll', updateScroll, { passive: true })
    // Hide synchronously (no flash), then animate the rise in.
    playOpen()
  } else {
    previouslyFocused?.focus()
    previouslyFocused = null
  }
}

watch(open, applyOpenState)

onBeforeUnmount(() => {
  if (import.meta.client) {
    document.documentElement.style.overflow = ''
    navigation.value?.removeEventListener('scroll', updateScroll)
  }
})

onMounted(() => {
  if (import.meta.client) {
    reduceMotion.value = window.matchMedia('(prefers-reduced-motion: reduce)').matches
  }
  // The host mounts this component lazily on the first open, so the watcher
  // above may never see the transition into `true`. Run the same sequence.
  if (open.value) void applyOpenState(true)
})
</script>

<template>
  <Teleport to="body">
    <Transition name="sidebar-fade">
      <button
        v-if="open"
        type="button"
        class="mobile-sidebar-backdrop fixed inset-0 z-[80] cursor-default"
        aria-label="بستن منو"
        @click="close"
      />
    </Transition>

    <Transition name="sidebar-slide">
      <aside
        v-if="open"
        id="mobile-sidebar"
        ref="sidebar"
        class="mobile-sidebar fixed inset-y-0 z-[85] flex max-w-full flex-col"
        role="dialog"
        aria-modal="true"
        aria-label="منوی اصلی"
        dir="rtl"
        @keydown="trapSidebarFocus"
        @touchstart.passive="handleCloseSwipeStart"
        @touchmove.passive="handleCloseSwipeMove"
        @touchend.passive="handleCloseSwipeEnd"
        @touchcancel.passive="handleCloseSwipeEnd"
      >
        <header class="mobile-sidebar__head">
          <AppLogo :compact-on-mobile="false" @click="close" />
          <button
            type="button"
            class="mobile-sidebar__close"
            aria-label="بستن منو"
            @click="close"
          >
            <CinematicIcon name="x" class="size-5" />
          </button>
        </header>

        <div
          ref="navigation"
          class="mobile-sidebar__navigation soft-scrollbar min-h-0 flex-1 overflow-y-auto"
          :class="{
            'is-scrollable': hasOverflow,
            'is-at-top': atTop,
            'is-at-bottom': atBottom,
          }"
        >
          <span class="mobile-sidebar__fade mobile-sidebar__fade--top" aria-hidden="true" />
          <LineSidebar
            :items="lineSidebarItems"
            :icons="lineSidebarIcons"
            :headers="navGroupHeaders"
            direction="rtl"
            aria-label="ناوبری اصلی موبایل"
            accent-color="var(--theme-accent-primary)"
            text-color="var(--theme-text-secondary)"
            marker-color="var(--theme-text-disabled)"
            :default-active="activeLineIndex"
            :show-index="false"
            :show-marker="false"
            :proximity-radius="56"
            :max-shift="4"
            falloff="smooth"
            :scale-tick="false"
            :item-gap="4"
            :font-size="0.9"
            :smoothing="80"
            :magnetic-pill="true"
            pill-color="var(--theme-accent-primary)"
            class="mobile-sidebar__line-nav"
            @item-click="handleLineSidebarClick"
          />

          <span class="mobile-sidebar__fade mobile-sidebar__fade--bottom" aria-hidden="true" />

          <section class="mobile-sidebar__help" aria-labelledby="mobile-sidebar-help-title">
            <button type="button" class="mobile-sidebar__request" @click="openQuickSupport('content_request', $event)">
              <span class="mobile-sidebar__request-glow" aria-hidden="true" />
              <span class="mobile-sidebar__request-icon" aria-hidden="true">
                <CinematicIcon name="film" class="size-5" />
                <span class="mobile-sidebar__request-plus">+</span>
              </span>
              <span class="min-w-0 flex-1 text-start">
                <strong id="mobile-sidebar-help-title" class="mobile-sidebar__request-title">چی دوست داری ببینی؟</strong>
                <small class="mobile-sidebar__request-copy">فیلم یا سریالت را درخواست کن</small>
              </span>
              <span class="mobile-sidebar__request-arrow" aria-hidden="true"><CinematicIcon name="arrow-left" class="size-4" /></span>
            </button>

            <div class="mobile-sidebar__help-actions">
              <button type="button" class="mobile-sidebar__help-action" @click="openQuickSupport('support', $event)">
                <span class="mobile-sidebar__help-icon mobile-sidebar__help-icon--support"><CinematicIcon name="comments" class="size-4.5" /></span>
                <span><strong>پشتیبانی</strong><small>سؤال یا مشکل</small></span>
              </button>
            </div>
          </section>
        </div>

        <span
          class="mobile-sidebar__progress"
          :class="hasOverflow && 'is-active'"
          aria-hidden="true"
        >
          <span class="mobile-sidebar__progress-thumb" :style="{ transform: `scaleX(${scrollProgress})` }" />
        </span>

        <footer class="mobile-sidebar__foot">
          <NuxtLink
            :to="profilePath"
            class="mobile-sidebar__account"
            :class="route.path.startsWith('/profile') && 'mobile-sidebar__account--active'"
            :aria-current="route.path.startsWith('/profile') ? 'page' : undefined"
            @click="handleFooterClick($event, $el)"
          >
            <span v-if="authStore.isAuthenticated" class="mobile-sidebar__avatar" aria-hidden="true">
              <img v-if="authStore.user?.profile.avatar" :src="authStore.user.profile.avatar" alt="" class="size-full object-cover">
              <span v-else>{{ avatarInitial }}</span>
            </span>
            <span v-else class="mobile-sidebar__account-icon"><CinematicIcon name="login" class="size-5" /></span>
            <span class="min-w-0 flex-1">
              <strong class="mobile-sidebar__account-title font-latin" :dir="authStore.isAuthenticated ? 'ltr' : undefined">{{ authStore.isAuthenticated ? authStore.user?.username : 'ورود به حساب' }}</strong>
              <small class="mobile-sidebar__account-subtitle">{{ authStore.isAuthenticated ? 'مشاهده و مدیریت پروفایل' : 'ورود برای دسترسی به لیست شخصی' }}</small>
            </span>
            <CinematicIcon name="arrow-left" class="size-4 shrink-0 text-disabled" />
          </NuxtLink>

          <div class="mobile-sidebar__row-actions">
            <NuxtLink
              to="/about"
              class="mobile-sidebar__footer-icon"
              aria-label="درباره روایتو"
              title="درباره روایتو"
              @click="handleFooterClick($event, $el)"
            >
              <CinematicIcon name="info" class="size-5" />
            </NuxtLink>
            <NotificationCenter />
          </div>
        </footer>
      </aside>
    </Transition>
  </Teleport>
</template>

<style scoped>
.mobile-sidebar-backdrop {
  background: rgb(5 8 7 / 52%);
  -webkit-backdrop-filter: blur(4px) saturate(115%);
  backdrop-filter: blur(4px) saturate(115%);
}

:global(html[data-theme="light"] .mobile-sidebar-backdrop) {
  background: var(--theme-overlay-backdrop);
}

/* Click ripple: a mint wave that blooms from the tap point and fades. */
.mobile-sidebar__account,
.mobile-sidebar__footer-icon,
.mobile-sidebar__request,
.mobile-sidebar__help-action {
  position: relative;
  overflow: hidden;
}

.mobile-sidebar__ripple {
  position: absolute;
  left: var(--ripple-x, 50%);
  top: var(--ripple-y, 50%);
  border-radius: 9999px;
  transform: translate(-50%, -50%) scale(0);
  background: radial-gradient(circle, color-mix(in srgb, var(--theme-accent-primary) 42%, transparent), color-mix(in srgb, var(--theme-accent-primary) 12%, transparent) 60%, transparent 72%);
  pointer-events: none;
  display: block;
  animation: mobile-sidebar-ripple 520ms var(--ease-emphasized) forwards;
  will-change: transform, opacity;
}

@keyframes mobile-sidebar-ripple {
  0% { transform: translate(-50%, -50%) scale(0); opacity: 0.85; }
  100% { transform: translate(-50%, -50%) scale(1); opacity: 0; }
}

.mobile-sidebar {
  inset-inline-start: 0;
  width: min(20.5rem, calc(100dvw - .75rem));
  padding-top: env(safe-area-inset-top, 0);
  padding-bottom: env(safe-area-inset-bottom, 0);
  border-inline-start: 1px solid color-mix(in srgb, var(--theme-border) 55%, transparent);
  background:
    linear-gradient(180deg, color-mix(in srgb, var(--theme-accent-primary) 7%, var(--theme-bg-surface)), var(--theme-bg-surface) 8rem);
  box-shadow: -12px 0 40px rgb(0 0 0 / 28%);
}

/* Tablets get a slightly roomier drawer while it stays one-hand friendly. */
@media (min-width: 768px) {
  .mobile-sidebar {
    width: min(22.5rem, calc(100dvw - 1.5rem));
  }
}

:global(html[data-theme="light"] .mobile-sidebar) {
  background:
    radial-gradient(circle at 100% 0, rgb(23 107 80 / 10%), transparent 13rem),
    linear-gradient(180deg, #f8fbf9, var(--theme-bg-surface) 8rem);
  border-inline-start-color: var(--theme-border);
  box-shadow: -18px 0 48px rgb(23 50 38 / 16%);
}

.mobile-sidebar__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: .75rem;
  padding: .9rem 1rem .55rem;
}

.mobile-sidebar__account {
  display: flex;
  min-height: 4.5rem;
  align-items: center;
  gap: .75rem;
  border: 1px solid color-mix(in srgb, var(--theme-border) 72%, transparent);
  border-radius: 1rem;
  background: color-mix(in srgb, var(--theme-bg-elevated) 72%, transparent);
  padding: .65rem .75rem;
  transition: border-color var(--motion-fast) var(--ease-out), background-color var(--motion-fast) var(--ease-out);
}

.mobile-sidebar__account:hover,
.mobile-sidebar__account:focus-visible,
.mobile-sidebar__account--active {
  border-color: color-mix(in srgb, var(--theme-accent-primary) 36%, transparent);
  background: color-mix(in srgb, var(--theme-accent-primary) 10%, var(--theme-bg-elevated));
}

.mobile-sidebar__avatar,
.mobile-sidebar__account-icon {
  display: grid;
  width: 2.65rem;
  height: 2.65rem;
  flex: none;
  overflow: hidden;
  place-items: center;
  border-radius: .85rem;
}

.mobile-sidebar__avatar {
  border: 1px solid color-mix(in srgb, var(--theme-accent-primary) 42%, transparent);
  background: linear-gradient(145deg, var(--theme-accent-primary), var(--theme-primary-700));
  color: var(--theme-on-accent);
  font-family: var(--font-latin-ui);
  font-size: .85rem;
  font-weight: 800;
}

.mobile-sidebar__account-icon {
  background: color-mix(in srgb, var(--theme-accent-primary) 12%, transparent);
  color: var(--theme-accent-primary);
}

.mobile-sidebar__account-title {
  display: block;
  overflow: hidden;
  color: var(--theme-text-primary);
  font-size: .8rem;
  font-weight: 800;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.mobile-sidebar__account-subtitle {
  display: block;
  overflow: hidden;
  margin-top: .2rem;
  color: var(--theme-text-muted);
  font-size: .62rem;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.mobile-sidebar__footer-icon {
  display: grid;
  width: var(--touch-target);
  height: var(--touch-target);
  flex: none;
  place-items: center;
  border-radius: .7rem;
  color: var(--theme-text-muted);
  transition: color var(--motion-fast) var(--ease-out), background-color var(--motion-fast) var(--ease-out);
}

.mobile-sidebar__footer-icon:hover,
.mobile-sidebar__footer-icon:focus-visible {
  background: color-mix(in srgb, var(--theme-bg-elevated) 70%, transparent);
  color: var(--theme-text-primary);
}

.mobile-sidebar__close {
  display: grid;
  flex: none;
  width: var(--touch-target);
  height: var(--touch-target);
  place-items: center;
  border-radius: .7rem;
  color: var(--theme-text-muted);
  transition: color var(--motion-fast) var(--ease-out), background-color var(--motion-fast) var(--ease-out);
}

.mobile-sidebar__close:hover {
  background: color-mix(in srgb, var(--theme-bg-elevated) 80%, transparent);
  color: var(--theme-text-primary);
}

.mobile-sidebar__navigation {
  position: relative;
  padding: 0 .65rem .5rem;
  overscroll-behavior: contain;
}

/* Edge fades + inline scroll-progress bar give the rail a clear, distinct
   scroll state without adding a heavy scrollbar: a veil appears above/below
   only while more content exists in that direction, and the progress thumb
   tracks position. All purely visual — never blocks the scrolled content. */
.mobile-sidebar__fade {
  position: sticky;
  inset-inline: -.65rem;
  z-index: 3;
  flex: none;
  height: 1.5rem;
  margin-block: -.25rem;
  pointer-events: none;
  opacity: 0;
  transition: opacity var(--motion-base) var(--ease-out);
}

.mobile-sidebar__fade--top {
  top: -.5rem;
  margin-bottom: -.75rem;
  background: linear-gradient(to bottom, var(--theme-bg-surface), transparent);
}

.mobile-sidebar__fade--bottom {
  bottom: -.5rem;
  margin-top: -.75rem;
  background: linear-gradient(to top, var(--theme-bg-surface), transparent);
}

.mobile-sidebar__navigation.is-scrollable:not(.is-at-top) .mobile-sidebar__fade--top,
.mobile-sidebar__navigation.is-scrollable:not(.is-at-bottom) .mobile-sidebar__fade--bottom {
  opacity: 1;
}

.mobile-sidebar__progress {
  position: absolute;
  inset-inline: .35rem;
  bottom: calc(.5rem + env(safe-area-inset-bottom, 0px));
  z-index: 4;
  height: 3px;
  border-radius: 999px;
  background: color-mix(in srgb, var(--theme-border) 60%, transparent);
  overflow: hidden;
  opacity: 0;
  transition: opacity var(--motion-base) var(--ease-out);
}

.mobile-sidebar__progress.is-active { opacity: 1; }

.mobile-sidebar__progress-thumb {
  display: block;
  height: 100%;
  width: 100%;
  transform-origin: right center;
  border-radius: 999px;
  background: linear-gradient(to left, var(--theme-accent-primary), var(--theme-accent-crimson));
}

:global(html[data-theme="light"] .mobile-sidebar__progress) {
  background: color-mix(in srgb, var(--theme-border) 70%, transparent);
}

.mobile-sidebar__help { display: grid; gap: .5rem; padding: .25rem .1rem .75rem; }

.mobile-sidebar__request {
  isolation: isolate;
  display: flex;
  width: 100%;
  min-height: 4.75rem;
  align-items: center;
  gap: .7rem;
  border: 1px solid color-mix(in srgb, var(--theme-accent-primary) 42%, transparent);
  border-radius: 1.15rem;
  background: linear-gradient(125deg, color-mix(in srgb, var(--theme-accent-primary) 19%, var(--theme-bg-elevated)), color-mix(in srgb, var(--theme-accent-crimson, #b04848) 10%, var(--theme-bg-elevated)));
  padding: .7rem;
  color: var(--theme-text-primary);
  box-shadow: inset 0 1px 0 rgb(255 255 255 / 7%), 0 .65rem 1.8rem color-mix(in srgb, var(--theme-accent-primary) 8%, transparent);
  transition: transform var(--motion-base) var(--ease-out), border-color var(--motion-base) var(--ease-out), box-shadow var(--motion-base) var(--ease-out);
}
.mobile-sidebar__request:hover, .mobile-sidebar__request:focus-visible { border-color: color-mix(in srgb, var(--theme-accent-primary) 72%, transparent); box-shadow: inset 0 1px 0 rgb(255 255 255 / 10%), 0 .75rem 2rem color-mix(in srgb, var(--theme-accent-primary) 15%, transparent); transform: translateY(-1px); }
.mobile-sidebar__request:active { transform: scale(.985); }
.mobile-sidebar__request-glow { position: absolute; z-index: -1; width: 7rem; height: 7rem; inset-inline-end: -3rem; top: -4rem; border-radius: 9999px; background: var(--theme-accent-primary); filter: blur(35px); opacity: .18; }
.mobile-sidebar__request-icon { position: relative; display: grid; width: 2.8rem; height: 2.8rem; flex: none; place-items: center; border-radius: .9rem; background: var(--theme-accent-primary); color: var(--theme-on-accent); box-shadow: 0 .45rem 1.2rem color-mix(in srgb, var(--theme-accent-primary) 28%, transparent); }
.mobile-sidebar__request-plus { position: absolute; inset-inline-end: -.18rem; top: -.25rem; display: grid; width: 1rem; height: 1rem; place-items: center; border: 2px solid var(--theme-bg-surface); border-radius: 9999px; background: var(--theme-accent-crimson, #b04848); color: white; font: 800 .65rem/1 var(--font-latin-ui); }
.mobile-sidebar__request-title { display: block; font-size: .82rem; font-weight: 900; }
.mobile-sidebar__request-copy { display: block; margin-top: .2rem; color: var(--theme-text-muted); font-size: .65rem; }
.mobile-sidebar__request-arrow { display: grid; width: 2rem; height: 2rem; flex: none; place-items: center; border-radius: .65rem; background: color-mix(in srgb, var(--theme-bg-surface) 45%, transparent); color: var(--theme-accent-primary); }
.mobile-sidebar__help-actions { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: .5rem; }
.mobile-sidebar__help-action { display: flex; min-width: 0; min-height: 3.4rem; align-items: center; gap: .55rem; border: 1px solid color-mix(in srgb, var(--theme-border) 70%, transparent); border-radius: .95rem; background: color-mix(in srgb, var(--theme-bg-elevated) 68%, transparent); padding: .5rem; color: var(--theme-text-secondary); text-align: start; transition: border-color var(--motion-fast) var(--ease-out), background-color var(--motion-fast) var(--ease-out), transform var(--motion-fast) var(--ease-out); }
.mobile-sidebar__help-action:hover, .mobile-sidebar__help-action:focus-visible { border-color: color-mix(in srgb, var(--theme-accent-primary) 32%, var(--theme-border)); background: var(--theme-bg-elevated); transform: translateY(-1px); }
.mobile-sidebar__help-action strong { display: block; color: var(--theme-text-primary); font-size: .7rem; font-weight: 850; white-space: nowrap; }
.mobile-sidebar__help-action small { display: block; margin-top: .12rem; color: var(--theme-text-muted); font-size: .58rem; white-space: nowrap; }
.mobile-sidebar__help-icon { display: grid; width: 2rem; height: 2rem; flex: none; place-items: center; border-radius: .65rem; }
.mobile-sidebar__help-icon--support { background: color-mix(in srgb, var(--theme-accent-primary) 12%, transparent); color: var(--theme-accent-primary); }
.mobile-sidebar__line-nav {
  width: 100%;
  min-width: 0;
}

.mobile-sidebar__line-nav :deep(.line-sidebar__list) {
  width: 100%;
  padding: .45rem 0 .75rem;
}

.mobile-sidebar__line-nav :deep(.line-sidebar__group-header) {
  margin-block-start: 1rem;
  padding-inline: .75rem .8rem;
  color: var(--theme-text-muted);
}

.mobile-sidebar__line-nav :deep(.line-sidebar__group-header:first-child) {
  margin-block-start: 0;
}

.mobile-sidebar__line-nav :deep(.line-sidebar__item) {
  display: flex;
  min-height: var(--touch-target);
  align-items: center;
}

.mobile-sidebar__line-nav :deep(.line-sidebar__item::before) {
  inset: 0;
  pointer-events: none;
}

.mobile-sidebar__line-nav :deep(.line-sidebar__control) {
  display: flex;
  width: 100%;
  min-height: var(--touch-target);
  max-width: 100%;
  align-items: center;
  border: 1px solid transparent;
  border-radius: .85rem;
  padding: .25rem .4rem;
  transition: border-color 140ms ease, background-color 140ms ease;
}

.mobile-sidebar__line-nav :deep(.line-sidebar__control:hover),
.mobile-sidebar__line-nav :deep(.line-sidebar__control:focus-visible) {
  border-color: color-mix(in srgb, var(--theme-border) 75%, transparent);
  background: color-mix(in srgb, var(--theme-bg-elevated) 72%, transparent);
}

.mobile-sidebar__line-nav :deep(.line-sidebar__control[aria-current='true']) {
  border-color: color-mix(in srgb, var(--theme-accent-primary) 32%, transparent);
  background: color-mix(in srgb, var(--theme-accent-primary) 11%, var(--theme-bg-elevated));
}

.mobile-sidebar__line-nav :deep(.line-sidebar__label) {
  width: 100%;
  max-width: 100%;
  align-items: center;
  font-weight: 650;
  white-space: nowrap;
}

.mobile-sidebar__line-nav :deep(.line-sidebar__icon) {
  display: grid;
  width: 2.15rem;
  height: 2.15rem;
  margin-inline-end: .7rem;
  place-items: center;
  border-radius: .7rem;
  background: color-mix(in srgb, var(--theme-bg-elevated) 78%, transparent);
  color: color-mix(in srgb, var(--theme-accent-primary) calc(38% + var(--effect, 0) * 62%), var(--theme-text-muted));
}

.mobile-sidebar__line-nav :deep(.line-sidebar__icon svg) {
  width: 1.15rem;
  height: 1.15rem;
}

.mobile-sidebar__line-nav :deep(.line-sidebar__control[aria-current='true'] .line-sidebar__icon) {
  background: color-mix(in srgb, var(--theme-accent-primary) 18%, transparent);
  color: var(--theme-accent-primary);
}

.mobile-sidebar__foot {
  display: flex;
  flex-direction: column;
  gap: .35rem;
  border-top: 1px solid color-mix(in srgb, var(--theme-border) 55%, transparent);
  padding: .55rem .75rem .9rem;
}

.mobile-sidebar__row-actions {
  display: flex;
  align-items: center;
  gap: .35rem;
  padding-inline: .15rem;
}

.mobile-sidebar__row-actions :deep(.site-header__icon-btn) {
  width: var(--touch-target);
  height: var(--touch-target);
  border-radius: .7rem;
  color: var(--theme-text-secondary);
}

.mobile-sidebar__row-actions :deep(.site-header__icon-btn:hover),
.mobile-sidebar__row-actions :deep(.site-header__icon-btn--active) {
  background: color-mix(in srgb, var(--theme-bg-elevated) 70%, transparent);
  color: var(--theme-text-primary);
}

.sidebar-fade-enter-active,
.sidebar-fade-leave-active { transition: opacity var(--motion-base) var(--ease-out); }
.sidebar-fade-enter-from,
.sidebar-fade-leave-to { opacity: 0; }

/* Panel slides in with a springy overshoot, slides straight out on close.
   GSAP owns the inner item stagger + pill (independent of this transform). */
.sidebar-slide-enter-active { transition: transform 360ms var(--ease-spring); }
.sidebar-slide-leave-active { transition: transform 260ms var(--ease-in-out); }
.sidebar-slide-enter-from { transform: translateX(106%); }
.sidebar-slide-leave-to { transform: translateX(100%); }

@media (prefers-reduced-motion: reduce) {
  .sidebar-fade-enter-active,
  .sidebar-fade-leave-active,
  .sidebar-slide-enter-active,
  .sidebar-slide-leave-active { transition: none; }
}
</style>
