<script setup lang="ts">
import type { AnalyticsPeriodKey } from '~/types/analytics'

const props = defineProps<{
  modelValue: AnalyticsPeriodKey
}>()

const emit = defineEmits<{
  'update:modelValue': [value: AnalyticsPeriodKey]
}>()

const options: Array<{ value: AnalyticsPeriodKey, label: string }> = [
  { value: '7d', label: '۷ روز' },
  { value: '30d', label: '۳۰ روز' },
  { value: '90d', label: '۹۰ روز' },
]
</script>

<template>
  <div class="inline-flex max-w-full gap-1 overflow-x-auto rounded-2xl border border-[var(--admin-border)] bg-white p-1 shadow-[var(--admin-shadow)]">
    <button
      v-for="option in options"
      :key="option.value"
      type="button"
      class="admin-focus min-h-11 shrink-0 rounded-xl px-4 text-xs font-black transition"
      :class="props.modelValue === option.value
        ? 'bg-[var(--admin-primary)] text-white'
        : 'text-[var(--admin-muted)] hover:bg-[var(--admin-surface-muted)]'"
      :aria-pressed="props.modelValue === option.value"
      @click="emit('update:modelValue', option.value)"
    >
      {{ option.label }}
    </button>
  </div>
</template>
