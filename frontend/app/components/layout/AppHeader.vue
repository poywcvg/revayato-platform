<script setup lang="ts">
const route = useRoute()
const authStore = useAuthStore()
// Mobile chrome (compact header + bottom nav + drawer) owns phone *and* tablet
// widths; the desktop header only takes over from lg (1024px) up. Without this,
// tablets were stranded with no main nav links at all.
const isDesktop = useMediaQuery('(min-width: 1024px)')

const sidebarOpen = ref(false)
// The drawer is only mounted once the user reaches for it, so its code and CSS
// never cost a visit that does not open the menu.
const sidebarEverOpened = ref(false)
const searchOpen = ref(false)
const searchRoot = useTemplateRef<HTMLElement>('searchRoot')
// Transparent over the page at rest; a floating glass capsule once scrolled.
const { y: scrollY } = useWindowScroll()
const isScrolled = computed(() => scrollY.value > 8)

const profilePath = computed(() => authStore.isAuthenticated
  ? '/profile'
  : `/auth/login?redirect=${encodeURIComponent(route.fullPath)}`)

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
    <header
      ref="searchRoot"
      class="site-header sticky top-0 z-[60] lg:hidden"
      :class="{ 'site-header--search-open': searchOpen, 'site-header--scrolled': isScrolled || searchOpen }"
    >
      <a href="#main-content" class="site-header__skip-link">پرش به محتوای اصلی</a>

      <div class="site-header__bar">
        <AppLogo class="site-header__logo" :compact-on-mobile="false" />

        <div class="site-header__actions">
          <button
            type="button"
            class="site-header__search-button"
            :class="searchOpen && 'site-header__search-button--active'"
            :aria-label="searchOpen ? 'بستن جستجو' : 'جستجو'"
            :aria-expanded="searchOpen"
            aria-controls="header-search-panel"
            @click="toggleSearch"
          >
            <CinematicIcon :name="searchOpen ? 'x' : 'search'" class="size-[1.15rem]" />
            <span class="site-header__search-label" aria-hidden="true">جستجو</span>
          </button>

          <button
            type="button"
            class="site-header__login"
            :class="sidebarOpen && 'site-header__login--active'"
            aria-label="باز کردن منو"
            aria-controls="mobile-sidebar"
            :aria-expanded="sidebarOpen"
            title="منو"
            @click="toggleSidebar"
          >
            <CinematicIcon :name="sidebarOpen ? 'x' : 'menu'" class="size-[1.3rem]" aria-hidden="true" />
          </button>
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

    <MobileBottomNavigation :profile-path="profilePath" />

    <ClientOnly>
      <!-- Lazy on purpose: most visits never open the drawer, so keep its UI
           and motion chunk out of the initial page payload. -->
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
/* Mobile / tablet header (below lg). Same language as the desktop bar:
   soft glass rails, mint for anything active, every control a pill. */
