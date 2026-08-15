<script setup lang="ts">
import type { CinematicIconName } from '~/types'

withDefaults(defineProps<{
  title: string
  eyebrow?: string
  description?: string
  href?: string
  linkLabel?: string
  dark?: boolean
  icon?: CinematicIconName | ''
}>(), {
  eyebrow: '',
  description: '',
  href: '',
  linkLabel: 'مشاهده همه',
  dark: false,
  icon: '',
})
</script>

<template>
  <header class="section-header mb-3.5 flex flex-col gap-2 sm:mb-5 sm:flex-row sm:items-end sm:justify-between sm:gap-4">
    <div class="flex min-w-0 flex-1 items-start gap-3">
      <span
        v-if="icon"
        class="section-icon"
        aria-hidden="true"
      >
        <CinematicIcon :name="icon" class="size-[1.15rem] sm:size-5" :stroke-width="1.55" />
      </span>
      <div class="min-w-0 flex-1">
        <p v-if="eyebrow" class="mb-0.5 inline-flex max-w-full items-center gap-1.5 text-[11px] font-medium text-muted sm:mb-1 sm:gap-2 sm:text-xs">
          <span class="hidden h-1.5 w-1.5 shrink-0 rounded-full bg-primary-500 sm:inline-block" />
          <span class="truncate">{{ eyebrow }}</span>
        </p>
        <h2 class="text-balance text-lg font-black tracking-tight text-ink sm:text-xl lg:text-2xl">
          <NuxtLink
            v-if="href"
            :to="href"
            class="transition hover:text-primary-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500/60"
          >
            {{ title }}
          </NuxtLink>
          <template v-else>{{ title }}</template>
        </h2>
        <p
          v-if="description"
          class="mt-1 hidden max-w-3xl text-pretty text-sm leading-6 sm:block"
          :class="dark ? 'text-secondary' : 'text-muted'"
        >
          {{ description }}
        </p>
      </div>
    </div>
    <div class="flex w-full shrink-0 flex-wrap items-center gap-2 sm:w-auto sm:justify-end">
      <slot name="actions" />
      <NuxtLink
        v-if="href"
        :to="href"
        class="group inline-flex min-h-11 shrink-0 items-center gap-1 rounded-xl px-1.5 text-xs font-medium text-muted transition hover:bg-primary-500/10 hover:text-primary-300 sm:px-2 sm:text-sm"
      >
        <span class="whitespace-nowrap">{{ linkLabel }}</span>
        <CinematicIcon name="arrow-left" class="size-3.5 shrink-0 transition-transform group-hover:-translate-x-0.5 sm:size-4" />
      </NuxtLink>
    </div>
  </header>
</template>
