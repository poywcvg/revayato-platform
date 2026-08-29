<script setup lang="ts">
import ChevronLeft from '~icons/lucide/chevron-left'
import ChevronRight from '~icons/lucide/chevron-right'
import { clampPage, paginationWindow, totalPagesFor } from '~/composables/usePagination'

const props = withDefaults(defineProps<{
  page: number
  total: number
  pageSize: number
  loading?: boolean
  /** Optional Persian label appended to the count range (e.g. "فیلم"). */
  countLabel?: string
}>(), { loading: false, countLabel: '' })

const emit = defineEmits<{ 'update:page': [value: number] }>()

const totalPages = computed(() => totalPagesFor(props.total, props.pageSize))
const pageStart = computed(() => props.total ? ((props.page - 1) * props.pageSize) + 1 : 0)
const pageEnd = computed(() => Math.min(props.page * props.pageSize, props.total))

const segments = computed(() => {
  const items: Array<{ type: 'page'; page: number } | { type: 'gap'; key: string }> = []
  let previous = 0
  for (const page of paginationWindow(props.page, totalPages.value)) {
    if (previous && page - previous > 1) {
      items.push({ type: 'gap', key: `gap-${previous}-${page}` })
    }
    items.push({ type: 'page', page })
    previous = page
  }
  return items
})

function go(next: number) {
  const target = clampPage(next, totalPages.value)
  if (target !== props.page) emit('update:page', target)
}
</script>

<template>
  <footer v-if="total" class="flex flex-col gap-3 border-t border-[var(--admin-border)] px-5 py-4 text-xs text-[var(--admin-muted)] sm:flex-row sm:items-center">
    <p>
      نمایش {{ pageStart.toLocaleString('fa-IR') }} تا {{ pageEnd.toLocaleString('fa-IR') }} از {{ total.toLocaleString('fa-IR') }}{{ countLabel }}
    </p>
    <div class="flex flex-wrap items-center gap-1 sm:ms-auto">
      <button
        class="admin-focus grid size-9 place-items-center rounded-full bg-[var(--admin-surface)] text-[var(--admin-muted)] transition-colors hover:text-[var(--admin-text)] disabled:opacity-35"
        type="button"
        :disabled="page <= 1 || loading"
        :aria-label="'صفحه قبل'"
        @click="go(page - 1)"
      >
        <ChevronRight class="size-4" aria-hidden="true" />
      </button>
      <template v-for="segment in segments" :key="segment.type === 'gap' ? segment.key : `page-${segment.page}`">
        <span v-if="segment.type === 'gap'" class="px-0.5 font-black" aria-hidden="true">…</span>
        <button
          v-else
          type="button"
          class="admin-focus grid size-9 place-items-center rounded-[.55rem] border border-transparent text-[var(--admin-muted)] transition-colors disabled:opacity-35"
          :class="segment.page === page && 'is-active'"
          :disabled="loading"
          :aria-label="`صفحه ${segment.page}`"
          :aria-current="segment.page === page ? 'page' : undefined"
          @click="go(segment.page)"
        >
          {{ segment.page.toLocaleString('fa-IR') }}
        </button>
      </template>
      <button
        class="admin-focus grid size-9 place-items-center rounded-full bg-[var(--admin-surface)] text-[var(--admin-muted)] transition-colors hover:text-[var(--admin-text)] disabled:opacity-35"
        type="button"
        :disabled="page >= totalPages || loading"
        :aria-label="'صفحه بعد'"
        @click="go(page + 1)"
      >
        <ChevronLeft class="size-4" aria-hidden="true" />
      </button>
    </div>
  </footer>
</template>

<style scoped>
/* Active page pill mirrors the site-wide numbered pagination. */
.admin-focus.is-active {
  border-color: color-mix(in srgb, var(--theme-accent-primary) 45%, transparent);
  border-radius: 9999px;
  background: color-mix(in srgb, var(--theme-accent-primary) 12%, transparent);
  color: var(--theme-accent-primary);
}

@media (hover: hover) and (pointer: fine) {
  .admin-focus:hover:not(:disabled):not(.is-active) {
    color: var(--admin-text);
    background: color-mix(in srgb, var(--admin-border) 40%, transparent);
  }
}
</style>
