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
    class="catalog-pagination mt-6 flex flex-wrap items-center justify-between gap-3 px-1 py-2"
    :aria-label="label"
  >
    <p class="text-[11px] font-bold text-muted">
      صفحه {{ page.toLocaleString('fa-IR') }} از {{ totalPages.toLocaleString('fa-IR') }}
      <span v-if="total" class="text-secondary"> · {{ total.toLocaleString('fa-IR') }} مورد</span>
    </p>
    <div class="flex flex-wrap items-center gap-1 sm:gap-1.5">
      <button
        type="button"
        class="catalog-pagination__arrow"
        :disabled="pending || page <= 1"
        aria-label="صفحه قبل"
        @click="go(page - 1)"
      >
        <CinematicIcon name="chevron-right" class="size-5" />
      </button>
      <template v-for="segment in segments" :key="segment.type === 'gap' ? segment.key : `page-${segment.page}`">
        <span v-if="segment.type === 'gap'" class="px-0.5 text-xs font-black text-muted" aria-hidden="true">…</span>
        <button
          v-else
          type="button"
          class="catalog-pagination__page"
          :class="{ 'is-active': segment.page === page }"
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
        class="catalog-pagination__arrow"
        :disabled="pending || page >= totalPages"
        aria-label="صفحه بعد"
        @click="go(page + 1)"
      >
        <CinematicIcon name="chevron-left" class="size-5" />
      </button>
    </div>
  </nav>
</template>

<style scoped>
/* Numbered pagination: round prev/next arrows, square page numbers,
   active page becomes a ringed pill (harmonized with theme tokens). */
.catalog-pagination__arrow {
  display: inline-grid;
  width: 2.5rem;
  height: 2.5rem;
  place-items: center;
  border-radius: 9999px;
  background: color-mix(in srgb, var(--theme-bg-elevated) 72%, transparent);
  color: var(--theme-text-secondary);
  transition: background-color 160ms ease, color 160ms ease;
}

@media (hover: hover) and (pointer: fine) {
  .catalog-pagination__arrow:hover:not(:disabled) {
    background: color-mix(in srgb, var(--theme-accent-primary) 14%, transparent);
    color: var(--theme-accent-primary);
  }
}

.catalog-pagination__page {
  display: inline-grid;
  width: 2.25rem;
  height: 2.25rem;
  place-items: center;
  border: 1px solid transparent;
  border-radius: .55rem;
  color: var(--theme-text-secondary);
  font-size: .8rem;
  font-weight: 600;
  font-feature-settings: 'ss01';
  transition: background-color 160ms ease, color 160ms ease, border-color 160ms ease, border-radius 160ms ease;
}

@media (hover: hover) and (pointer: fine) {
  .catalog-pagination__page:hover:not(:disabled):not(.is-active) {
    background: color-mix(in srgb, var(--theme-bg-elevated) 72%, transparent);
    color: var(--theme-text-primary);
  }
}

.catalog-pagination__page.is-active {
  border-color: color-mix(in srgb, var(--theme-accent-primary) 45%, transparent);
  border-radius: 9999px;
  background: color-mix(in srgb, var(--theme-accent-primary) 12%, transparent);
  color: var(--theme-accent-primary);
}

.catalog-pagination__arrow:disabled,
.catalog-pagination__page:disabled {
  opacity: .4;
  cursor: not-allowed;
}

@media (max-width: 400px) {
  .catalog-pagination__arrow {
    width: 2.25rem;
    height: 2.25rem;
  }

  .catalog-pagination__page {
    width: 2rem;
    height: 2rem;
  }
}
</style>
