<script setup lang="ts">
import type { Component } from 'vue'

withDefaults(defineProps<{
  title?: string
  subtitle?: string
  icon?: Component
  padded?: boolean
}>(), { padded: true, title: '', subtitle: '', icon: undefined })
</script>

<template>
  <section class="rv-card rv-card--glass rv-rise flex min-w-0 flex-col overflow-hidden">
    <header v-if="title || $slots.actions" class="flex items-center justify-between gap-3 border-b border-[var(--rv-border)] px-4 py-3">
      <div class="flex min-w-0 items-center gap-2.5">
        <span v-if="icon" class="grid size-8 shrink-0 place-items-center rounded-[var(--rv-radius-sm)] bg-[var(--rv-accent-soft)] text-[var(--rv-accent)]">
          <component :is="icon" class="size-4" />
        </span>
        <div class="min-w-0">
          <h2 class="truncate text-sm font-black text-[var(--rv-text)]">{{ title }}</h2>
          <p v-if="subtitle" class="truncate text-xs font-semibold text-[var(--rv-muted)]">{{ subtitle }}</p>
        </div>
      </div>
      <div v-if="$slots.actions" class="flex shrink-0 items-center gap-2">
        <slot name="actions" />
      </div>
    </header>
    <div :class="padded ? 'p-4' : ''" class="min-w-0 flex-1">
      <slot />
    </div>
  </section>
</template>
