<script setup lang="ts">
import type { AppErrorDetails } from '~/types'

defineProps<{ error: AppErrorDetails }>()
defineEmits<{ close: [] }>()
</script>

<template>
  <section class="rounded-lg border border-error/25 bg-error/15 px-3 py-2.5 text-error" role="alert" aria-live="polite">
    <div class="flex items-center justify-between gap-2">
      <div class="flex min-w-0 items-center">
        <CinematicIcon name="alert-circle" class="size-5 shrink-0" />
        <p class="ms-2 truncate text-sm font-bold">{{ error.title }}</p>
      </div>
      <button
        type="button"
        aria-label="بستن پیام خطا"
        class="grid size-8 shrink-0 cursor-pointer place-items-center rounded-md text-error/80 transition-all hover:bg-error/10 hover:text-error active:scale-90"
        @click="$emit('close')"
      >
        <CinematicIcon name="x" class="size-4" />
      </button>
    </div>
    <div v-if="error.message || error.fields.length || error.reason || error.hint" class="mt-1 space-y-1 pe-10 text-xs leading-6 text-error/85">
      <p v-if="error.message && error.message !== error.title">{{ error.message }}</p>
      <ul v-if="error.fields.length">
        <li v-for="item in error.fields" :key="item.field"><strong>{{ item.label }}:</strong> {{ item.message }}</li>
      </ul>
      <p v-else-if="error.reason && error.reason !== error.message">
        <strong>دلیل:</strong> {{ error.reason }}
      </p>
      <p v-if="error.hint" class="text-error/70">{{ error.hint }}</p>
    </div>
  </section>
</template>
