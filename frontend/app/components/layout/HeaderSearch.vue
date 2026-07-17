<script setup lang="ts">
const props = withDefaults(defineProps<{ active?: boolean; mobile?: boolean }>(), {
  active: false,
  mobile: false,
})

const route = useRoute()
const input = useTemplateRef<HTMLInputElement>('input')
const query = ref(route.path === '/search' ? String(route.query.q || '') : '')
const { trackSearch } = useAnalyticsEvent()
const advancedTo = computed(() => ({
  path: '/search',
  query: query.value.trim() ? { q: query.value.trim() } : {},
}))

function submit() {
  const term = query.value.trim()
  trackSearch(term, 0)
  void navigateTo({ path: '/search', query: term ? { q: term } : {} })
}

function focusFromShortcut(event: KeyboardEvent) {
  const desktopViewport = window.matchMedia('(min-width: 768px)').matches
  if ((props.mobile && desktopViewport) || (!props.mobile && !desktopViewport)) return
  const target = event.target as HTMLElement | null
  if (target?.matches('input, textarea, select, [contenteditable="true"]')) return
  event.preventDefault()
  input.value?.focus()
}

onKeyStroke('/', focusFromShortcut)
watch(() => route.fullPath, () => {
  query.value = route.path === '/search' ? String(route.query.q || '') : ''
})
</script>

<template>
  <div class="header-search flex min-w-0 items-center gap-2" :class="mobile && 'header-search--mobile'">
    <form class="group flex h-11 min-w-0 flex-1 items-center rounded-xl border bg-white/[.055] shadow-inner shadow-black/10 transition-colors" :class="active ? 'border-primary-400/35 bg-primary-500/10' : 'border-white/[.09] hover:border-white/15 hover:bg-white/[.08] focus-within:border-primary-400/55 focus-within:bg-surface'" role="search" @submit.prevent="submit">
      <label class="sr-only" :for="mobile ? 'mobile-header-search' : 'desktop-header-search'">جستجوی سریع فیلم یا سریال</label>
      <CinematicIcon name="search" class="mr-3 size-4.5 shrink-0 text-primary-400" />
      <input
        :id="mobile ? 'mobile-header-search' : 'desktop-header-search'"
        ref="input"
        v-model="query"
        type="search"
        inputmode="search"
        enterkeyhint="search"
        autocomplete="off"
        class="h-full min-w-0 flex-1 bg-transparent px-2 text-sm text-ink outline-none placeholder:text-muted"
        placeholder="نام فیلم، سریال یا بازیگر…"
      >
      <button v-if="query" type="button" class="grid size-9 shrink-0 place-items-center rounded-lg text-muted hover:bg-white/6 hover:text-ink" aria-label="پاک کردن جستجو" @click="query = ''; input?.focus()"><CinematicIcon name="x" class="size-3.5" /></button>
      <kbd v-else class="ml-1 hidden rounded-md bg-night-950 px-1.5 py-0.5 font-latin text-[10px] text-muted ring-1 ring-white/10 xl:block">/</kbd>
      <button type="submit" class="ml-1 grid size-9 shrink-0 place-items-center rounded-lg bg-primary-500 text-night-950 hover:bg-primary-400" aria-label="جستجو"><CinematicIcon name="arrow-left" class="size-4" /></button>
    </form>
    <NuxtLink :to="advancedTo" class="inline-flex h-11 shrink-0 items-center justify-center gap-1.5 rounded-xl border border-line bg-elevated px-3 text-xs font-black text-secondary hover:border-primary-500/45 hover:bg-primary-500/10 hover:text-primary-300" aria-label="باز کردن جستجوی پیشرفته" :aria-current="active ? 'page' : undefined">
      <CinematicIcon name="sliders" class="size-4" />
      <span :class="mobile ? 'inline' : 'hidden xl:inline'">فیلتر</span>
    </NuxtLink>
  </div>
</template>
