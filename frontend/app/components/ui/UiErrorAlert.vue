<script setup lang="ts">
import type { AppErrorDetails } from '~/types'

defineProps<{ error: AppErrorDetails }>()
defineEmits<{ close: [] }>()
</script>

<template>
  <section class="rounded-2xl border border-error/25 bg-error/8 p-4" role="alert" aria-live="polite">
    <div class="flex items-start gap-3">
      <span class="mt-0.5 grid size-9 shrink-0 place-items-center rounded-xl bg-error/12 text-error"><CinematicIcon name="alert-triangle" class="size-5" /></span>
      <div class="min-w-0 flex-1">
        <p class="text-sm font-black text-ink">{{ error.title }}</p>
        <p class="mt-1 text-sm leading-6 text-secondary">{{ error.message }}</p>
        <ul v-if="error.fields.length" class="mt-2 space-y-1 text-xs leading-6 text-secondary">
          <li v-for="item in error.fields" :key="item.field"><strong class="text-ink">{{ item.label }}:</strong> {{ item.message }}</li>
        </ul>
        <p v-else-if="error.reason && error.reason !== error.message" class="mt-2 rounded-xl bg-error/10 px-3 py-2 text-xs leading-6 text-secondary">
          <strong class="text-error">دلیل:</strong> {{ error.reason }}
        </p>
        <p v-if="error.hint" class="mt-2 flex items-start gap-1.5 text-xs leading-6 text-muted"><CinematicIcon name="info" class="mt-1 size-3.5 shrink-0 text-primary-400" />{{ error.hint }}</p>
      </div>
      <button type="button" class="grid size-11 shrink-0 place-items-center rounded-xl text-muted hover:bg-elevated hover:text-ink" aria-label="بستن پیام خطا" @click="$emit('close')"><CinematicIcon name="x" class="size-4" /></button>
    </div>
  </section>
</template>
