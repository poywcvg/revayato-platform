<script setup lang="ts">
import type { Component } from 'vue'
import ChevronDown from '~icons/lucide/chevron-down'

const props = defineProps<{
  items: Array<{ label: string; href: string; icon: Component; hint?: string }>
  label?: string
  groupId: string
  sectionId: string
  icon: Component
}>()

const openGroup = defineModel<string | null>('openGroup', { default: null })
const route = useRoute()

function itemActive(href: string) {
  const [path, queryString = ''] = href.split('?')
  if (path === '/admin/movies/new') {
    return route.path === '/admin/movies/new'
  }
  if (path === '/admin/movies' && queryString.includes('tmdb=1')) {
    return route.path === '/admin/movies' && String(route.query.tmdb) === '1'
  }
  if (path === '/admin/movies') {
    return (
      (route.path === '/admin/movies' && String(route.query.tmdb) !== '1')
      || /^\/admin\/movies\/\d+/.test(route.path)
    )
  }
  if (path === '/admin/users') {
    return route.path.startsWith('/admin/users')
  }
  if (path === '/admin/inbox') {
    return route.path.startsWith('/admin/inbox')
  }
  if (path === '/admin/reviews') {
    return route.path.startsWith('/admin/reviews')
  }
  if (path === '/admin/catalog-sync') {
    return route.path.startsWith('/admin/catalog-sync')
  }
  return route.path === path || route.path.startsWith(`${path}/`)
}

const isOpen = computed(() => openGroup.value === props.groupId)
const hasActiveItem = computed(() => props.items.some(item => itemActive(item.href)))

function toggle() {
  openGroup.value = isOpen.value ? null : props.groupId
}
</script>

<template>
  <nav :aria-label="label || 'ناوبری مدیریت'">
    <button
      type="button"
      class="admin-focus flex min-h-12 w-full items-center gap-3 rounded-2xl px-3 py-2 text-start text-sm font-black text-white/70 hover:bg-white/8 hover:text-white"
      :class="[
        isOpen && 'bg-white/8 text-white',
        hasActiveItem && 'text-[var(--admin-warm)]',
      ]"
      :aria-expanded="isOpen"
      :aria-controls="sectionId"
      @click="toggle"
    >
      <span
        class="grid size-9 shrink-0 place-items-center rounded-xl bg-white/6 text-white/70"
        :class="(isOpen || hasActiveItem) && 'bg-[var(--admin-warm)]/14 text-[var(--admin-warm)]'"
      >
        <component :is="icon" class="size-4.5" />
      </span>
      <span class="min-w-0 flex-1 truncate">{{ label }}</span>
      <span class="rounded-full bg-white/6 px-2 py-0.5 text-[10px] tabular-nums text-white/45">{{ items.length }}</span>
      <ChevronDown
        class="size-4 shrink-0 text-white/40 transition-transform duration-200"
        :class="isOpen && 'rotate-180'"
      />
    </button>

    <Transition name="admin-nav-section">
      <div v-if="isOpen" :id="sectionId" class="admin-nav-section">
        <ul class="admin-nav-section__inner space-y-1">
          <li v-for="item in items" :key="`${item.href}-${item.label}`">
            <NuxtLink
              :to="item.href"
              class="admin-focus group relative flex items-start gap-3 rounded-2xl px-3 py-2.5 text-sm font-bold text-white/65 hover:bg-white/8 hover:text-white"
              :class="itemActive(item.href) ? 'bg-white/11 text-white shadow-inner' : ''"
              :aria-current="itemActive(item.href) ? 'page' : undefined"
            >
              <span
                v-if="itemActive(item.href)"
                class="absolute inset-y-2 right-0 w-1 rounded-full bg-[var(--admin-warm)]"
                aria-hidden="true"
              />
              <span
                class="mt-0.5 grid size-9 shrink-0 place-items-center rounded-xl"
                :class="itemActive(item.href) ? 'bg-[var(--admin-warm)]/18 text-[var(--admin-warm)]' : 'bg-white/6 text-white/70 group-hover:bg-white/10'"
              >
                <component :is="item.icon" class="size-4.5" />
              </span>
              <span class="min-w-0 flex-1 py-0.5">
                <span class="block truncate">{{ item.label }}</span>
                <span v-if="item.hint" class="mt-0.5 block truncate text-[11px] font-medium text-white/40">{{ item.hint }}</span>
              </span>
            </NuxtLink>
          </li>
        </ul>
      </div>
    </Transition>
  </nav>
</template>

<style scoped>
.admin-nav-section {
  display: grid;
  grid-template-rows: 1fr;
  opacity: 1;
}

.admin-nav-section__inner {
  min-height: 0;
  overflow: hidden;
  padding-top: .35rem;
}

.admin-nav-section-enter-active,
.admin-nav-section-leave-active {
  overflow: hidden;
  transition: grid-template-rows .2s ease, opacity .16s ease;
}

.admin-nav-section-enter-from,
.admin-nav-section-leave-to {
  grid-template-rows: 0fr;
  opacity: 0;
}

@media (prefers-reduced-motion: reduce) {
  .admin-nav-section-enter-active,
  .admin-nav-section-leave-active {
    transition: none;
  }
}
</style>
