<script setup lang="ts">
import Film from '~icons/lucide/film'
import LayoutDashboard from '~icons/lucide/layout-dashboard'
import Users from '~icons/lucide/users-round'

const route = useRoute()

const items = [
  { to: '/dashboard', label: 'نمای کلی', icon: LayoutDashboard, match: (path: string) => path === '/dashboard' },
  { to: '/dashboard/users', label: 'کاربران', icon: Users, match: (path: string) => path.startsWith('/dashboard/users') },
  { to: '/dashboard/content', label: 'محتوا و تعامل', icon: Film, match: (path: string) => path.startsWith('/dashboard/content') },
]
</script>

<template>
  <div class="mb-5 flex max-w-full gap-1 overflow-x-auto rounded-2xl border border-[var(--admin-border)] bg-white p-1 shadow-[var(--admin-shadow)]">
    <NuxtLink
      v-for="item in items"
      :key="item.to"
      :to="item.to"
      class="admin-focus inline-flex min-h-11 shrink-0 items-center gap-1.5 rounded-xl px-4 text-xs font-black transition"
      :class="item.match(route.path)
        ? 'bg-[var(--admin-primary)] text-white'
        : 'text-[var(--admin-muted)] hover:bg-[var(--admin-surface-muted)]'"
    >
      <component :is="item.icon" class="size-3.5" />
      {{ item.label }}
    </NuxtLink>
  </div>
</template>
