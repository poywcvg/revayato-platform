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
  <div class="page-shell py-4 sm:py-8 lg:py-12">
    <section class="auth-shell grid overflow-hidden rounded-[1.75rem] bg-surface shadow-2xl shadow-black/30 ring-1 ring-line lg:grid-cols-[.9fr_1.1fr] lg:rounded-[2rem]">
      <aside class="relative order-2 overflow-hidden bg-canvas-soft p-6 text-ink sm:p-8 lg:order-none lg:p-10">
        <div class="relative">
          <span class="grid size-12 place-items-center rounded-2xl bg-primary-500/12 text-primary-300 ring-1 ring-primary-500/20"><CinematicIcon :name="icon" class="size-6" /></span>
          <p class="mt-5 text-xs font-black text-primary-400">{{ eyebrow }}</p>
          <h1 class="mt-1 text-3xl font-black sm:text-4xl">{{ title }}</h1>
          <p class="mt-4 max-w-md text-sm leading-8 text-slate-400">{{ description }}</p>
          <ul class="mt-6 grid gap-3 text-xs font-bold text-slate-300 sm:grid-cols-2 lg:mt-8 lg:grid-cols-1">
            <li class="flex items-center gap-2"><CinematicIcon name="check-circle" class="size-4.5 text-primary-400" />ادامه تماشا روی دستگاه‌های مختلف</li>
            <li class="flex items-center gap-2"><CinematicIcon name="check-circle" class="size-4.5 text-primary-400" />لیست شخصی فیلم و سریال</li>
            <li class="flex items-center gap-2"><CinematicIcon name="shield-check" class="size-4.5 text-success" />پیشنهاد شخصی فقط با اجازه تو</li>
          </ul>
        </div>
      </aside>
      <div class="order-1 flex items-center p-6 sm:p-10 lg:order-none lg:p-12">
        <div class="mx-auto w-full max-w-md">
          <slot />
        </div>
      </div>
    </section>
  </div>
</template>
