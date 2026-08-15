<script setup lang="ts">
import type { CinematicIconName } from '~/types'

withDefaults(defineProps<{ title?: string; description?: string; icon?: CinematicIconName; actionLabel?: string; actionHref?: string; dark?: boolean }>(), {
  title: 'نتیجه‌ای پیدا نشد',
  description: 'فیلترها را تغییر دهید یا عبارت دیگری را جستجو کنید.',
  icon: 'film',
  actionLabel: '',
  actionHref: '',
  dark: false,
})
</script>

<template>
  <div class="relative overflow-hidden rounded-3xl border border-dashed px-5 py-12 text-center sm:py-14" :class="dark ? 'border-white/15 bg-white/[.035]' : 'border-line bg-surface'">
    <span class="pointer-events-none absolute inset-x-8 top-0 h-px bg-gradient-to-r from-transparent via-primary-500/45 to-transparent" aria-hidden="true" />
    <span class="mx-auto grid size-14 place-items-center rounded-2xl bg-primary-500/12 text-brand ring-1 ring-primary-500/20"><CinematicIcon :name="icon" class="size-7" /></span>
    <h2 class="mt-4 text-lg font-black text-ink">{{ title }}</h2>
    <p class="mx-auto mt-1.5 max-w-md text-sm leading-7 text-secondary">{{ description }}</p>
    <NuxtLink v-if="actionHref" :to="actionHref" class="ui-primary-button mt-5">
      {{ actionLabel }}
      <CinematicIcon name="arrow-left" class="size-4" />
    </NuxtLink>
  </div>
</template>
