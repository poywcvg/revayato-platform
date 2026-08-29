<script setup lang="ts">
const route = useRoute()
const authStore = useAuthStore()
// Mobile chrome (compact header + bottom nav + drawer) owns phone *and* tablet
// widths; the desktop header only takes over from lg (1024px) up. Without this,
// tablets were stranded with no main nav links at all.
const isDesktop = useMediaQuery('(min-width: 1024px)')

const sidebarOpen = ref(false)
// The drawer is only mounted once the user actually reaches for it, so its gsap
// entrance never costs a visit that stays on the page it landed on.
const sidebarEverOpened = ref(false)
const searchOpen = ref(false)
const searchRoot = useTemplateRef<HTMLElement>('searchRoot')

const profilePath = computed(() => authStore.isAuthenticated
  ? '/profile'
  : `/auth/login?redirect=${encodeURIComponent(route.fullPath)}`)

const activeBottomItem = computed<'home' | 'movies' | 'series' | 'menu'>(() => {
  if (sidebarOpen.value) return 'menu'
  if (route.path === '/' || route.path === '/welcome') return 'home'
  if (route.path.startsWith('/movies')) return 'movies'
  if (route.path.startsWith('/series')) return 'series'
  return 'menu'
})

watch(isDesktop, (desktop) => {
  if (desktop) sidebarOpen.value = false
})

watch(() => route.fullPath, () => {
  sidebarOpen.value = false
  searchOpen.value = false
})

onClickOutside(searchRoot, () => {
  searchOpen.value = false
})

onKeyStroke('Escape', () => {
  if (searchOpen.value) {
    searchOpen.value = false
    return
  }
  if (sidebarOpen.value) sidebarOpen.value = false
})

onKeyStroke('/', (event) => {
  const target = event.target as HTMLElement | null
  if (target?.matches('input, textarea, select, [contenteditable="true"]')) return
  event.preventDefault()
  sidebarOpen.value = false
  searchOpen.value = true
})

function toggleSearch() {
  searchOpen.value = !searchOpen.value
  if (searchOpen.value) sidebarOpen.value = false
}

function toggleSidebar() {
  if (!sidebarOpen.value) sidebarEverOpened.value = true
  sidebarOpen.value = !sidebarOpen.value
  if (sidebarOpen.value) searchOpen.value = false
}

// Edge-swipe to open: a touch starting at the leading edge (right in RTL) that
// drags inward past a threshold commits to opening the sidebar. The strip is
// only live when the drawer is closed and we're on a phone width.
const SWIPE_EDGE = 28
const SWIPE_THRESHOLD = 42
let swipeStartX: number | null = null

function handleSwipeStart(event: TouchEvent) {
  if (sidebarOpen.value || isDesktop.value) return
  const touch = event.touches[0]
  if (!touch || touch.clientX < window.innerWidth - SWIPE_EDGE) return
  swipeStartX = touch.clientX
}

function handleSwipeMove(event: TouchEvent) {
  if (swipeStartX == null) return
  const touch = event.touches[0]
  if (!touch) return
  const dx = swipeStartX - touch.clientX
  if (dx > SWIPE_THRESHOLD) {
    swipeStartX = null
    sidebarEverOpened.value = true
    sidebarOpen.value = true
    searchOpen.value = false
  } else if (dx < -10) {
    swipeStartX = null
  }
}

function handleSwipeEnd() {
  swipeStartX = null
}
</script>