.site-header-root {
  --mh-accent: var(--theme-accent-primary, #b0e4cc);
  --mh-ink: var(--theme-text-primary, #fff);
  --mh-ink-soft: var(--theme-text-secondary, #c4c4c4);
  --mh-rail: color-mix(in srgb, var(--mh-ink) 6%, transparent);
  --mh-rail-line: color-mix(in srgb, var(--mh-ink) 10%, transparent);
  --mh-tint: color-mix(in srgb, var(--mh-accent) 15%, transparent);
  display: contents;
}

.site-header {
  position: sticky;
  min-height: calc(var(--header-height) + env(safe-area-inset-top, 0px));
  padding-top: env(safe-area-inset-top, 0px);
  border-bottom: 0;
  background: none;
  color: var(--mh-ink);
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
  gap: .75rem;
  padding-inline: var(--layout-gutter);
  border: 1px solid transparent;
  transition:
    background-color 280ms ease,
    border-color 280ms ease,
    border-radius 280ms cubic-bezier(.22, 1, .36, 1),
    box-shadow 280ms ease,
    margin 280ms cubic-bezier(.22, 1, .36, 1),
    padding 280ms cubic-bezier(.22, 1, .36, 1);
}

/* Scrolled: the bar lifts into a floating glass capsule. */
.site-header--scrolled .site-header__bar {
  width: auto;
  height: calc(var(--header-height) - .5rem);
  margin: .35rem var(--layout-gutter) 0;
  padding-inline: .9rem .35rem;
  border-color: var(--mh-rail-line);
  border-radius: 999px;
  background: color-mix(in srgb, var(--theme-bg-soft, #161518) 86%, transparent);
  box-shadow: 0 .75rem 1.8rem rgb(0 0 0 / 30%);
  -webkit-backdrop-filter: blur(14px) saturate(1.3);
  backdrop-filter: blur(14px) saturate(1.3);
}

.site-header__logo {
  color: var(--mh-ink);
}

.site-header__actions {
  display: flex;
  flex: none;
  align-items: center;
  gap: .4rem;
}

.site-header__search-button,
.site-header__login {
  display: inline-flex;
  height: 2.6rem;
  flex: none;
  align-items: center;
  justify-content: center;
  gap: .45rem;
  border: 0;
  border-radius: 999px;
  background: var(--mh-rail);
  box-shadow: inset 0 0 0 1px var(--mh-rail-line);
  color: var(--mh-ink-soft);
  transition:
    background-color 180ms ease,
    color 180ms ease,
    box-shadow 180ms ease,
    transform 200ms cubic-bezier(.34, 1.56, .64, 1);
  -webkit-tap-highlight-color: transparent;
}

/* Search reads as a field, not an icon: a short pill with its label. */
.site-header__search-button {
  padding-inline: .85rem 1rem;
}

.site-header__search-label {
  font-size: .82rem;
  font-weight: 600;
}

.site-header__login {
  width: 2.6rem;
}

.site-header__search-button:active,
.site-header__login:active {
  transform: scale(.94);
}

.site-header__search-button:focus-visible,
.site-header__login:focus-visible {
  outline: 2px solid var(--mh-accent);
  outline-offset: 2px;
}

.site-header__search-button--active,
.site-header__login--active {
  background: var(--mh-tint);
  box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--mh-accent) 32%, transparent);
  color: var(--mh-accent);
}

/* Open search collapses the trigger to a round close button. */
.site-header__search-button--active {
  width: 2.6rem;
  padding: 0;
}

.site-header__search-button--active .site-header__search-label {
  display: none;
}

@media (hover: hover) and (pointer: fine) {
  .site-header__search-button:hover,
  .site-header__login:hover {
    background: var(--mh-tint);
    color: var(--mh-accent);
  }
}

@media (max-width: 359px) {
  .site-header__search-button { width: 2.6rem; padding: 0; }
  .site-header__search-label { display: none; }
}

.site-header__skip-link {
  position: absolute;
  inset-inline-start: 1rem;
  top: .35rem;
  z-index: 90;
  transform: translateY(-5rem);
  border-radius: 999px;
  background: var(--mh-accent);
  padding: .45rem .9rem;
  color: var(--theme-on-accent, #07110d);
  font-size: .75rem;
  font-weight: 800;
  transition: transform var(--motion-fast) var(--ease-out);
}

.site-header__skip-link:focus {
  transform: translateY(0);
}

/* The search sheet: just the search pill, floating under the bar. Its result
   list is the HeaderSearch panel itself, so there is one surface, not two. */
.site-header__search-panel {
  position: absolute;
  inset-inline: var(--layout-gutter);
  top: calc(100% + .45rem);
  z-index: 75;
  max-width: 34rem;
  margin-inline: auto;
  padding: .4rem;
  border: 1px solid var(--mh-rail-line);
  border-radius: 1.9rem;
  background: color-mix(in srgb, var(--theme-bg-elevated, #141414) 96%, transparent);
  box-shadow: 0 1.25rem 3rem rgb(0 0 0 / 42%);
  -webkit-backdrop-filter: blur(16px) saturate(1.3);
  backdrop-filter: blur(16px) saturate(1.3);
}

.site-header__search-panel :deep(.header-search__panel) {
  inset-inline: -.4rem;
  top: calc(100% + .8rem);
}

.search-drop-enter-active,
.search-drop-leave-active {
  transition: opacity 160ms ease, transform 260ms cubic-bezier(.22, 1, .36, 1);
  transform-origin: top center;
}

.search-drop-enter-from,
.search-drop-leave-to {
  opacity: 0;
  transform: translateY(-.4rem) scale(.97);
}

:global(html[data-theme="light"]) .site-header--scrolled .site-header__bar {
  background: color-mix(in srgb, var(--theme-bg-surface, #fff) 88%, transparent);
  box-shadow: 0 .75rem 1.8rem rgb(23 50 38 / 12%);
}

:global(html[data-theme="light"]) .site-header__search-panel {
  background: var(--theme-bg-surface, #fff);
  box-shadow: var(--theme-shadow-float, 0 18px 40px rgb(23 50 38 / 14%));
}

@media (prefers-reduced-motion: reduce) {
  .site-header__bar,
  .site-header__search-button,
  .site-header__login,
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
