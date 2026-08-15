<script setup lang="ts">
import Download from '~icons/lucide/download'

const props = withDefaults(defineProps<{
  title?: string
  subtitle?: string
  columns: Array<{ key: string, label: string, align?: 'start' | 'end' | 'center' }>
  rows: Array<Record<string, unknown>>
  loading?: boolean
  exportName?: string
}>(), {
  title: '',
  subtitle: '',
  loading: false,
  exportName: 'analytics-export',
})

function cellText(value: unknown) {
  if (value == null || value === '') return '—'
  if (typeof value === 'number') return value.toLocaleString('fa-IR')
  return String(value)
}

function exportCsv() {
  if (!import.meta.client || !props.rows.length) return
  const header = props.columns.map(column => column.label).join(',')
  const lines = props.rows.map((row) => {
    return props.columns.map((column) => {
      const raw = cellText(row[column.key]).replaceAll('"', '""')
      return `"${raw}"`
    }).join(',')
  })
  const blob = new Blob([['\uFEFF' + header, ...lines].join('\n')], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = `${props.exportName}.csv`
  anchor.click()
  URL.revokeObjectURL(url)
}
</script>

<template>
  <AdminCard class="overflow-hidden">
    <div class="flex flex-col gap-3 border-b border-[var(--admin-border)] px-4 py-3 sm:flex-row sm:items-center sm:justify-between sm:px-5">
      <div>
        <h3 v-if="title" class="text-sm font-black text-[var(--admin-text)]">{{ title }}</h3>
        <p v-if="subtitle" class="mt-0.5 text-[11px] text-[var(--admin-muted)]">{{ subtitle }}</p>
      </div>
      <AdminButton
        size="sm"
        variant="secondary"
        :disabled="loading || !rows.length"
        @click="exportCsv"
      >
        <template #icon><Download class="size-3.5" /></template>
        CSV
      </AdminButton>
    </div>

    <div v-if="loading" class="space-y-2 p-4">
      <div v-for="n in 5" :key="n" class="h-10 animate-pulse rounded-xl bg-[var(--admin-surface-muted)]" />
    </div>

    <div v-else class="overflow-x-auto">
      <table class="min-w-full text-sm">
        <thead>
          <tr class="border-b border-[var(--admin-border)] text-[11px] text-[var(--admin-muted)]">
            <th
              v-for="column in columns"
              :key="column.key"
              class="px-4 py-3 font-black sm:px-5"
              :class="{
                'text-start': (column.align || 'start') === 'start',
                'text-end': column.align === 'end',
                'text-center': column.align === 'center',
              }"
            >
              {{ column.label }}
            </th>
          </tr>
        </thead>
        <tbody>
          <tr v-if="!rows.length">
            <td :colspan="columns.length" class="px-4 py-10 text-center text-[var(--admin-muted)] sm:px-5">
              داده‌ای برای نمایش نیست
            </td>
          </tr>
          <tr
            v-for="(row, index) in rows"
            :key="index"
            class="border-b border-[var(--admin-border)]/60 text-[var(--admin-text)] transition hover:bg-[var(--admin-surface-muted)]/60"
          >
            <td
              v-for="column in columns"
              :key="column.key"
              class="px-4 py-3 font-semibold tabular-nums sm:px-5"
              :class="{
                'text-start': (column.align || 'start') === 'start',
                'text-end': column.align === 'end',
                'text-center': column.align === 'center',
              }"
            >
              <slot :name="`cell-${column.key}`" :row="row" :value="row[column.key]">
                {{ cellText(row[column.key]) }}
              </slot>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </AdminCard>
</template>
