<script setup lang="ts">
import type { CinematicIconName } from '~/types'

export interface CategoryChipItem {
  label: string
  value: string
  icon?: CinematicIconName
  /** When false, chip is desktop-only to keep mobile filter uncluttered. */
  mobile?: boolean
}

defineProps<{ items: CategoryChipItem[]; modelValue: string }>()
const emit = defineEmits<{ 'update:modelValue': [value: string] }>()
</script>

<template>
  <ScrollStrip
    track-class="category-chips rail-bleed flex snap-x gap-2 pb-1 sm:pb-2"
    role="group"
    label="دسته‌بندی سریع"
  >
    <button
      v-for="item in items"
      :key="item.value"
      type="button"
      class="category-chip shrink-0 snap-start"
      :class="[
        modelValue === item.value && 'category-chip--active',
        item.mobile === false && 'category-chip--desktop-only',
      ]"
      :aria-pressed="modelValue === item.value"
      :aria-label="item.label"
      @click="emit('update:modelValue', item.value)"
    >
      <span class="category-chip__icon" aria-hidden="true">
        <CinematicIcon
          v-if="item.icon"
          :name="item.icon"
          class="size-4 sm:size-4"
          :stroke-width="modelValue === item.value ? 1.9 : 1.5"
        />
      </span>
      <span class="category-chip__label">{{ item.label }}</span>
    </button>
  </ScrollStrip>
</template>
