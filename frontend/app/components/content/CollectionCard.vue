<script setup lang="ts">
import type { Movie } from '~/types'

defineProps<{ title: string; description: string; items: Movie[]; href: string; accent?: string }>()
</script>

<template>
  <NuxtLink :to="href" class="performance-card group relative block min-h-64 overflow-hidden rounded-3xl bg-night-800 ring-1 ring-white/10 transition-[transform,box-shadow] duration-200 hover:-translate-y-0.5 hover:ring-energy-400/35">
    <div class="absolute inset-0 grid grid-cols-3 gap-1 opacity-65 transition-opacity duration-200 group-hover:opacity-75"><NuxtImg v-for="item in items.slice(0, 3)" :key="item.id" :src="item.poster_url" alt="" class="h-full w-full object-cover" loading="lazy" decoding="async" fetchpriority="low" /></div>
    <div class="absolute inset-0 bg-gradient-to-t from-canvas via-canvas/70 to-transparent" />
    <div class="absolute inset-x-0 bottom-0 p-5"><span class="inline-flex rounded-full bg-primary-500/15 px-2.5 py-1 text-[10px] font-black text-primary-300 ring-1 ring-primary-400/25">{{ accent || 'کالکشن دست‌چین' }}</span><h3 class="mt-3 text-lg font-black text-white">{{ title }}</h3><p class="mt-1 line-clamp-2 text-xs leading-6 text-slate-400">{{ description }}</p><span class="mt-4 inline-flex items-center gap-1 text-xs font-black text-primary-300">دیدن کالکشن<CinematicIcon name="arrow-left" class="size-4 transition-transform group-hover:-translate-x-1" /></span></div>
  </NuxtLink>
</template>
