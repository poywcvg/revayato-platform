<script setup lang="ts">
const route = useRoute()
const { watchlistIds } = useLibrary()
const authStore = useAuthStore()
const { y } = useWindowScroll()

const profilePath = computed(() => authStore.isAuthenticated
  ? '/profile'
  : `/auth/login?redirect=${encodeURIComponent(route.fullPath)}`)

interface HeaderNavItem {
  label: string
  to: string
  match: (path: string) => boolean
}

const navItems: HeaderNavItem[] = [
  { label: 'خانه', to: '/', match: path => path === '/' },
  { label: 'فیلم‌ها', to: '/movies', match: path => path.startsWith('/movies') },
  { label: 'سریال‌ها', to: '/series', match: path => path.startsWith('/series') },
  { label: '۲۵۰ برتر', to: '/top250', match: path => path.startsWith('/top250') },
  { label: 'تماشای گروهی', to: '/watch-party', match: path => path.startsWith('/watch-party') },
]

const pillItems = navItems.map(({ label, to }) => ({ label, href: to }))
const activeNavHref = computed(() => navItems.find(item => item.match(route.path))?.to)

// Home floats the bar transparently over the hero until the viewer scrolls a
// little; every other route wears a solid glass bar from the first pixel.
const isOverlay = computed(() => route.path === '/')
const isHomeAtTop = computed(() => isOverlay.value && y.value < 24)
// Past a few pixels the bar detaches into a floating, rounded capsule.
const isScrolled = computed(() => y.value > 8)

// Thin reading-progress line under the bar. rAF-throttled so measuring
// scrollHeight (a reflow) never happens more than once per frame.
const scrollProgress = ref(0)
let ticking = false
function measureProgress() {
  if (!import.meta.client) return
  const doc = document.documentElement
  const max = doc.scrollHeight - window.innerHeight
  scrollProgress.value = max > 8 ? Math.min(1, Math.max(0, window.scrollY / max)) : 0
}
function onScroll() {
  if (ticking) return
  ticking = true
  requestAnimationFrame(() => { measureProgress(); ticking = false })
}
onMounted(() => {
  measureProgress()
  useEventListener(window, 'scroll', onScroll, { passive: true })
  useEventListener(window, 'resize', onScroll, { passive: true })
})
watch(() => route.fullPath, () => nextTick(measureProgress))
</script>

<template>
  <header
    class="rvh"
    :class="{
      'rvh--overlay': isOverlay,
      'rvh--top': isHomeAtTop,
      'rvh--scrolled': isScrolled,
    }"
  >
    <a href="#main-content" class="rvh__skip">پرش به محتوای اصلی</a>

    <div class="rvh__inner">
      <div class="rvh__bar">
        <AppLogo class="rvh__logo" />

        <PillNav
          class="rvh__nav"
          :items="pillItems"
          :active-href="activeNavHref"
          :mobile-menu="false"
          :initial-load-animation="false"
          base-color="var(--rvh-accent)"
          pill-color="transparent"
          pill-text-color="var(--theme-text-secondary, #c4c4c4)"
          hovered-pill-text-color="var(--theme-on-accent, #07110d)"
        />

        <HeaderCategories class="rvh__cats" />

        <HeaderSearch class="rvh__search" :active="route.path === '/search'" />

        <div class="rvh__actions" aria-label="ابزارهای حساب">
          <NotificationCenter />

          <NuxtLink
            to="/watchlist"
            class="rvh__action"
            :class="route.path === '/watchlist' && 'rvh__action--active'"
            aria-label="لیست من"
            title="لیست من"
            :aria-current="route.path === '/watchlist' ? 'page' : undefined"
          >
            <CinematicIcon name="bookmark" class="size-5" :filled="route.path === '/watchlist'" />
            <span v-if="watchlistIds.length" class="rvh__badge tabular-nums">{{ watchlistIds.length }}</span>
          </NuxtLink>

          <NuxtLink
            :to="profilePath"
            class="rvh__action rvh__action--profile"
            :class="route.path.startsWith('/profile') && 'rvh__action--active'"
            :aria-label="authStore.isAuthenticated ? 'پروفایل' : 'ورود به حساب'"
            :title="authStore.isAuthenticated ? 'پروفایل' : 'ورود و ثبت‌نام'"
            :aria-current="route.path.startsWith('/profile') ? 'page' : undefined"
          >
            <CinematicIcon :name="authStore.isAuthenticated ? 'user' : 'login'" class="size-5" :stroke-width="route.path.startsWith('/profile') ? 2.2 : 1.8" />
            <span v-if="!authStore.isAuthenticated" class="rvh__action-label">ورود</span>
          </NuxtLink>
        </div>
      </div>

      <span class="rvh__progress" aria-hidden="true" :style="{ '--rvh-progress': scrollProgress }" />
    </div>
  </header>
