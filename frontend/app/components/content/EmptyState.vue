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
  <div class="rounded-3xl border border-dashed px-5 py-14 text-center" :class="dark ? 'border-white/15 bg-white/[.035]' : 'border-line bg-surface'">
    <span class="mx-auto grid size-14 place-items-center rounded-2xl" :class="dark ? 'bg-white/5 text-muted ring-1 ring-white/10' : 'bg-elevated text-muted ring-1 ring-line'"><CinematicIcon :name="icon" class="size-7" /></span>
    <h2 class="mt-4 text-lg font-black text-ink">{{ title }}</h2>
    <p class="mx-auto mt-1.5 max-w-md text-sm leading-6" :class="dark ? 'text-slate-400' : 'text-slate-500'">{{ description }}</p>
    <NuxtLink v-if="actionHref" :to="actionHref" class="mt-5 inline-flex rounded-xl bg-primary-500 px-5 py-2.5 text-sm font-black text-night-950 hover:bg-primary-400">{{ actionLabel }}</NuxtLink>
  </div>
</template>
