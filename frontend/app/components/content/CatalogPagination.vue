<script setup lang="ts">
import { paginationWindow } from '~/composables/usePagination'

const props = withDefaults(defineProps<{
  page: number
  totalPages: number
  total?: number
  pending?: boolean
  label?: string
}>(), {
  total: 0,
  pending: false,
  label: 'صفحه‌بندی نتایج',
})

const emit = defineEmits<{
  change: [page: number]
}>()

const windowPages = computed(() => paginationWindow(props.page, props.totalPages))

const segments = computed(() => {
  const items: Array<{ type: 'page'; page: number } | { type: 'gap'; key: string }> = []
  let previous = 0
  for (const page of windowPages.value) {
    if (previous && page - previous > 1) {
      items.push({ type: 'gap', key: `gap-${previous}-${page}` })
    }
    items.push({ type: 'page', page })
    previous = page
  }
  return items
})

function go(page: number) {
  if (props.pending) return
  if (page < 1 || page > props.totalPages || page === props.page) return
  emit('change', page)
}
</script>

<template>
  <nav
    v-if="totalPages > 1"
    class="catalog-pagination ui-surface mt-6 flex flex-wrap items-center justify-between gap-3 px-3 py-3 sm:px-4"
    :aria-label="label"
  >
    <p class="text-[11px] font-bold text-muted">
      صفحه {{ page.toLocaleString('fa-IR') }} از {{ totalPages.toLocaleString('fa-IR') }}
      <span v-if="total" class="text-secondary"> · {{ total.toLocaleString('fa-IR') }} مورد</span>
    </p>
    <div class="flex flex-wrap items-center gap-1.5">
      <button
        type="button"
        class="catalog-pagination__btn"
        :disabled="pending || page <= 1"
        aria-label="صفحه قبل"
        @click="go(page - 1)"
      >
        <CinematicIcon name="chevron-right" class="size-4" />
      </button>
      <template v-for="segment in segments" :key="segment.type === 'gap' ? segment.key : `page-${segment.page}`">
        <span v-if="segment.type === 'gap'" class="px-1 text-xs font-black text-muted" aria-hidden="true">…</span>
        <button
          v-else
          type="button"
          class="catalog-pagination__btn catalog-pagination__btn--page"
          :class="segment.page === page && 'is-active'"
          :aria-current="segment.page === page ? 'page' : undefined"
          :disabled="pending"
          :aria-label="`صفحه ${segment.page}`"
          @click="go(segment.page)"
        >
          {{ segment.page.toLocaleString('fa-IR') }}
        </button>
      </template>
      <button
        type="button"
        class="catalog-pagination__btn"
        :disabled="pending || page >= totalPages"
        aria-label="صفحه بعد"
        @click="go(page + 1)"
      >
        <CinematicIcon name="chevron-left" class="size-4" />
      </button>
    </div>
  </nav>
</template>

<style scoped>
.catalog-pagination__btn {
  display: inline-grid;
  min-width: 2.5rem;
  min-height: 2.5rem;
  place-items: center;
  border-radius: 0.85rem;
  background: rgb(var(--surface-elevated-rgb, 20 24 33) / 1);
  color: var(--color-secondary, #9aa3b5);
  box-shadow: inset 0 0 0 1px rgb(var(--line-rgb, 255 255 255) / 12%);
  font-size: 0.75rem;
  font-weight: 800;
  transition: color 160ms ease, background 160ms ease, box-shadow 160ms ease;
}

.catalog-pagination__btn:hover:not(:disabled) {
  color: var(--color-brand, #e8c27a);
  box-shadow: inset 0 0 0 1px rgb(var(--palette-sand-rgb, 232 194 122) / 35%);
}

.catalog-pagination__btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.catalog-pagination__btn--page.is-active {
  background: rgb(var(--palette-sand-rgb, 232 194 122) / 18%);
  color: var(--color-brand, #e8c27a);
  box-shadow: inset 0 0 0 1px rgb(var(--palette-sand-rgb, 232 194 122) / 40%);
}
</style>
