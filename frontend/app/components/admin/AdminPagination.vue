<script setup lang="ts">
import ChevronLeft from '~icons/lucide/chevron-left'
import ChevronRight from '~icons/lucide/chevron-right'
import { clampPage, totalPagesFor } from '~/composables/usePagination'

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
    <div class="flex items-center gap-2 sm:ms-auto">
      <button
        class="admin-focus grid size-11 place-items-center rounded-xl border border-[var(--admin-border)] bg-white disabled:opacity-35"
        type="button"
        :disabled="page <= 1 || loading"
        :aria-label="'صفحه قبل'"
        @click="go(page - 1)"
      >
        <ChevronRight class="size-4" aria-hidden="true" />
      </button>
      <span class="min-w-20 text-center font-bold text-[var(--admin-text)]">
        صفحه {{ page.toLocaleString('fa-IR') }} از {{ totalPages.toLocaleString('fa-IR') }}
      </span>
      <button
        class="admin-focus grid size-11 place-items-center rounded-xl border border-[var(--admin-border)] bg-white disabled:opacity-35"
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