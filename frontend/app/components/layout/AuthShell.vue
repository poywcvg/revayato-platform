<script setup lang="ts">
import type { CinematicIconName } from '~/types'

withDefaults(defineProps<{
  title: string
  eyebrow: string
  description: string
  icon?: CinematicIconName
}>(), {
  icon: 'user',
})
</script>

<template>
  <div class="page-section auth-shell-page">
    <section class="auth-shell grid overflow-hidden rounded-[1.25rem] bg-surface ring-1 ring-line sm:rounded-[1.75rem] lg:grid-cols-[.9fr_1.1fr] lg:rounded-[2rem]">
      <aside class="relative order-2 overflow-hidden bg-canvas-soft p-5 text-ink sm:p-8 lg:order-none lg:p-10">
        <div class="relative">
          <span class="grid size-11 place-items-center rounded-2xl bg-primary-500/12 text-primary-300 ring-1 ring-primary-500/20 sm:size-12"><CinematicIcon :name="icon" class="size-5 sm:size-6" /></span>
          <p class="mt-4 text-xs font-black text-primary-400 sm:mt-5">{{ eyebrow }}</p>
          <h1 class="mt-1 text-[clamp(1.55rem,5.5vw,2.5rem)] font-black leading-tight">{{ title }}</h1>
          <p class="mt-3 max-w-md text-sm leading-7 text-secondary sm:mt-4 sm:leading-8">{{ description }}</p>
          <ul class="mt-5 grid gap-2.5 text-xs font-bold text-secondary sm:mt-6 sm:grid-cols-2 sm:gap-3 lg:mt-8 lg:grid-cols-1">
            <li class="flex items-center gap-2"><CinematicIcon name="check-circle" class="size-4.5 shrink-0 text-primary-400" />ادامه تماشا روی دستگاه‌های مختلف</li>
            <li class="flex items-center gap-2"><CinematicIcon name="check-circle" class="size-4.5 shrink-0 text-primary-400" />لیست شخصی فیلم و سریال</li>
            <li class="flex items-center gap-2 sm:col-span-2 lg:col-span-1"><CinematicIcon name="shield-check" class="size-4.5 shrink-0 text-success" />پیشنهاد شخصی فقط با اجازه تو</li>
          </ul>
        </div>
      </aside>
      <div class="order-1 flex items-center p-5 sm:p-10 lg:order-none lg:p-12">
        <div class="mx-auto w-full max-w-md min-w-0">
          <slot />
        </div>
      </div>
    </section>
  </div>
</template>
