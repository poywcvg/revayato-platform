<script setup lang="ts">
import type { CinematicIconName } from '~/types'

type MobileTabKey = 'home' | 'movies' | 'series' | 'app' | 'profile'

interface MobileTab {
  key: MobileTabKey
  label: string
  to: string
  icon: CinematicIconName
  match: (path: string) => boolean
}

const props = defineProps<{
  profilePath: string
}>()

const route = useRoute()

const tabs = computed<MobileTab[]>(() => [
  { key: 'home', label: 'خانه', to: '/', icon: 'home', match: path => path === '/' || path === '/welcome' },
  { key: 'movies', label: 'فیلم‌ها', to: '/movies', icon: 'movie', match: path => path.startsWith('/movies') },
  { key: 'series', label: 'سریال‌ها', to: '/series', icon: 'series', match: path => path.startsWith('/series') },
  { key: 'app', label: 'اپلیکیشن', to: '/app', icon: 'smartphone', match: path => path.startsWith('/app') },
  {
    key: 'profile',
    label: 'پروفایل',
    to: props.profilePath,
    icon: 'profile',
    match: path => path.startsWith('/profile') || path.startsWith('/auth'),
  },
])

const activeIndex = computed(() => tabs.value.findIndex(tab => tab.match(route.path)))
</script>

<template>
  <nav
    class="magic-bottom-nav"
    :class="{ 'magic-bottom-nav--inactive': activeIndex < 0 }"
    :style="{ '--active-index': Math.max(activeIndex, 0) }"
    aria-label="ناوبری اصلی موبایل"
    dir="rtl"
  >
    <div class="magic-bottom-nav__surface" aria-hidden="true" />
    <div class="magic-bottom-nav__indicator" aria-hidden="true">
      <span class="magic-bottom-nav__indicator-core" />
    </div>

    <NuxtLink
      v-for="tab in tabs"
      :key="tab.key"
      :to="tab.to"
      class="magic-bottom-nav__item"
      :class="{ 'magic-bottom-nav__item--active': tab.match(route.path) }"
      :aria-current="tab.match(route.path) ? 'page' : undefined"
    >
      <span class="magic-bottom-nav__icon-wrap">
        <CinematicIcon
          :name="tab.icon"
          class="magic-bottom-nav__icon"
          :stroke-width="tab.match(route.path) ? 2.35 : 1.8"
        />
      </span>
      <span class="magic-bottom-nav__label">{{ tab.label }}</span>
    </NuxtLink>
  </nav>
</template>

<style scoped>
.magic-bottom-nav {
  --nav-bg: #11151d;
  --nav-accent: var(--theme-accent-primary);
  --nav-muted: #9298a5;
  --nav-line: rgb(255 255 255 / 8%);
  --nav-count: 5;
  --indicator-size: 3.65rem;
  position: fixed;
  inset-inline: 0;
  bottom: 0;
  z-index: 70;
  display: grid;
  min-height: calc(var(--mobile-bottom-nav-height) + env(safe-area-inset-bottom, 0px));
  grid-template-columns: repeat(var(--nav-count), minmax(0, 1fr));
  align-items: end;
  padding: 1.3rem max(.25rem, env(safe-area-inset-right, 0px)) env(safe-area-inset-bottom, 0px) max(.25rem, env(safe-area-inset-left, 0px));
  isolation: isolate;
}

.magic-bottom-nav__surface {
  position: absolute;
  inset: 1.3rem 0 0;
  z-index: -2;
  border-top: 1px solid var(--nav-line);
  background: color-mix(in srgb, var(--nav-bg) 97%, transparent);
  box-shadow: none;
  /* Surface is 97% opaque, so a large blur is invisible but repaints the whole
     backdrop on every scroll. A small radius keeps the hint of glass cheaply. */
}

html[data-theme="light"] .magic-bottom-nav {
  --nav-bg: #ffffff;
  --nav-muted: var(--theme-text-muted);
  --nav-line: var(--theme-border);
}


/* One moving element creates both the circular cutout and its curved shoulders.
   inset-inline-start keeps the same math correct in RTL and LTR. */
.magic-bottom-nav__indicator {
  position: absolute;
  inset-block-start: .05rem;
  inset-inline-start: calc((100% / var(--nav-count)) * var(--active-index) + (100% / var(--nav-count) - var(--indicator-size)) / 2);
  z-index: -1;
  width: var(--indicator-size);
  height: var(--indicator-size);
  border: .42rem solid var(--theme-bg-main, #080a0f);
  border-radius: 50%;
  background: var(--nav-accent);
  box-shadow: none;
  transition: inset-inline-start 420ms cubic-bezier(.22, 1, .36, 1), opacity 180ms ease, transform 420ms cubic-bezier(.22, 1, .36, 1);
}

.magic-bottom-nav__indicator::before,
.magic-bottom-nav__indicator::after {
  content: '';
  position: absolute;
  top: 1.43rem;
  width: .78rem;
  height: .78rem;
  background: transparent;
}

.magic-bottom-nav__indicator::before {
  right: calc(100% + .36rem);
  border-top-left-radius: .8rem;
  box-shadow: -.18rem -.35rem 0 .18rem var(--nav-bg);
}

.magic-bottom-nav__indicator::after {
  left: calc(100% + .36rem);
  border-top-right-radius: .8rem;
  box-shadow: .18rem -.35rem 0 .18rem var(--nav-bg);
}

.magic-bottom-nav__indicator-core {
  position: absolute;
  inset: .2rem;
  border-radius: inherit;
  border: 1px solid rgb(255 255 255 / 18%);
}

.magic-bottom-nav--inactive .magic-bottom-nav__indicator {
  opacity: 0;
  transform: translateY(.75rem) scale(.75);
}

.magic-bottom-nav__item {
  position: relative;
  z-index: 1;
  display: flex;
  min-width: 0;
  height: var(--mobile-bottom-nav-height);
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: .28rem;
  border-radius: .75rem;
  color: var(--nav-muted);
  font-size: 0.75rem;
  font-weight: 700;
  line-height: 1;
  -webkit-tap-highlight-color: transparent;
}

.magic-bottom-nav__icon-wrap {
  display: grid;
  width: 2rem;
  height: 1.65rem;
  place-items: center;
  transition: color 180ms ease, transform 420ms cubic-bezier(.22, 1, .36, 1);
}

.magic-bottom-nav__icon {
  width: 1.35rem;
  height: 1.35rem;
}

.magic-bottom-nav__label {
  overflow: hidden;
  max-width: 100%;
  white-space: nowrap;
  transition: color 180ms ease, transform 300ms ease, opacity 180ms ease;
}

.magic-bottom-nav__item--active .magic-bottom-nav__icon-wrap {
  color: var(--theme-on-accent);
  transform: translateY(-.96rem);
}

.magic-bottom-nav__item--active .magic-bottom-nav__label {
  color: var(--nav-accent);
  transform: translateY(-.08rem);
}

.magic-bottom-nav__item:focus-visible {
  outline: 2px solid color-mix(in srgb, var(--nav-accent) 75%, transparent);
  outline-offset: -4px;
}

@media (min-width: 1024px) {
  .magic-bottom-nav {
    display: none;
  }
}

@media (prefers-reduced-motion: reduce) {
  .magic-bottom-nav__indicator,
  .magic-bottom-nav__icon-wrap,
  .magic-bottom-nav__label {
    transition-duration: 1ms;
  }
}
</style>
