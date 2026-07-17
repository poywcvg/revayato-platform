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
  <header class="page-hero relative mb-7 overflow-hidden rounded-3xl p-6 text-white ring-1 ring-white/10 sm:p-8">
    <div class="relative flex flex-wrap items-end justify-between gap-5">
      <div class="flex min-w-0 items-start gap-4">
        <span class="hidden h-12 w-12 shrink-0 place-items-center rounded-2xl bg-energy-500/14 text-energy-300 ring-1 ring-energy-400/22 sm:grid">
          <CinematicIcon :name="icon" class="size-6" />
        </span>
        <div class="min-w-0">
          <p class="text-xs font-black text-energy-300">{{ eyebrow }}</p>
          <h1 class="mt-1 text-3xl font-black tracking-tight sm:text-5xl">{{ title }}</h1>
          <p class="mt-3 max-w-2xl text-sm leading-7 text-slate-400 sm:text-[15px]">{{ description }}</p>
        </div>
      </div>
      <span v-if="count !== undefined" class="inline-flex shrink-0 items-center gap-2 rounded-xl bg-white/[.055] px-3.5 py-2 text-sm font-black text-slate-300 ring-1 ring-white/10" aria-live="polite">
        <span class="h-2 w-2 rounded-full bg-crimson" />
        <span class="tabular-nums">{{ count }}</span> {{ countLabel }}
      </span>
    </div>
    <div v-if="$slots.default" class="relative mt-5">
      <slot />
    </div>
  </header>
</template>
