<script setup lang="ts">
import type { CinematicIconName } from '~/types'

const route = useRoute()
const { watchlistIds } = useLibrary()
const authStore = useAuthStore()
const { y } = useWindowScroll()
const profilePath = computed(() => authStore.isAuthenticated ? '/profile' : `/auth/login?redirect=${encodeURIComponent(route.fullPath)}`)

interface HeaderNavItem {
  label: string
  to: string
  icon: CinematicIconName
  match: (path: string) => boolean
  desktopOnly?: boolean
}

const navItems: HeaderNavItem[] = [
  { label: 'خانه', to: '/', icon: 'home', match: path => path === '/' },
  { label: 'فیلم‌ها', to: '/movies', icon: 'movie', match: path => path.startsWith('/movies') },
  { label: 'سریال‌ها', to: '/series', icon: 'series', match: path => path.startsWith('/series') },
  { label: 'تماشای گروهی', to: '/watch-party', icon: 'users', match: path => path.startsWith('/watch-party'), desktopOnly: true },
]

const isHomeAtTop = computed(() => route.path === '/' && y.value < 24)
</script>

<template>
  <header
    class="cinematic-glass sticky top-0 z-50 text-ink backdrop-blur-xl transition-[background-color,box-shadow] duration-300"
    :class="[
      route.path === '/' && 'cinematic-header--overlay',
      isHomeAtTop && 'cinematic-header--at-top',
    ]"
  >
    <a href="#main-content" class="absolute right-4 top-2 z-10 -translate-y-20 rounded-xl bg-primary-500 px-4 py-2 text-sm font-black text-night-950 transition-transform focus:translate-y-0">پرش به محتوای اصلی</a>

    <nav class="mx-auto flex h-[68px] max-w-[1600px] items-center gap-1.5 px-3 sm:gap-2.5 sm:px-6 lg:px-8" aria-label="منوی اصلی">
      <AppLogo />

      <div class="hidden h-full items-center gap-0.5 lg:flex">
        <NuxtLink
          v-for="item in navItems"
          :key="item.to"
          :to="item.to"
          class="group relative inline-flex h-10 items-center gap-1.5 rounded-xl px-2.5 text-sm font-bold transition-colors 2xl:px-3"
          :class="[
            item.match(route.path) ? 'bg-primary-500/13 text-primary-300' : 'text-slate-400 hover:bg-white/[.055] hover:text-white',
            item.desktopOnly && 'hidden xl:inline-flex',
          ]"
          :aria-current="item.match(route.path) ? 'page' : undefined"
        >
          <CinematicIcon :name="item.icon" class="size-4.5" :stroke-width="item.match(route.path) ? 2.2 : 1.8" />
          <span>{{ item.label }}</span>
          <span v-if="item.match(route.path)" class="absolute inset-x-4 -bottom-3.5 h-0.5 rounded-full bg-primary-500" aria-hidden="true" />
        </NuxtLink>
      </div>

      <HeaderCategories />

      <HeaderSearch class="mr-auto hidden min-w-[15rem] max-w-[30rem] flex-1 md:flex lg:max-w-[21rem] xl:max-w-[25rem] 2xl:max-w-[30rem]" :active="route.path === '/search'" />

      <div class="desktop-header__actions mr-auto flex shrink-0 items-center gap-1.5 md:mr-0" aria-label="ابزارهای حساب">
        <NotificationCenter />
        <NuxtLink
          to="/watchlist"
          class="desktop-header__action relative hidden lg:grid"
          :class="route.path === '/watchlist' ? 'desktop-header__action--active' : ''"
          aria-label="لیست من"
          title="لیست من"
          :aria-current="route.path === '/watchlist' ? 'page' : undefined"
        >
          <CinematicIcon name="bookmark" class="size-5" :filled="route.path === '/watchlist'" />
          <span v-if="watchlistIds.length" class="absolute -left-1 -top-1 grid min-h-4 min-w-4 place-items-center rounded-full bg-primary-500 px-1 text-[8px] font-black leading-none text-night-950 ring-2 ring-night-950 tabular-nums">{{ watchlistIds.length }}</span>
        </NuxtLink>
        <NuxtLink
          :to="profilePath"
          class="desktop-header__action grid"
          :class="route.path.startsWith('/profile') ? 'desktop-header__action--active' : ''"
          :aria-label="authStore.isAuthenticated ? 'پروفایل' : 'ورود به حساب'"
          :title="authStore.isAuthenticated ? 'پروفایل' : 'ورود و ثبت‌نام'"
          :aria-current="route.path.startsWith('/profile') ? 'page' : undefined"
        >
          <CinematicIcon :name="authStore.isAuthenticated ? 'user' : 'login'" class="size-5" :stroke-width="route.path.startsWith('/profile') ? 2.2 : 1.8" />
        </NuxtLink>
      </div>
    </nav>
  </header>
</template>

<style scoped>
.desktop-header__actions {
  direction: rtl;
  padding: .2rem;
  border-radius: 1rem;
  background: rgb(255 255 255 / 3%);
  box-shadow: inset 0 1px 0 rgb(255 255 255 / 4%);
}

.desktop-header__action,
.desktop-header__actions :deep(.site-header__icon-btn) {
  width: 2.75rem;
  height: 2.75rem;
  flex: none;
  place-items: center;
  border: 0;
  border-radius: .75rem;
  background: transparent;
  color: rgb(148 163 184);
  transition: color 140ms ease, background-color 140ms ease, transform 140ms ease;
}

.desktop-header__actions :deep(.site-header__icon-btn) {
  display: grid;
}

.desktop-header__action:hover,
.desktop-header__action:focus-visible,
.desktop-header__actions :deep(.site-header__icon-btn:hover),
.desktop-header__actions :deep(.site-header__icon-btn:focus-visible),
.desktop-header__actions :deep(.site-header__icon-btn--active) {
  background: rgb(255 255 255 / 7%);
  color: white;
}

.desktop-header__action:active,
.desktop-header__actions :deep(.site-header__icon-btn:active) {
  transform: scale(.96);
}

.desktop-header__action--active {
  background: rgb(228 173 73 / 14%);
  color: rgb(252 211 77);
}

@media (prefers-reduced-motion: reduce) {
  .desktop-header__action,
  .desktop-header__actions :deep(.site-header__icon-btn) {
    transition: none;
  }
}
</style>
