<script setup lang="ts">
import type { LiquidNavItem } from '~/types'

const open = defineModel<boolean>('open', { default: false })

const route = useRoute()
const { watchlistIds } = useLibrary()
const authStore = useAuthStore()
const sidebar = useTemplateRef<HTMLElement>('sidebar')
let previouslyFocused: HTMLElement | null = null
const sidebarFocusable = 'a[href], button:not([disabled]), [tabindex]:not([tabindex="-1"])'

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

function handleLineSidebarClick(index: number) {
  const item = navItems.value[index]
  if (!item) return
  close()
  void navigateTo(item.to)
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

watch(open, async (value) => {
  if (!import.meta.client) return
  document.documentElement.style.overflow = value ? 'hidden' : ''
  if (value) {
    previouslyFocused = document.activeElement instanceof HTMLElement ? document.activeElement : null
    await nextTick()
    sidebar.value?.querySelector<HTMLElement>(sidebarFocusable)?.focus()
  } else {
    previouslyFocused?.focus()
    previouslyFocused = null
  }
})

onBeforeUnmount(() => {
  if (import.meta.client) document.documentElement.style.overflow = ''
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

        <div class="mobile-sidebar__navigation soft-scrollbar min-h-0 flex-1 overflow-y-auto">
          <LineSidebar
            :items="lineSidebarItems"
            :icons="lineSidebarIcons"
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
            class="mobile-sidebar__line-nav"
            @item-click="handleLineSidebarClick"
          />
        </div>

        <footer class="mobile-sidebar__foot">
          <NuxtLink
            :to="profilePath"
            class="mobile-sidebar__account"
            :class="route.path.startsWith('/profile') && 'mobile-sidebar__account--active'"
            :aria-current="route.path.startsWith('/profile') ? 'page' : undefined"
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
              @click="close"
            >
              <CinematicIcon name="info" class="size-5" />
            </NuxtLink>
            <NuxtLink
              to="/contact"
              class="mobile-sidebar__footer-icon"
              aria-label="پشتیبانی"
              title="پشتیبانی"
              @click="close"
            >
              <CinematicIcon name="comments" class="size-5" />
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
  background: rgb(5 8 7 / 48%);
}

:global(html[data-theme="light"] .mobile-sidebar-backdrop) {
  background: var(--theme-overlay-backdrop);
}

.mobile-sidebar {
  inset-inline-start: 0;
  width: min(20rem, calc(100dvw - .75rem));
  padding-top: env(safe-area-inset-top, 0);
  padding-bottom: env(safe-area-inset-bottom, 0);
  border-inline-start: 1px solid color-mix(in srgb, var(--theme-border) 55%, transparent);
  background:
    linear-gradient(180deg, color-mix(in srgb, var(--theme-accent-primary) 7%, var(--theme-bg-surface)), var(--theme-bg-surface) 8rem);
  box-shadow: -12px 0 40px rgb(0 0 0 / 28%);
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
  transition: border-color 150ms ease, background-color 150ms ease;
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
  transition: color 140ms ease, background-color 140ms ease;
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
  transition: color 140ms ease, background-color 140ms ease;
}

.mobile-sidebar__close:hover {
  background: color-mix(in srgb, var(--theme-bg-elevated) 80%, transparent);
  color: var(--theme-text-primary);
}

.mobile-sidebar__navigation {
  padding: 0 .65rem .5rem;
  overscroll-behavior: contain;
}

.mobile-sidebar__line-nav {
  width: 100%;
  min-width: 0;
}

.mobile-sidebar__line-nav :deep(.line-sidebar__list) {
  width: 100%;
  padding: .45rem 0 .75rem;
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
.sidebar-fade-leave-active { transition: opacity 180ms ease; }
.sidebar-fade-enter-from,
.sidebar-fade-leave-to { opacity: 0; }

.sidebar-slide-enter-active,
.sidebar-slide-leave-active { transition: transform 240ms cubic-bezier(.22, 1, .36, 1); }
.sidebar-slide-enter-from,
.sidebar-slide-leave-to { transform: translateX(100%); }

@media (prefers-reduced-motion: reduce) {
  .sidebar-fade-enter-active,
  .sidebar-fade-leave-active,
  .sidebar-slide-enter-active,
  .sidebar-slide-leave-active { transition: none; }
}
</style>