<template>
  <div class="site-header-root" dir="rtl">
    <header ref="searchRoot" class="site-header sticky top-0 z-[60] lg:hidden" :class="searchOpen && 'site-header--search-open'">
      <a href="#main-content" class="site-header__skip-link">پرش به محتوای اصلی</a>

      <div class="site-header__bar">
        <AppLogo class="site-header__logo" :compact-on-mobile="false" />

        <div class="site-header__actions">
          <button
            type="button"
            class="site-header__search-button"
            :class="searchOpen && 'site-header__search-button--active'"
            aria-label="جستجو"
            :aria-expanded="searchOpen"
            aria-controls="header-search-panel"
            @click="toggleSearch"
          >
            <CinematicIcon :name="searchOpen ? 'x' : 'search'" class="size-6" />
          </button>

          <NuxtLink
            :to="profilePath"
            class="site-header__login"
            :aria-label="authStore.isAuthenticated ? 'رفتن به حساب کاربری' : 'ورود به حساب'"
            :title="authStore.isAuthenticated ? 'حساب کاربری' : 'ورود و ثبت‌نام'"
            :aria-current="route.path.startsWith('/profile') ? 'page' : undefined"
          >
            <CinematicIcon :name="authStore.isAuthenticated ? 'user' : 'login'" class="size-6" aria-hidden="true" />
          </NuxtLink>
        </div>
      </div>

      <Transition name="search-drop">
        <div
          v-if="searchOpen"
          id="header-search-panel"
          class="site-header__search-panel"
          role="dialog"
          aria-label="جستجوی فیلم یا سریال"
        >
          <HeaderSearch
            input-id="header-search-input"
            :active="route.path === '/search'"
            autofocus
            compact-placeholder
            @submitted="searchOpen = false"
          />
        </div>
      </Transition>
    </header>

    <DesktopHeader class="hidden lg:block" />

    <nav class="mobile-bottom-nav" aria-label="ناوبری اصلی موبایل">
      <NuxtLink
        to="/"
        class="mobile-bottom-nav__item"
        :class="activeBottomItem === 'home' && 'mobile-bottom-nav__item--active'"
        :aria-current="activeBottomItem === 'home' ? 'page' : undefined"
      >
        <CinematicIcon name="home" class="mobile-bottom-nav__icon" :stroke-width="activeBottomItem === 'home' ? 2.25 : 1.8" />
        <span>خانه</span>
      </NuxtLink>

      <NuxtLink
        to="/movies"
        class="mobile-bottom-nav__item"
        :class="activeBottomItem === 'movies' && 'mobile-bottom-nav__item--active'"
        :aria-current="activeBottomItem === 'movies' ? 'page' : undefined"
      >
        <CinematicIcon name="movie" class="mobile-bottom-nav__icon" :stroke-width="activeBottomItem === 'movies' ? 2.25 : 1.8" />
        <span>فیلم‌ها</span>
      </NuxtLink>

      <NuxtLink
        to="/series"
        class="mobile-bottom-nav__item"
        :class="activeBottomItem === 'series' && 'mobile-bottom-nav__item--active'"
        :aria-current="activeBottomItem === 'series' ? 'page' : undefined"
      >
        <CinematicIcon name="series" class="mobile-bottom-nav__icon" :stroke-width="activeBottomItem === 'series' ? 2.25 : 1.8" />
        <span>سریال‌ها</span>
      </NuxtLink>

      <button
        type="button"
        class="mobile-bottom-nav__item"
        :class="activeBottomItem === 'menu' && 'mobile-bottom-nav__item--active'"
        aria-label="باز کردن منو"
        aria-controls="mobile-sidebar"
        :aria-expanded="sidebarOpen"
        @click="toggleSidebar"
      >
        <CinematicIcon :name="sidebarOpen ? 'x' : 'menu'" class="mobile-bottom-nav__icon" :stroke-width="activeBottomItem === 'menu' ? 2.25 : 1.8" />
        <span>منو</span>
      </button>
    </nav>

    <ClientOnly>
      <!-- Lazy on purpose: the drawer pulls in gsap (~27 kB gzip). Statically
           imported here it landed in the entry chunk and every page paid for a
           menu most visits never open. -->
      <LazyMobileSidebar
        v-if="!isDesktop && sidebarEverOpened"
        v-model:open="sidebarOpen"
      />
    </ClientOnly>

    <!-- Invisible leading-edge swipe strip to open the sidebar on touch. -->
    <button
      v-if="!isDesktop"
      type="button"
      class="mobile-edge-swipe"
      aria-hidden="true"
      tabindex="-1"
      :class="{ 'mobile-edge-swipe--active': !sidebarOpen }"
      @touchstart.passive="handleSwipeStart"
      @touchmove.passive="handleSwipeMove"
      @touchend.passive="handleSwipeEnd"
      @touchcancel.passive="handleSwipeEnd"
    />
  </div>
</template>

<style scoped>
.site-header-root {
  --stream-chrome: #0b0d12;
  --stream-chrome-elevated: #12151c;
  --stream-border: rgb(255 255 255 / 8%);
  --stream-text: #f7f7f8;
  --stream-muted: #a5a8b0;
  --stream-active: #e4ad49;
  display: contents;
}

.site-header {
  position: sticky;
  min-height: calc(var(--header-height) + env(safe-area-inset-top, 0px));
  padding-top: env(safe-area-inset-top, 0px);
  border-bottom: 0;
  background: none;
  color: var(--stream-text);
  box-shadow: none;
  -webkit-backdrop-filter: none;
  backdrop-filter: none;
}

.site-header__bar {
  display: flex;
  width: 100%;
  max-width: var(--layout-max);
  height: var(--header-height);
  margin-inline: auto;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  padding-inline: var(--layout-gutter);
}

.site-header__logo {
  color: var(--stream-text);
}

.site-header__actions {
  display: flex;
  flex: none;
  align-items: center;
  gap: .25rem;
}

.site-header__search-button {
  display: grid;
  width: var(--touch-target);
  height: var(--touch-target);
  flex: none;
  place-items: center;
  border: 1px solid rgb(255 255 255 / 6%);
  border-radius: .7rem;
  background: rgb(255 255 255 / 3%);
  color: #fff;
  box-shadow: inset 0 1px 0 rgb(255 255 255 / 5%);
  transition: color var(--motion-fast) var(--ease-out), background-color var(--motion-fast) var(--ease-out);
  -webkit-tap-highlight-color: transparent;
}

