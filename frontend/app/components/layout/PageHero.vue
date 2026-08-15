<script setup lang="ts">
import type { CinematicIconName } from '~/types'

withDefaults(defineProps<{
  title: string
  eyebrow: string
  description: string
  icon?: CinematicIconName
  count?: number
  countLabel?: string
}>(), {
  icon: 'sparkles',
  count: undefined,
  countLabel: 'عنوان',
})
</script>

<template>
  <header class="page-hero relative mb-5 overflow-hidden rounded-2xl p-[clamp(1rem,3vw,1.75rem)] text-ink sm:mb-6 sm:rounded-3xl">
    <div class="relative flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-end sm:justify-between sm:gap-5">
      <div class="flex min-w-0 items-start gap-3 sm:gap-4">
        <span class="grid size-10 shrink-0 place-items-center rounded-xl bg-primary-500/14 text-brand sm:size-11">
          <CinematicIcon :name="icon" class="size-5 sm:size-5.5" />
        </span>
        <div class="min-w-0">
          <p class="text-xs font-black text-muted">{{ eyebrow }}</p>
          <h1 class="mt-1 text-[clamp(1.4rem,3.5vw,2.4rem)] font-black leading-tight tracking-tight">{{ title }}</h1>
          <p class="mt-2 max-w-2xl text-sm leading-7 text-secondary">{{ description }}</p>
        </div>
      </div>
      <span v-if="count !== undefined" class="inline-flex w-fit shrink-0 items-center gap-2 rounded-xl bg-elevated px-3.5 py-2 text-xs font-black text-secondary ring-1 ring-line sm:text-sm" aria-live="polite">
        <span class="h-2 w-2 rounded-full bg-brand" />
        <span class="tabular-nums">{{ count.toLocaleString('fa-IR') }}</span> {{ countLabel }}
      </span>
    </div>
    <div v-if="$slots.default" class="relative mt-4">
      <slot />
    </div>
  </header>
</template>
