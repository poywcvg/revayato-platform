<script setup lang="ts">
import type { Component } from 'vue'
import ArrowUp from '~icons/lucide/arrow-up-right'
import ArrowDown from '~icons/lucide/arrow-down-right'

type Tone = 'accent' | 'success' | 'warning' | 'danger' | 'info' | 'violet'

const props = withDefaults(defineProps<{
  label: string
  value: number | string | null
  hint?: string
  icon?: Component
  tone?: Tone
  delta?: number | null
  format?: 'number' | 'percent' | 'hours' | 'raw'
  spark?: number[]
  loading?: boolean
}>(), {
  hint: '',
  tone: 'accent',
  delta: null,
  format: 'number',
  loading: false,
  icon: undefined,
  spark: undefined,
})

const TONE: Record<Tone, string> = {
  accent: 'var(--rv-accent)',
  success: 'var(--rv-success)',
  warning: 'var(--rv-warning)',
  danger: 'var(--rv-danger)',
  info: 'var(--rv-info)',
  violet: 'var(--rv-violet)',
}

const display = computed(() => {
  const v = props.value
  if (v == null || v === '') return '—'
  if (typeof v === 'string') return v
  if (props.format === 'percent') return `${v.toLocaleString('fa-IR', { maximumFractionDigits: 1 })}٪`
  if (props.format === 'hours') return `${v.toLocaleString('fa-IR', { maximumFractionDigits: 1 })} ساعت`
  if (props.format === 'raw') return v.toLocaleString('fa-IR', { maximumFractionDigits: 1 })
  return v.toLocaleString('fa-IR')
})

const deltaTone = computed(() => {
  if (props.delta == null) return null
  return props.delta >= 0 ? 'up' : 'down'
})
</script>

<template>
  <div class="rv-card rv-card--glass rv-rise relative overflow-hidden p-4">
    <div class="flex items-start justify-between gap-3">
      <div class="min-w-0">
        <p class="truncate text-xs font-black uppercase tracking-wide text-[var(--rv-faint)]">{{ label }}</p>
        <div v-if="loading" class="rv-skeleton mt-2 h-8 w-24" />
        <p v-else class="mt-1.5 text-[26px] font-black leading-none tabular-nums text-[var(--rv-text)]">{{ display }}</p>
      </div>
      <span
        v-if="icon"
        class="grid size-9 shrink-0 place-items-center rounded-[var(--rv-radius-sm)]"
        :style="{ color: TONE[tone], background: `color-mix(in srgb, ${TONE[tone]} 14%, transparent)` }"
      >
        <component :is="icon" class="size-[18px]" />
      </span>
    </div>

    <div class="mt-3 flex items-center gap-2">
      <span
        v-if="deltaTone"
        class="inline-flex items-center gap-0.5 text-xs font-black tabular-nums"
        :style="{ color: deltaTone === 'up' ? 'var(--rv-success)' : 'var(--rv-danger)' }"
      >
        <component :is="deltaTone === 'up' ? ArrowUp : ArrowDown" class="size-3.5" />
        {{ Math.abs(delta ?? 0).toLocaleString('fa-IR', { maximumFractionDigits: 1 }) }}٪
      </span>
      <span v-if="hint" class="truncate text-xs font-semibold text-[var(--rv-muted)]">{{ hint }}</span>
    </div>

    <div v-if="spark && spark.length > 1" class="pointer-events-none mt-2 -mb-1">
      <RvSpark :values="spark" :color="TONE[tone]" :height="34" />
    </div>
  </div>
</template>
