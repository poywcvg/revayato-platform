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
// A solid bar at all times; once scrolled it only gains a soft shadow.
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

        <!-- Uiverse-style search field: reads as an input, opens the real one. -->
        <button
          type="button"
          class="site-header__search"
          :class="searchOpen && 'site-header__search--active'"
          :aria-label="searchOpen ? 'بستن جستجو' : 'جستجوی فیلم و سریال'"
          :aria-expanded="searchOpen"
          aria-controls="header-search-panel"
          @click="toggleSearch"
        >
          <CinematicIcon :name="searchOpen ? 'x' : 'search'" class="site-header__search-icon" />
          <span class="site-header__search-label" aria-hidden="true">جستجوی فیلم و سریال</span>
        </button>

        <div class="site-header__actions">
          <ThemeToggle size="sm" class="site-header__theme" />

          <!-- Uiverse burger: three bars that fold into an X while the menu is open. -->
          <button
            type="button"
            class="site-header__burger"
            :class="sidebarOpen && 'site-header__burger--open'"
            :aria-label="sidebarOpen ? 'بستن منو' : 'باز کردن منو'"
            aria-controls="mobile-sidebar"
            :aria-expanded="sidebarOpen"
            title="منو"
            @click="toggleSidebar"
          >
            <span class="site-header__burger-bars" aria-hidden="true"><i /><i /><i /></span>
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
/* Mobile / tablet header (below lg): a solid bar that never sits on top of the
   page, so artwork underneath can't tint it or swallow its controls. */
.site-header-root {
  --mh-accent: var(--theme-accent-primary, #b0e4cc);
  --mh-ink: var(--theme-text-primary, #fff);
  --mh-ink-soft: var(--theme-text-secondary, #c4c4c4);
  --mh-field: var(--theme-bg-soft, #1b1d1c);
  --mh-line: var(--theme-border, rgb(255 255 255 / 10%));
  --mh-tint: color-mix(in srgb, var(--mh-accent) 15%, transparent);
  display: contents;
}

.site-header {
  position: sticky;
  min-height: calc(var(--header-height) + env(safe-area-inset-top, 0px));
  padding-top: env(safe-area-inset-top, 0px);
  border-bottom: 1px solid var(--mh-line);
  background: var(--theme-bg-main, #0f1211);
  color: var(--mh-ink);
  box-shadow: none;
  transition: box-shadow 220ms ease;
}

.site-header--scrolled {
  box-shadow: none;
}

.site-header__bar {
  display: flex;
  width: 100%;
  max-width: var(--layout-max);
  height: var(--header-height);
  margin-inline: auto;
  align-items: center;
  gap: .6rem;
  padding-inline: var(--layout-gutter);
}

.site-header__logo {
  flex: none;
  color: var(--mh-ink);
}

/* Search field — after Uiverse's "search input" pattern: a filled pill with an
   inset hairline, the icon leading, and the accent ring on focus/active. */
.site-header__search {
  display: flex;
  min-width: 0;
  height: 2.5rem;
  flex: 1 1 auto;
  align-items: center;
  gap: .5rem;
  padding-inline: .85rem;
  border: 0;
  border-radius: 999px;
  background: var(--mh-field);
  box-shadow: inset 0 0 0 1px var(--mh-line);
  color: var(--theme-text-muted, var(--mh-ink-soft));
  text-align: start;
  transition: box-shadow 180ms ease, color 180ms ease, background-color 180ms ease;
  -webkit-tap-highlight-color: transparent;
}

.site-header__search-icon {
  width: 1.1rem;
  height: 1.1rem;
  flex: none;
  color: var(--mh-ink-soft);
}

.site-header__search-label {
  overflow: hidden;
  font-size: .82rem;
  font-weight: 500;
  white-space: nowrap;
  text-overflow: ellipsis;
}

.site-header__search--active,
.site-header__search:focus-visible {
  outline: none;
  box-shadow: inset 0 0 0 1.5px var(--mh-accent), 0 0 0 3px var(--mh-tint);
  color: var(--mh-accent);
}

.site-header__search--active .site-header__search-icon {
  color: var(--mh-accent);
}

.site-header__actions {
  display: flex;
  flex: none;
  align-items: center;
  gap: .45rem;
}

/* Burger — after Uiverse's animated hamburger: three bars, the outer two
   rotate into an X and the middle one collapses. */
.site-header__burger {
  display: inline-grid;
  width: 2.5rem;
  height: 2.5rem;
  flex: none;
  place-items: center;
  border: 0;
  border-radius: 999px;
  background: var(--mh-field);
  box-shadow: inset 0 0 0 1px var(--mh-line);
  color: var(--mh-ink);
  transition: background-color 180ms ease, color 180ms ease, transform 200ms cubic-bezier(.34, 1.56, .64, 1);
  -webkit-tap-highlight-color: transparent;
}

.site-header__burger-bars {
  position: relative;
  display: block;
  width: 1.15rem;
  height: .85rem;
}

.site-header__burger-bars i {
  position: absolute;
  inset-inline: 0;
  height: 2px;
  border-radius: 2px;
  background: currentColor;
  transition: transform 260ms cubic-bezier(.22, 1, .36, 1), opacity 160ms ease, width 260ms ease;
}

.site-header__burger-bars i:nth-child(1) { top: 0; }
.site-header__burger-bars i:nth-child(2) { top: calc(50% - 1px); width: 70%; }
.site-header__burger-bars i:nth-child(3) { bottom: 0; }

.site-header__burger--open {
  background: var(--mh-tint);
  color: var(--mh-accent);
}

.site-header__burger--open .site-header__burger-bars i:nth-child(1) {
  transform: translateY(calc(.425rem - 1px)) rotate(45deg);
}

.site-header__burger--open .site-header__burger-bars i:nth-child(2) {
  opacity: 0;
  width: 0;
}

.site-header__burger--open .site-header__burger-bars i:nth-child(3) {
  transform: translateY(calc(-.425rem + 1px)) rotate(-45deg);
}

.site-header__burger:active,
.site-header__search:active {
  transform: scale(.96);
}

.site-header__burger:focus-visible {
  outline: 2px solid var(--mh-accent);
  outline-offset: 2px;
}

@media (hover: hover) and (pointer: fine) {
  .site-header__search:hover {
    box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--mh-accent) 45%, transparent);
  }

  .site-header__burger:hover {
    background: var(--mh-tint);
    color: var(--mh-accent);
  }
}

/* Narrow phones: the field keeps its icon, the hint text shortens away. */
@media (max-width: 359px) {
  .site-header__search-label { display: none; }
  .site-header__search { flex: 0 0 2.5rem; justify-content: center; padding: 0; margin-inline-start: auto; }
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
  border: 1px solid var(--mh-line);
  border-radius: 1.9rem;
  background: color-mix(in srgb, var(--theme-bg-elevated, #141414) 96%, transparent);
  box-shadow: none;
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

html[data-theme="light"] .site-header--scrolled {
  box-shadow: none;
}

html[data-theme="light"] .site-header__search-panel {
  background: var(--theme-bg-surface, #fff);
  box-shadow: var(--theme-shadow-float, 0 18px 40px rgb(23 50 38 / 14%));
}

@media (prefers-reduced-motion: reduce) {
  .site-header,
  .site-header__search,
  .site-header__burger,
  .site-header__burger-bars i,
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
