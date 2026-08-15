<script setup lang="ts">
import ArrowDown from '~icons/lucide/arrow-down'
import ArrowUp from '~icons/lucide/arrow-up'
import Minus from '~icons/lucide/minus'
import type { Component } from 'vue'

const props = withDefaults(defineProps<{
  label: string
  value: number | string | null
  deltaPercent?: number | null
  hint?: string
  icon?: Component
  loading?: boolean
  format?: 'number' | 'hours' | 'currency' | 'percent' | 'raw'
  tone?: 'green' | 'blue' | 'amber' | 'violet' | 'rose' | 'slate' | 'teal'
}>(), {
  deltaPercent: null,
  hint: '',
  loading: false,
  format: 'number',
  tone: 'green',
})

function formatValue(value: number | string | null) {
  if (value == null || value === '') return '—'
  if (typeof value === 'string') return value
  if (props.format === 'raw') return value.toLocaleString('fa-IR', { maximumFractionDigits: 1 })
  if (props.format === 'currency') return '—'
  if (props.format === 'percent') return `${value.toLocaleString('fa-IR', { maximumFractionDigits: 1 })}٪`
  if (props.format === 'hours') return `${value.toLocaleString('fa-IR', { maximumFractionDigits: 1 })} س`
  return value.toLocaleString('fa-IR')
}

const deltaTone = computed(() => {
  if (props.deltaPercent == null) return 'neutral'
  if (props.deltaPercent > 0) return 'up'
  if (props.deltaPercent < 0) return 'down'
  return 'neutral'
})
</script>

<template>
  <article
    class="dashboard-kpi rounded-[20px] border border-[var(--admin-border)] bg-white p-4 shadow-[var(--admin-shadow)]"
    :data-tone="tone"
  >
    <div v-if="loading" class="animate-pulse space-y-3">
      <div class="h-10 w-10 rounded-2xl bg-[var(--admin-surface-muted)]" />
      <div class="h-7 w-24 rounded bg-[var(--admin-surface-muted)]" />
      <div class="h-3 w-20 rounded bg-[var(--admin-surface-muted)]" />
    </div>
    <template v-else>
      <div class="flex items-start justify-between gap-3">
        <span class="dashboard-kpi__icon grid size-10 place-items-center rounded-2xl">
          <component :is="icon" v-if="icon" class="size-4.5" />
        </span>
        <span
          v-if="deltaPercent != null"
          class="inline-flex min-h-7 items-center gap-1 rounded-full px-2 text-[10px] font-black"
          :class="{
            'bg-emerald-50 text-emerald-700': deltaTone === 'up',
            'bg-red-50 text-red-700': deltaTone === 'down',
            'bg-slate-100 text-slate-500': deltaTone === 'neutral',
          }"
        >
          <ArrowUp v-if="deltaTone === 'up'" class="size-3" />
          <ArrowDown v-else-if="deltaTone === 'down'" class="size-3" />
          <Minus v-else class="size-3" />
          {{ Math.abs(deltaPercent).toLocaleString('fa-IR', { maximumFractionDigits: 1 }) }}٪
        </span>
      </div>
      <p class="mt-5 text-2xl font-black tabular-nums text-[var(--admin-text)]">
        {{ formatValue(value) }}
      </p>
      <h2 class="mt-1 text-sm font-black text-[var(--admin-text)]">{{ label }}</h2>
      <p v-if="hint" class="mt-1 text-[11px] leading-5 text-[var(--admin-muted)]">{{ hint }}</p>
    </template>
  </article>
</template>

<style scoped>
.dashboard-kpi__icon {
  background: var(--admin-surface-muted);
  color: var(--admin-primary);
}
.dashboard-kpi[data-tone='blue'] .dashboard-kpi__icon { background: #eff6ff; color: #1d4ed8; }
.dashboard-kpi[data-tone='amber'] .dashboard-kpi__icon { background: #fffbeb; color: #b45309; }
.dashboard-kpi[data-tone='violet'] .dashboard-kpi__icon { background: #f5f3ff; color: #6d28d9; }
.dashboard-kpi[data-tone='rose'] .dashboard-kpi__icon { background: #fff1f2; color: #be123c; }
.dashboard-kpi[data-tone='slate'] .dashboard-kpi__icon { background: #f1f5f9; color: #475569; }
.dashboard-kpi[data-tone='teal'] .dashboard-kpi__icon { background: #f0fdfa; color: #0f766e; }
</style>