.site-header__search-button:hover,
.site-header__search-button:focus-visible,
.site-header__search-button--active {
  background: rgb(255 255 255 / 6%);
  color: #fff;
}

.site-header__login {
  display: grid;
  width: var(--touch-target);
  height: var(--touch-target);
  flex: none;
  place-items: center;
  border: 1px solid rgb(255 255 255 / 6%);
  border-radius: .7rem;
  background: rgb(255 255 255 / 3%);
  color: #fff;
  box-shadow: inset 0 1px 0 rgb(255 255 255 / 5%);
  transition: color var(--motion-fast) var(--ease-out), background-color var(--motion-fast) var(--ease-out);
  -webkit-tap-highlight-color: transparent;
}

.site-header__login:hover,
.site-header__login:focus-visible,
.site-header__login[aria-current='page'] {
  background: rgb(255 255 255 / 6%);
  color: #fff;
}

.site-header__skip-link {
  position: absolute;
  inset-inline-start: 1rem;
  top: .35rem;
  z-index: 90;
  transform: translateY(-5rem);
  border-radius: .5rem;
  background: var(--stream-active);
  padding: .45rem .75rem;
  color: #181006;
  font-size: .75rem;
  font-weight: 800;
  transition: transform var(--motion-fast) var(--ease-out);
}

.site-header__skip-link:focus {
  transform: translateY(0);
}

.site-header__search-panel {
  position: absolute;
  inset-inline: var(--layout-gutter);
  top: calc(100% + .5rem);
  z-index: 75;
  width: auto;
  max-width: 30rem;
  margin-inline: auto;
  border: 1px solid var(--stream-border);
  border-radius: 1rem;
  padding: .65rem;
  background: color-mix(in srgb, var(--stream-chrome-elevated) 97%, transparent);
  box-shadow: 0 20px 48px rgb(0 0 0 / 42%);
}

.site-header__search-panel :deep(.header-search) {
  height: 2.75rem;
  border-radius: .8rem;
  background: rgb(255 255 255 / 5%);
}

.site-header__search-panel :deep(.header-search--open) {
  border-radius: .8rem .8rem .25rem .25rem;
}

.site-header__search-panel :deep(.header-search__kbd) {
  display: none;
}

.mobile-bottom-nav {
  position: fixed;
  inset-inline: 0;
  bottom: 0;
  z-index: 70;
  display: grid;
  min-height: calc(var(--mobile-bottom-nav-height) + env(safe-area-inset-bottom, 0px));
  grid-template-columns: repeat(4, minmax(0, 1fr));
  padding: .15rem max(.35rem, env(safe-area-inset-right, 0px)) env(safe-area-inset-bottom, 0px) max(.35rem, env(safe-area-inset-left, 0px));
  border-top: 1px solid var(--stream-border);
  background: var(--stream-chrome);
  box-shadow: 0 -10px 28px rgb(0 0 0 / 24%);
}

.mobile-bottom-nav__item {
  display: flex;
  min-width: 0;
  min-height: 3rem;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: .18rem;
  border-radius: .65rem;
  color: var(--stream-muted);
  font-size: .65rem;
  font-weight: 650;
  line-height: 1.15;
  transition: color var(--motion-fast) var(--ease-out);
  -webkit-tap-highlight-color: transparent;
}

.mobile-bottom-nav__icon {
  width: 1.25rem;
  height: 1.25rem;
}

.mobile-bottom-nav__item--active {
  color: var(--stream-active);
}

.mobile-bottom-nav__item:focus-visible {
  outline: 2px solid color-mix(in srgb, var(--stream-active) 72%, transparent);
  outline-offset: -2px;
}

.search-drop-enter-active,
.search-drop-leave-active {
  transition: opacity var(--motion-fast) var(--ease-out), transform var(--motion-base) var(--ease-emphasized);
}

.search-drop-enter-from,
.search-drop-leave-to {
  opacity: 0;
  transform: translateY(-.35rem) scale(.985);
}

@media (min-width: 1024px) {
  .mobile-bottom-nav {
    display: none;
  }

}

@media (prefers-reduced-motion: reduce) {
  .site-header__search-button,
  .site-header__login,
  .mobile-bottom-nav__item,
  .search-drop-enter-active,
  .search-drop-leave-active {
    transition: none;
  }
}

/* Leading-edge (right in RTL) invisible strip that captures the open swipe. */
.mobile-edge-swipe {
  position: fixed;
  inset-block: 0;
  inset-inline-end: 0;
  z-index: 55;
  width: 1.75rem;
  padding: 0;
  border: 0;
  background: transparent;
  cursor: ew-resize;
  opacity: 0;
  pointer-events: none;
}

.mobile-edge-swipe--active {
  pointer-events: auto;
}
</style>