</template>

<style scoped>
/* =====================================================================
   Revayato desktop header (lg / 1024px and up).
   One palette, taken from PillNav: a soft glass rail, mint (the brand
   accent) for hover / active / focus, pine for the progress tail. Every
   control is a pill of the same height (--rvh-control), so the row reads
   as one calm line: logo · nav · categories ····· search · account.
   The search widens when used; the bar condenses into a floating capsule
   on scroll and floats transparently over the home hero.
   ===================================================================== */
.rvh {
  --rvh-accent: var(--theme-accent-primary, #b0e4cc);
  --rvh-control: 2.6rem;
  --rvh-ink: var(--theme-text-primary, #fff);
  --rvh-ink-soft: var(--theme-text-secondary, #c4c4c4);
  --rvh-rail: color-mix(in srgb, var(--rvh-ink) 5%, transparent);
  --rvh-rail-line: color-mix(in srgb, var(--rvh-ink) 9%, transparent);
  --rvh-tint: color-mix(in srgb, var(--rvh-accent) 14%, transparent);
  /* Feed the notification bell's focus ring the right surface colour. */
  --header-ring: var(--theme-bg-soft, #161518);
  position: sticky;
  top: 0;
  z-index: 50;
  color: var(--rvh-ink);
}

.rvh__inner {
  position: relative;
  margin-inline: auto;
  max-width: var(--layout-max);
  padding-inline: clamp(.75rem, 2.4vw, 2rem);
}

/* ---- The bar ---- */
.rvh__bar {
  position: relative;
  display: flex;
  align-items: center;
  gap: clamp(.5rem, 1vw, .9rem);
  height: 4.5rem;
  padding-inline: clamp(.5rem, 1.1vw, .9rem);
  border: 1px solid transparent;
  border-radius: 0;
  transition:
    height 300ms cubic-bezier(.22, 1, .36, 1),
    background-color 300ms ease,
    border-color 300ms ease,
    border-radius 300ms cubic-bezier(.22, 1, .36, 1),
    box-shadow 300ms ease,
    margin-top 300ms cubic-bezier(.22, 1, .36, 1);
  animation: rvh-drop .5s cubic-bezier(.22, 1, .36, 1) both;
}

@keyframes rvh-drop {
  from { opacity: 0; transform: translateY(-.55rem); }
  to { opacity: 1; transform: none; }
}

/* Non-home routes: a quiet glass band from the first pixel. */
.rvh:not(.rvh--overlay) .rvh__bar {
  background: color-mix(in srgb, var(--theme-bg-soft, #161518) 78%, transparent);
  border-bottom-color: var(--rvh-rail-line);
  -webkit-backdrop-filter: blur(12px) saturate(1.25);
  backdrop-filter: blur(12px) saturate(1.25);
}

/* Home at the very top: nothing behind it but the hero. */
.rvh--top .rvh__bar {
  background: transparent;
  border-color: transparent;
}

/* Scrolled (any route): lift into a floating pill-shaped capsule. */
.rvh--scrolled .rvh__bar {
  height: 3.6rem;
  margin-top: .6rem;
  border-color: var(--rvh-rail-line);
  border-radius: 1.8rem;
  background: color-mix(in srgb, var(--theme-bg-soft, #161518) 86%, transparent);
  box-shadow:
    0 .9rem 2.2rem rgb(0 0 0 / 30%),
    inset 0 1px 0 rgb(255 255 255 / 5%);
  -webkit-backdrop-filter: blur(14px) saturate(1.3);
  backdrop-filter: blur(14px) saturate(1.3);
}

.rvh__logo {
  flex: none;
  color: var(--rvh-ink);
}

/* ---- Primary navigation (PillNav): glass rail, mint hover, mint dot ---- */
.rvh__nav {
  flex: none;
  min-width: 0;
  width: auto;
  --nav-h: var(--rvh-control);
  --pill-gap: 2px;
  --pill-pad-x: clamp(.65rem, .95vw, 1.05rem);
  --pill-font-size: .875rem;
  --track-bg: var(--rvh-rail);
  --track-border: var(--rvh-rail-line);
  --pill-active-bg: var(--rvh-tint);
  --pill-active-text: var(--rvh-accent);
  --dot-bg: var(--rvh-accent);
  --dot-size: 4px;
  --dot-offset: 5px;
}

/* ---- Categories trigger: same pill as everything else ---- */
.rvh__cats { flex: none; }

.rvh__cats :deep(.header-categories__trigger) {
  height: var(--rvh-control);
  padding-inline: .8rem;
  border-radius: 999px;
  background: var(--rvh-rail);
  box-shadow: inset 0 0 0 1px var(--rvh-rail-line);
  color: var(--rvh-ink-soft);
  transition: background-color 180ms ease, color 180ms ease, box-shadow 180ms ease;
}

.rvh__cats :deep(.header-categories__trigger:hover),
.rvh__cats :deep(.header-categories__trigger[aria-expanded="true"]) {
  background: var(--rvh-tint);
  box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--rvh-accent) 30%, transparent);
  color: var(--rvh-accent);
}

/* ---- Search: compact at rest, widens while in use ---- */
.rvh__search {
  --hs-h: var(--rvh-control);
  flex: 1 1 auto;
  min-width: 11rem;
  max-width: 19rem;
  margin-inline-start: auto;
  transition: max-width 420ms cubic-bezier(.22, 1, .36, 1);
}

.rvh__search:focus-within,
.rvh__search:has(.header-search--alive) {
  max-width: 34rem;
}

/* ---- Account cluster: one rail holding round icon buttons ---- */
.rvh__actions {
  display: flex;
  flex: none;
  align-items: center;
  gap: 2px;
  height: var(--rvh-control);
  padding: 3px;
  border-radius: 999px;
  background: var(--rvh-rail);
  box-shadow: inset 0 0 0 1px var(--rvh-rail-line);
}

.rvh__action,
.rvh__actions :deep(.site-header__icon-btn) {
  position: relative;
  display: grid;
  width: calc(var(--rvh-control) - 6px);
  height: calc(var(--rvh-control) - 6px);
  flex: none;
  place-items: center;
  border: 0;
  border-radius: 999px;
  background: transparent;
  color: var(--rvh-ink-soft);
  transition: background-color 180ms ease, color 180ms ease, transform 220ms cubic-bezier(.34, 1.56, .64, 1);
}

.rvh__action:hover,
.rvh__action:focus-visible,
.rvh__actions :deep(.site-header__icon-btn:hover),
.rvh__actions :deep(.site-header__icon-btn:focus-visible),
.rvh__actions :deep(.site-header__icon-btn--active) {
  background: var(--rvh-tint);
  color: var(--rvh-accent);
}

.rvh__action:active,
.rvh__actions :deep(.site-header__icon-btn:active) {
  transform: scale(.92);
}

.rvh__action--active {
  background: var(--rvh-tint);
  color: var(--rvh-accent);
}

.rvh__action:focus-visible,
.rvh__actions :deep(.site-header__icon-btn:focus-visible) {
  outline: 2px solid var(--rvh-accent);
  outline-offset: 1px;
}

/* Guests: the profile slot becomes the one solid mint call to action. */
.rvh__action--profile:has(.rvh__action-label) {
  width: auto;
  gap: .35rem;
  padding-inline: .8rem .95rem;
  background: var(--rvh-accent);
  color: var(--theme-on-accent, #07110d);
}

.rvh__action--profile:has(.rvh__action-label):hover,
.rvh__action--profile:has(.rvh__action-label):focus-visible {
  background: var(--theme-accent-primary-hover, #c8efdc);
  color: var(--theme-on-accent, #07110d);
}

.rvh__action-label {
  font-size: .8rem;
  font-weight: 800;
}

.rvh__badge {
  position: absolute;
  inset-block-start: 0;
  inset-inline-start: 0;
  display: grid;
  min-width: 1rem;
  min-height: 1rem;
  place-items: center;
  padding-inline: .2rem;
  border-radius: 999px;
  background: var(--rvh-accent);
  color: var(--theme-on-accent, #07110d);
  font-size: 0.75rem;
  font-weight: 900;
  line-height: 1;
  box-shadow: 0 0 0 2px var(--theme-bg-soft, #161518);
}

/* ---- Reading progress along the capsule's floor ---- */
.rvh__progress {
  position: absolute;
  inset-inline: calc(clamp(.75rem, 2.4vw, 2rem) + 1.4rem);
  bottom: 0;
  height: 2px;
  transform-origin: right center; /* RTL: fill from the leading edge */
  transform: scaleX(var(--rvh-progress, 0));
  border-radius: 999px;
  background: linear-gradient(to left, var(--rvh-accent), var(--theme-accent-crimson, #408a71));
  opacity: 0;
  transition: opacity 160ms ease;
  will-change: transform;
}

.rvh--scrolled .rvh__progress { opacity: .85; }

/* ---- Skip link ---- */
.rvh__skip {
  position: absolute;
  inset-inline-start: 1rem;
  top: .5rem;
  z-index: 10;
  transform: translateY(-5rem);
  border-radius: 999px;
  background: var(--rvh-accent);
  padding: .5rem 1rem;
  color: var(--theme-on-accent, #07110d);
  font-size: .8rem;
  font-weight: 800;
  transition: transform 120ms cubic-bezier(.2, .8, .2, 1);
}

.rvh__skip:focus { transform: translateY(0); }

/* ---- Narrow desktops (1024–1279px): tighter pills, smaller search ---- */
@media (min-width: 1024px) and (max-width: 1279px) {
  .rvh { --rvh-control: 2.45rem; }

  .rvh__nav {
    --pill-pad-x: .55rem;
    --pill-font-size: .82rem;
  }

  .rvh__search { min-width: 9rem; max-width: 15rem; }

  .rvh__search:focus-within,
  .rvh__search:has(.header-search--alive) { max-width: 24rem; }
}

/* Roomy layouts. */
@media (min-width: 1536px) {
  .rvh__nav { --pill-font-size: .92rem; }

  .rvh__search { max-width: 22rem; }

  .rvh__search:focus-within,
  .rvh__search:has(.header-search--alive) { max-width: 40rem; }
}

:global(html[data-theme="light"]) .rvh {
  --rvh-rail: color-mix(in srgb, var(--theme-text-primary) 4%, transparent);
  --rvh-rail-line: color-mix(in srgb, var(--theme-text-primary) 10%, transparent);
}

:global(html[data-theme="light"]) .rvh--scrolled .rvh__bar {
  box-shadow: 0 .8rem 2rem rgb(23 50 38 / 12%);
}

@media (prefers-reduced-motion: reduce) {
  .rvh__bar,
  .rvh__search,
  .rvh__action,
  .rvh__progress,
  .rvh__actions :deep(.site-header__icon-btn) {
    transition: none;
  }

  .rvh__bar { animation: none; }
}
</style>
