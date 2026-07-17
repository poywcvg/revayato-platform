<script setup lang="ts">
import type { CinematicIconName } from '~/types'

const route = useRoute()
const { watchlistIds } = useLibrary()
const authStore = useAuthStore()
interface MobileNavItem {
  label: string
  to: string
  icon: CinematicIconName
  badge?: number
}

const items = computed<MobileNavItem[]>(() => [
  { label: 'خانه', to: '/', icon: 'home' },
  { label: 'جستجو', to: '/search', icon: 'search' },
  { label: 'لیست من', to: '/watchlist', icon: 'bookmark', badge: watchlistIds.value.length || undefined },
  { label: authStore.isAuthenticated ? 'پروفایل' : 'ورود', to: authStore.isAuthenticated ? '/profile' : '/auth/login', icon: authStore.isAuthenticated ? 'user' : 'login' },
])

function active(to: string) {
  if (to === '/') return route.path === '/'
  return route.path === to || route.path.startsWith(`${to}/`)
}
</script>

<template>
  <nav class="mobile-bottom-nav fixed inset-x-3 z-50 mx-auto flex max-w-md items-center justify-around rounded-2xl border border-line bg-canvas-soft/98 p-1.5 shadow-2xl shadow-black/40 lg:hidden" aria-label="ناوبری اصلی موبایل">
    <NuxtLink
      v-for="item in items"
      :key="item.to"
      :to="item.to"
      class="relative flex min-h-12 min-w-12 flex-1 flex-col items-center justify-center gap-0.5 rounded-xl px-1.5 text-[10px] font-bold transition-colors active:scale-[.98] sm:text-[11px]"
      :class="active(item.to) ? 'bg-primary-500/13 text-primary-300' : 'text-slate-500 hover:bg-white/5 hover:text-slate-300'"
      :aria-current="active(item.to) ? 'page' : undefined"
    >
      <span v-if="active(item.to)" class="absolute top-0 h-0.5 w-7 rounded-full bg-primary-500" aria-hidden="true" />
      <span class="relative"><CinematicIcon :name="item.icon" class="size-5" :filled="active(item.to) && item.icon === 'bookmark'" :stroke-width="active(item.to) ? 2.2 : 1.8" /><span v-if="item.badge" class="absolute -left-2 -top-1.5 grid min-h-4 min-w-4 place-items-center rounded-full bg-primary-500 px-1 text-[8px] font-black leading-none text-night-950 ring-2 ring-night-900 tabular-nums">{{ item.badge }}</span></span>
      <span>{{ item.label }}</span>
    </NuxtLink>
  </nav>
</template>
