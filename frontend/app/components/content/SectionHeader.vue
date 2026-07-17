<script setup lang="ts">
withDefaults(defineProps<{
  title: string
  eyebrow?: string
  description?: string
  href?: string
  linkLabel?: string
  dark?: boolean
}>(), { eyebrow: '', description: '', href: '', linkLabel: 'مشاهده همه', dark: false })
</script>

<template>
  <header class="mb-5 flex flex-col items-start justify-between gap-3 sm:flex-row sm:items-end sm:gap-5">
    <div class="min-w-0">
      <p v-if="eyebrow" class="mb-1 inline-flex items-center gap-2 text-xs font-black text-primary-300"><span class="h-1.5 w-1.5 rounded-full bg-primary-500" />{{ eyebrow }}</p>
      <h2 class="text-xl font-black tracking-tight text-ink sm:text-2xl">{{ title }}</h2>
      <p v-if="description" class="mt-1.5 max-w-2xl text-sm leading-6" :class="dark ? 'text-slate-400' : 'text-slate-500'">{{ description }}</p>
    </div>
    <div class="flex w-full flex-wrap items-center justify-between gap-2 sm:w-auto sm:shrink-0 sm:justify-end">
      <slot name="actions" />
      <NuxtLink v-if="href" :to="href" class="group inline-flex min-h-11 shrink-0 items-center gap-1 rounded-xl px-2 text-sm font-bold text-muted transition hover:bg-primary-500/10 hover:text-primary-300">
        {{ linkLabel }}
        <CinematicIcon name="arrow-left" class="size-4 transition-transform group-hover:-translate-x-0.5" />
      </NuxtLink>
    </div>
  </header>
</template>
