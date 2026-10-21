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
  /** Shown from 1440px up; below that it lives in the categories menu. */
  wide?: boolean
}

const navItems: HeaderNavItem[] = [
  { label: 'خانه', to: '/', match: path => path === '/' },
  { label: 'فیلم‌ها', to: '/movies', match: path => path.startsWith('/movies') },
  { label: 'سریال‌ها', to: '/series', match: path => path.startsWith('/series') },
  { label: 'تازه‌ها', to: '/new', match: path => path.startsWith('/new'), wide: true },
  { label: '۲۵۰ برتر', to: '/top250', match: path => path.startsWith('/top250') },
  { label: 'جدول پخش', to: '/schedule', match: path => path.startsWith('/schedule'), wide: true },
  { label: 'تماشای گروهی', to: '/watch-party', match: path => path.startsWith('/watch-party'), wide: true },
]

const username = computed(() => authStore.user?.username || '')
const avatar = computed(() => authStore.user?.profile?.avatar || '')
const initial = computed(() => (username.value.trim()[0] || 'ر').toUpperCase())
const onProfile = computed(() => route.path.startsWith('/profile'))

// Once the page moves, the bar switches to the raised surface tone so it
// reads as sitting over the content (a tone step, never a shadow).
const isScrolled = computed(() => y.value > 8)

// Thin reading-progress line on the bar's floor. rAF-throttled so measuring
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
  <header class="rvh" :class="{ 'rvh--scrolled': isScrolled }">
    <a href="#main-content" class="rvh__skip">پرش به محتوای اصلی</a>

    <!-- One bar across the full width: brand + navigation · search · account. -->
    <div class="rvh__row">
      <div class="rvh__start">
        <AppLogo class="rvh__logo" />

        <nav class="rvh__nav" aria-label="منوی اصلی">
          <NuxtLink
            v-for="item in navItems"
            :key="item.to"
            :to="item.to"
            class="rvh__link"
            :class="[item.match(route.path) && 'rvh__link--active', item.wide && 'rvh__link--wide']"
            :aria-current="item.match(route.path) ? 'page' : undefined"
          >
            {{ item.label }}
          </NuxtLink>

          <HeaderCategories class="rvh__cats" />
        </nav>
      </div>

      <HeaderSearch class="rvh__search" :active="route.path === '/search'" submit-button />

      <div class="rvh__end" aria-label="ابزارهای حساب">
        <NuxtLink
          to="/app"
          class="rvh__icon rvh__icon--app"
          :class="route.path.startsWith('/app') && 'rvh__icon--active'"
          aria-label="اپلیکیشن اندروید"
          title="اپلیکیشن اندروید"
        >
          <CinematicIcon name="smartphone" class="size-[1.15rem]" />
        </NuxtLink>

        <ThemeToggle size="sm" class="rvh__theme" />

        <NotificationCenter class="rvh__bell" />

        <NuxtLink
          to="/watchlist"
          class="rvh__icon"
          :class="route.path === '/watchlist' && 'rvh__icon--active'"
          aria-label="لیست من"
          title="لیست من"
          :aria-current="route.path === '/watchlist' ? 'page' : undefined"
        >
          <CinematicIcon name="bookmark" class="size-[1.15rem]" :filled="route.path === '/watchlist'" />
          <span v-if="watchlistIds.length" class="rvh__badge tabular-nums">{{ watchlistIds.length }}</span>
        </NuxtLink>

        <span class="rvh__divider" aria-hidden="true" />

        <NuxtLink
          v-if="authStore.isAuthenticated"
          :to="profilePath"
          class="rvh__me"
          :class="onProfile && 'rvh__me--active'"
          :aria-current="onProfile ? 'page' : undefined"
          :title="username || 'پروفایل من'"
        >
          <span class="rvh__avatar">
            <img v-if="avatar" :src="avatar" alt="" width="34" height="34" loading="lazy" decoding="async">
            <span v-else aria-hidden="true">{{ initial }}</span>
          </span>
          <span class="rvh__me-name">{{ username || 'پروفایل من' }}</span>
          <span class="sr-only">پروفایل من</span>
        </NuxtLink>

        <NuxtLink v-else :to="profilePath" class="rvh__login">
          <CinematicIcon name="login" class="size-[1.05rem]" :stroke-width="2" />
          <span>ورود / ثبت‌نام</span>
        </NuxtLink>
      </div>
    </div>

    <span class="rvh__progress" aria-hidden="true" :style="{ '--rvh-progress': scrollProgress }" />
  </header>
</template>

<style scoped>
/* =====================================================================
   Revayato desktop header (lg / 1024px and up) — a single flat bar that
   spans the whole viewport, aligned to the same gutter as the page.
   Start: logo + text navigation (the current page gets an accent rule on
   the bar's floor). Middle: search, which takes the free room. End: app,
   theme, notifications, watchlist, then the account. No shadows, no blur:
   surfaces are separated by a hairline and a tone step on scroll.
   ===================================================================== */
