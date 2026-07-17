<script setup lang="ts">
import type { CinematicIconName } from '~/types'

export interface CategoryChipItem {
  label: string
  value: string
  icon?: CinematicIconName
}

defineProps<{ items: CategoryChipItem[]; modelValue: string }>()
const emit = defineEmits<{ 'update:modelValue': [value: string] }>()
</script>

<template>
  <div class="hide-scrollbar flex snap-x gap-2 overflow-x-auto pb-2" role="group" aria-label="دسته‌بندی سریع">
    <button v-for="item in items" :key="item.value" type="button" class="inline-flex min-h-11 shrink-0 snap-start items-center gap-2 rounded-xl px-4 py-2.5 text-sm font-bold ring-1 ring-inset transition" :class="modelValue === item.value ? 'energy-glow bg-energy-500 text-night-950 ring-energy-300' : 'bg-white/[.045] text-slate-400 ring-white/10 hover:bg-energy-500/8 hover:text-energy-200 hover:ring-energy-300/25'" :aria-pressed="modelValue === item.value" @click="emit('update:modelValue', item.value)"><CinematicIcon v-if="item.icon" :name="item.icon" class="size-4" :stroke-width="modelValue === item.value ? 2.2 : 1.8" />{{ item.label }}</button>
  </div>
</template>
