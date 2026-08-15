<script setup lang="ts">
import Refresh from '~icons/lucide/rotate-cw'
import Search from '~icons/lucide/search'

withDefaults(defineProps<{
  /** Placeholder for the search input. */
  searchPlaceholder?: string
  /** Two-way bound query string (debounced at the caller via useDebouncedFilters). */
  q?: string
  /** Disable the refresh button while a request is in flight. */
  refreshing?: boolean
  /** Show a refresh button alongside the filters. */
  showRefresh?: boolean
}>(), {
  searchPlaceholder: 'جستجو…',
  q: '',
  refreshing: false,
  showRefresh: false,
})

const emit = defineEmits<{
  'update:q': [value: string]
  refresh: []
}>()
</script>

<template>
  <div class="grid gap-3">
    <label class="relative block">
      <span class="mb-1.5 block text-[11px] font-extrabold text-[var(--admin-muted)]">جستجو</span>
      <span class="relative block">
        <Search class="pointer-events-none absolute right-3.5 top-1/2 size-4.5 -translate-y-1/2 text-[var(--admin-accent)]" aria-hidden="true" />
        <input
          :value="q"
          type="search"
          class="admin-focus h-11 w-full rounded-xl border border-[var(--admin-border)] bg-white pr-10 pl-3 text-sm outline-none placeholder:text-[var(--admin-muted)]/70 focus:border-[var(--admin-accent)]"
          :placeholder="searchPlaceholder"
          aria-label="جستجو"
          @input="emit('update:q', ($event.target as HTMLInputElement).value)"
        >
      </span>
    </label>

    <slot />

    <button
      v-if="showRefresh"
      type="button"
      class="admin-focus inline-flex min-h-11 items-center justify-center gap-1.5 rounded-lg px-2.5 text-xs font-bold text-[var(--admin-muted)] hover:bg-[var(--admin-surface-muted)]"
      :disabled="refreshing"
      @click="emit('refresh')"
    >
      <Refresh class="size-3.5" :class="refreshing && 'animate-spin'" aria-hidden="true" />
      به‌روزرسانی
    </button>
  </div>
</template>