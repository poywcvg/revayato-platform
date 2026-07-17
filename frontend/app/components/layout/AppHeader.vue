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
    class="cinematic-glass sticky top-0 z-50 border-b border-line text-ink backdrop-blur-xl transition-[background-color,border-color,box-shadow] duration-300"
    :class="[
      route.path === '/' && 'cinematic-header--overlay',
      isHomeAtTop && 'cinematic-header--at-top',
    ]"
  >
    <span class="pointer-events-none absolute inset-x-0 bottom-0 h-px bg-gradient-to-l from-transparent via-primary-500/45 to-transparent" aria-hidden="true" />
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

      <div class="mr-auto flex shrink-0 items-center gap-1 sm:gap-1.5 md:mr-0 md:border-r md:border-white/[.08] md:pr-2.5">
        <NotificationCenter />
        <NuxtLink
          to="/watchlist"
          class="relative hidden h-11 items-center justify-center gap-2 rounded-xl px-2.5 text-slate-400 ring-1 ring-transparent transition-colors hover:bg-white/[.055] hover:text-white lg:inline-flex"
          :class="route.path === '/watchlist' ? 'bg-primary-500/13 text-primary-300 ring-primary-400/20' : ''"
          aria-label="لیست من"
          :aria-current="route.path === '/watchlist' ? 'page' : undefined"
        >
          <CinematicIcon name="bookmark" class="size-5" :filled="route.path === '/watchlist'" />
          <span class="hidden 2xl:inline">لیست من</span>
          <span v-if="watchlistIds.length" class="absolute -left-1 -top-1 grid min-h-4 min-w-4 place-items-center rounded-full bg-primary-500 px-1 text-[8px] font-black leading-none text-night-950 ring-2 ring-night-950 tabular-nums">{{ watchlistIds.length }}</span>
        </NuxtLink>
        <NuxtLink
          :to="profilePath"
          class="inline-flex h-11 items-center justify-center gap-2 rounded-xl px-2.5 text-slate-300 ring-1 transition-colors 2xl:px-3"
          :class="route.path.startsWith('/profile') ? 'bg-primary-500 text-night-950 ring-primary-400' : 'bg-white/[.055] ring-white/[.09] hover:bg-white/[.09] hover:text-white'"
          :aria-label="authStore.isAuthenticated ? 'پروفایل' : 'ورود به حساب'"
          :aria-current="route.path.startsWith('/profile') ? 'page' : undefined"
        >
          <CinematicIcon :name="authStore.isAuthenticated ? 'user' : 'login'" class="size-5" :stroke-width="route.path.startsWith('/profile') ? 2.2 : 1.8" />
          <span class="hidden 2xl:inline">{{ authStore.isAuthenticated ? 'پروفایل' : 'ورود' }}</span>
        </NuxtLink>
      </div>
    </nav>
    <div class="border-t border-white/[.055] px-3 pb-3 pt-2 md:hidden">
      <HeaderSearch mobile class="mx-auto w-full max-w-xl" :active="route.path === '/search'" />
    </div>
  </header>
</template>