.rvh {
  --rvh-accent: var(--theme-accent-primary, #b0e4cc);
  --rvh-on-accent: var(--theme-on-accent, #07110d);
  --rvh-ink: var(--theme-text-primary, #fff);
  --rvh-ink-soft: var(--theme-text-secondary, #c4c4c4);
  --rvh-muted: var(--theme-text-muted, #979797);
  --rvh-h: var(--header-height, 4.5rem);
  --rvh-control: 2.5rem;
  --rvh-line: color-mix(in srgb, var(--rvh-ink) 9%, transparent);
  --rvh-tint: color-mix(in srgb, var(--rvh-ink) 6%, transparent);
  --rvh-bg: var(--theme-bg-main, #1d1c21);
  /* Feed the notification bell's focus ring the right surface colour. */
  --header-ring: var(--rvh-bg);
  position: sticky;
  top: 0;
  z-index: 50;
  height: var(--rvh-h);
  border-bottom: 1px solid var(--rvh-line);
  background: var(--rvh-bg);
  color: var(--rvh-ink);
  transition: background-color 200ms ease;
}

.rvh--scrolled { --rvh-bg: var(--theme-bg-soft, #161518); }

.rvh__row {
  display: flex;
  height: 100%;
  align-items: center;
  gap: clamp(1rem, 2vw, 2.5rem);
  padding-inline: var(--layout-gutter);
}

/* ---- Brand + navigation ---- */
.rvh__start {
  display: flex;
  height: 100%;
  min-width: 0;
  flex: none;
  align-items: center;
  gap: clamp(1rem, 2vw, 2.25rem);
}

.rvh__logo {
  flex: none;
  color: var(--rvh-ink);
}

.rvh__nav {
  display: flex;
  height: 100%;
  align-items: stretch;
  gap: clamp(.15rem, .5vw, .6rem);
}

.rvh__link {
  position: relative;
  display: inline-flex;
  flex: none;
  align-items: center;
  padding-inline: .7rem;
  color: var(--rvh-ink-soft);
  font-size: .92rem;
  font-weight: 600;
  white-space: nowrap;
  transition: color 160ms ease;
}

/* The active rule sits on the bar's floor, over the hairline. */
.rvh__link::after {
  content: "";
  position: absolute;
  inset-inline: .7rem;
  bottom: -1px;
  height: 3px;
  border-radius: 3px 3px 0 0;
  background: var(--rvh-accent);
  transform: scaleX(0);
  transition: transform 220ms cubic-bezier(.22, 1, .36, 1);
}

.rvh__link:hover { color: var(--rvh-ink); }

.rvh__link--active {
  color: var(--rvh-ink);
  font-weight: 700;
}

.rvh__link--active::after { transform: scaleX(1); }

.rvh__link:focus-visible {
  outline: 2px solid var(--rvh-accent);
  outline-offset: -.9rem;
  border-radius: .6rem;
}

/* Categories trigger: dressed like a nav link. */
.rvh__cats {
  display: flex;
  flex: none;
  align-items: center;
}

.rvh__cats :deep(.header-categories__trigger) {
  height: var(--rvh-control);
  padding-inline: .7rem;
  border-radius: .7rem;
  background: transparent;
  box-shadow: none;
  color: var(--rvh-ink-soft);
  font-size: .92rem;
  font-weight: 600;
  transition: background-color 160ms ease, color 160ms ease;
}

.rvh__cats :deep(.header-categories__trigger:hover),
.rvh__cats :deep(.header-categories__trigger[aria-expanded="true"]) {
  background: var(--rvh-tint);
  color: var(--rvh-ink);
}

/* ---- Search takes the free room between the two clusters ---- */
.rvh__search {
  --hs-h: calc(var(--rvh-control) + .2rem);
  flex: 1 1 auto;
  min-width: 11rem;
  max-width: 40rem;
  margin-inline: auto;
}

/* ---- Account cluster ---- */
.rvh__end {
  display: flex;
  flex: none;
  align-items: center;
  gap: .35rem;
}

.rvh__theme { margin-inline: .15rem .3rem; }

.rvh__icon,
.rvh__end :deep(.site-header__icon-btn) {
  position: relative;
  display: grid;
  width: var(--rvh-control);
  height: var(--rvh-control);
  flex: none;
  place-items: center;
  border: 0;
  border-radius: 999px;
  background: transparent;
  color: var(--rvh-ink-soft);
  transition: background-color 160ms ease, color 160ms ease;
}

.rvh__end :deep(.site-header__icon-btn svg) {
  width: 1.15rem;
  height: 1.15rem;
}

.rvh__icon:hover,
.rvh__end :deep(.site-header__icon-btn:hover) {
  background: var(--rvh-tint);
  color: var(--rvh-ink);
}

.rvh__icon--active,
.rvh__end :deep(.site-header__icon-btn--active) {
  background: color-mix(in srgb, var(--rvh-accent) 16%, transparent);
  color: var(--rvh-accent);
}

.rvh__icon:focus-visible,
.rvh__end :deep(.site-header__icon-btn:focus-visible),
.rvh__me:focus-visible,
.rvh__login:focus-visible {
  outline: 2px solid var(--rvh-accent);
  outline-offset: 2px;
}

.rvh__badge {
  position: absolute;
  inset-block-start: .1rem;
  inset-inline-start: .1rem;
  display: grid;
  min-width: 1.05rem;
  min-height: 1.05rem;
  place-items: center;
  padding-inline: .22rem;
  border-radius: 999px;
  background: var(--rvh-accent);
  color: var(--rvh-on-accent);
  font-size: .68rem;
  font-weight: 800;
  line-height: 1;
  box-shadow: 0 0 0 2px var(--rvh-bg);
}

.rvh__divider {
  width: 1px;
  height: 1.6rem;
  margin-inline: .45rem;
  background: var(--rvh-line);
}

/* Signed in: avatar (photo or initial) + username. */
.rvh__me {
  display: inline-flex;
  height: var(--rvh-control);
  align-items: center;
  gap: .55rem;
  padding-inline: .25rem .8rem;
  border: 1px solid var(--rvh-line);
  border-radius: 999px;
  color: var(--rvh-ink);
  font-size: .85rem;
  font-weight: 700;
  transition: background-color 160ms ease, border-color 160ms ease;
}

.rvh__me:hover { background: var(--rvh-tint); }

.rvh__me--active { border-color: color-mix(in srgb, var(--rvh-accent) 70%, transparent); }

.rvh__avatar {
  display: grid;
  width: calc(var(--rvh-control) - .5rem);
  height: calc(var(--rvh-control) - .5rem);
  flex: none;
  place-items: center;
  overflow: hidden;
  border-radius: 999px;
  background: color-mix(in srgb, var(--rvh-accent) 20%, transparent);
  color: var(--rvh-accent);
  font-size: .9rem;
  font-weight: 800;
}

.rvh__avatar img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.rvh__me-name {
  max-width: 8rem;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* Signed out: the one solid accent control in the bar. */
.rvh__login {
  display: inline-flex;
  height: var(--rvh-control);
  align-items: center;
  gap: .45rem;
  padding-inline: 1rem 1.1rem;
  border-radius: 999px;
  background: var(--rvh-accent);
  color: var(--rvh-on-accent);
  font-size: .85rem;
  font-weight: 700;
  white-space: nowrap;
  transition: background-color 160ms ease;
}

.rvh__login:hover { background: var(--theme-accent-primary-hover, #c8efdc); }

/* The bell's panel opens just under the bar. */
.rvh__end :deep(#notification-panel) {
  top: calc(100% + .75rem);
}

/* Reading progress along the bar's floor. */
.rvh__progress {
  position: absolute;
  inset-inline: 0;
  bottom: -1px;
  height: 2px;
  transform-origin: right center; /* RTL: fill from the leading edge */
  transform: scaleX(var(--rvh-progress, 0));
  background: var(--rvh-accent);
  opacity: 0;
  pointer-events: none;
  transition: opacity 160ms ease;
}

.rvh--scrolled .rvh__progress { opacity: .7; }

/* Skip link. */
.rvh__skip {
  position: absolute;
  inset-inline-start: 1rem;
  top: .6rem;
  z-index: 10;
  transform: translateY(-6rem);
  border-radius: 999px;
  background: var(--rvh-accent);
  padding: .45rem 1rem;
  color: var(--rvh-on-accent);
  font-size: .8rem;
  font-weight: 700;
}

.rvh__skip:focus { transform: none; }

/* Narrow desktops (1024–1439px): secondary links move into the
   categories menu, the app shortcut and username hide. */
@media (max-width: 1439px) {
  .rvh { --rvh-control: 2.35rem; }

  .rvh__link--wide,
  .rvh__icon--app,
  .rvh__me-name { display: none; }

  .rvh__me { padding-inline: .25rem; }

  .rvh__link,
  .rvh__cats :deep(.header-categories__trigger) {
    padding-inline: .55rem;
    font-size: .88rem;
  }

  .rvh__link::after { inset-inline: .55rem; }

  .rvh__search { min-width: 9rem; }
}

/* Mid desktops: keep every link, but the username only from 1600px. */
@media (min-width: 1440px) and (max-width: 1599px) {
  .rvh__me-name { display: none; }

  .rvh__me { padding-inline: .25rem; }
}

@media (min-width: 1920px) {
  .rvh__search { max-width: 48rem; }
}

@media (prefers-reduced-motion: reduce) {
  .rvh,
  .rvh__link,
  .rvh__link::after,
  .rvh__progress {
    transition: none;
  }
}
</style>
